"""Real phase orchestration: calibration, one series, all series, status."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import time
import tomllib
from dataclasses import asdict
from pathlib import Path

from . import config
from .logs import RunLog, drop_rows, read_csv
from .loop import Ident, Plan, SeriesState, calibrate, run_series
from .real_executor import BudgetExhausted, Ledger, RealExecutor, Workspace
from .real_metrics import RealMetrics

REAL_DIR = config.DATA_DIR / "real" / "real"


class StopForNow(Exception):
    pass


def settings() -> dict:
    with open(config.CONFIG_DIR / "real.toml", "rb") as f:
        return tomllib.load(f)


def work_root() -> Path:
    return Path(settings()["work_root"])


def ledger() -> Ledger:
    s = settings()
    return Ledger(work_root() / "ledger.jsonl", s["total_cap_usd"])


def specs() -> tuple[dict, list[str], list[str]]:
    out, order = {}, {}
    for kind in ("items", "calibration"):
        with open(config.ROOT / "backlog" / f"{kind}.json", encoding="utf-8") as f:
            data = json.load(f)["items"]
        order[kind] = [d["id"] for d in data]
        out.update({d["id"]: d for d in data})
    return out, order["items"], order["calibration"]


def prompts() -> dict:
    d = config.CONFIG_DIR / "prompts"
    return {p.stem: p.read_text(encoding="utf-8") for p in d.glob("*.txt")}


def price_table() -> dict:
    return config.prices()["models"]


def _executor(ws: Workspace, label: str, accepted=None) -> RealExecutor:
    s = settings()
    exp = config.experiment()
    spec, _, _ = specs()
    return RealExecutor(ws, model=s["model"], price_table=price_table(), prompts=prompts(),
                        specs=spec, ledger=ledger(), session_timeout_s=exp["session_timeout_s"],
                        transcript_dir=work_root() / "transcripts", accepted=accepted,
                        label=label)


def _workspace(name: str) -> Workspace:
    s = settings()
    return Workspace(work_root() / name, config.ROOT, s["start_ref"], config.ROOT / "acceptance")


def _cli_version() -> str:
    try:
        return subprocess.run(["claude", "--version"], capture_output=True, text=True,
                              timeout=30).stdout.strip()
    except OSError:
        return ""


def _start_commit() -> str:
    return subprocess.run(["git", "rev-parse", f"{settings()['start_ref']}^{{commit}}"],
                          cwd=config.ROOT, capture_output=True, text=True).stdout.strip()


def estimate(plan: Plan, spent_so_far: float) -> dict:
    exp = config.experiment()
    n_series = len(exp["groups"]) * exp["reps"]
    per_series_upper = exp["weeks"] * plan.budget + plan.cap * exp["runaway_guard_multiplier"]
    return {
        "series": n_series,
        "spent_before_formal_usd": spent_so_far,
        "formal_upper_usd": n_series * per_series_upper,
        "total_upper_usd": spent_so_far + n_series * per_series_upper,
        "note": "upper bound: every week spends its whole budget, plus one runaway-guard "
                "overspend per series in week 8; unused budget makes the real figure lower",
    }


def cmd_calibrate(force: bool = False) -> dict:
    exp, thr, s = config.experiment(), config.thresholds(), settings()
    if read_csv(REAL_DIR / "weeks.csv") and not force:
        raise SystemExit("formal-run logs exist; refusing to recalibrate (use --force)")
    led = ledger()
    ws = _workspace("calib")
    ws.create()
    baseline = RealMetrics(ws.path).measure()
    log = RunLog(REAL_DIR, fresh=True)
    _, _, calib_ids = specs()
    ex = _executor(ws, "calib")
    costs, firsts = calibrate(ex, calib_ids, exp, log, "real", "real",
                              guard_usd=exp["calibration_guard_usd"])
    plan = Plan.from_calibration(costs, firsts, baseline, exp)
    est = estimate(plan, led.total())
    meta = {
        "phase": "real", "hypothesis": "real",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=config.ROOT,
                                     capture_output=True, text=True).stdout.strip(),
        "start_ref": s["start_ref"], "start_commit": _start_commit(),
        "model": s["model"], "cli_version": _cli_version(),
        "prices": price_table()[s["model"]], "prices_source": "config/prices.toml",
        "experiment": exp, "thresholds": thr, "real": s,
        "plan": plan.to_dict(), "estimate": est,
        "calibration_items": calib_ids,
    }
    log.write_run_meta(meta)
    return meta


def _state_path(group: str, rep: int) -> Path:
    return work_root() / "state" / f"{group}-r{rep}.json"


def load_state(group: str, rep: int) -> dict | None:
    p = _state_path(group, rep)
    return json.loads(p.read_text()) if p.exists() else None


def save_state(group: str, rep: int, data: dict) -> None:
    p = _state_path(group, rep)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(p)


def cmd_run(group: str, rep: int, deadline_min: float) -> int:
    """Run or resume one series. Exit codes: 0 done, 3 stopped at deadline, 4 budget cap."""
    exp, thr = config.experiment(), config.thresholds()
    with open(REAL_DIR / "run.json", encoding="utf-8") as f:
        meta = json.load(f)
    plan = Plan(**meta["plan"])
    _, backlog, _ = specs()
    label = f"{group}-r{rep}"
    ws = _workspace(label)
    st = load_state(group, rep)
    if st and st.get("status") == "done":
        return 0
    if st:
        ws.reset(st["head"]) if ws.path.exists() else None
        if not ws.path.exists():
            raise SystemExit(f"{label}: state exists but working copy is gone; cannot resume")
        drop_rows(REAL_DIR, group, rep, st["week_done"])
        series = SeriesState(**st["series"])
        accepted = st["accepted"]
    else:
        ws.create()
        drop_rows(REAL_DIR, group, rep, -1)
        series, accepted = None, []
    ex = _executor(ws, label, accepted)
    log = RunLog(REAL_DIR)
    t0 = time.time()

    def on_week_end(week: int, state: SeriesState) -> None:
        done = week >= exp["weeks"]
        save_state(group, rep, {"series": asdict(state), "head": ws.head(),
                                "accepted": ex.accepted, "week_done": week,
                                "status": "done" if done else "running"})
        if not done and time.time() - t0 > deadline_min * 60:
            raise StopForNow()

    try:
        run_series(ex, RealMetrics(ws.path), plan, exp, thr, backlog, log,
                   Ident("real", "real", group, rep), state=series, on_week_end=on_week_end)
    except StopForNow:
        return 3
    except BudgetExhausted as e:
        st = load_state(group, rep) or {"week_done": 0}
        drop_rows(REAL_DIR, group, rep, st.get("week_done", 0))
        if st.get("series"):
            st["status"] = "budget_exhausted"
            save_state(group, rep, st)
        print(f"{label}: budget cap reached: {e}", file=sys.stderr)
        return 4
    return 0


def cmd_run_all(parallel: int, deadline_min: float) -> int:
    exp = config.experiment()
    pending = [(g, r) for r in range(1, exp["reps"] + 1) for g in exp["groups"]
               if (load_state(g, r) or {}).get("status") not in ("done", "budget_exhausted")]
    procs: dict[tuple, subprocess.Popen] = {}
    codes = {}
    logs_dir = work_root() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    while pending or procs:
        while pending and len(procs) < parallel:
            g, r = pending.pop(0)
            out = open(logs_dir / f"{g}-r{r}.log", "a")
            procs[(g, r)] = subprocess.Popen(
                [sys.executable, "-m", "harness", "real", "run", "--group", g, "--rep", str(r),
                 "--deadline-min", str(deadline_min)],
                cwd=config.ROOT, stdout=out, stderr=subprocess.STDOUT)
        time.sleep(5)
        for key, p in list(procs.items()):
            if p.poll() is not None:
                codes[key] = p.returncode
                del procs[key]
    for key, code in sorted(codes.items()):
        print(f"{key[0]}-r{key[1]}: exit {code}")
    return max(codes.values(), default=0)


def cmd_status() -> str:
    exp = config.experiment()
    lines = [f"ledger total: {ledger().total():.2f} USD (cap {settings()['total_cap_usd']:.0f})"]
    for r in range(1, exp["reps"] + 1):
        for g in exp["groups"]:
            st = load_state(g, r) or {}
            lines.append(f"{g}-r{r}: week {st.get('week_done', 0)}/{exp['weeks']} "
                         f"{st.get('status', 'not started')} accepted={len(st.get('accepted', []))}")
    return "\n".join(lines)
