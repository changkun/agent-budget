"""Capability experiment: does the need for maintenance depend on the model? (PLAN-capability.md)

Code states live in bare git repositories under <work_root>/store, one per (producer, rep) plus
one for v0. A state is a tag in its repository:

    v0                           site-v0
    <prod>-r<rep>-k<k>-R         producer <prod> after k backlog items, no maintenance
    <prod>-r<rep>-k<k>-M<maint>  that R state after maintenance by <maint>

Work is split into jobs (producer series, maintenance, probes) that run on a pool of worker
threads. Finished jobs are recorded in jobs.jsonl, so a stopped run resumes where it left off.
Session rows go to docs/data/capability/sessions.csv, state metrics to states.csv.
"""
from __future__ import annotations

import csv
import datetime as dt
import fcntl
import json
import random
import shutil
import subprocess
import sys
import threading
import time
import tomllib
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from statistics import fmean

from . import config, real_run
from .logs import _fmt, read_csv
from .interfaces import TaskResult
from .loop import check_trigger
from .real_executor import BudgetExhausted, InfraError, Ledger, RealExecutor, Workspace
from .real_metrics import RealMetrics
from .real_metrics import run as run_tool

DATA = config.DATA_DIR / "capability"
START_REF = "site-v0"

SESSION_COLUMNS = [
    "job", "block", "kind", "model", "producer", "rep", "k", "state", "state_kind",
    "maintainer", "item", "task_type", "debug_index", "input_tokens", "cache_write_tokens",
    "cache_read_tokens", "output_tokens", "cost_usd", "cli_cost_usd", "accepted",
    "rolled_back", "forced_stop", "num_turns", "duration_s", "session_id", "model_reported",
    "effort", "attempt", "started_at",
]
STATE_COLUMNS = [
    "state", "producer", "rep", "k", "kind", "maintainer", "base", "commit", "n_accepted",
    "accepted_items", "loc", "max_file_lines", "dup_ratio", "coverage", "vulns",
    "outdated_deps", "build_ok", "tests_ok", "probes_failing", "maint_fired", "maint_kept",
    "maint_cost_usd",
]
METRIC_TYPES = {"loc": int, "max_file_lines": int, "dup_ratio": float, "coverage": float,
                "vulns": int, "outdated_deps": int, "build_ok": int, "tests_ok": int}
KIND_RANK = {"feas_probe": 0, "feas_maint": 0, "produce": 0, "maint": 1, "probe": 2}

_CSV_LOCK = threading.Lock()


# ---------------------------------------------------------------- settings

def settings() -> dict:
    with open(config.CONFIG_DIR / "capability.toml", "rb") as f:
        return tomllib.load(f)


def root() -> Path:
    return Path(settings()["work_root"])


def ledger() -> Ledger:
    return Ledger(root() / "ledger.jsonl", settings()["total_cap_usd"])


def short(model: str) -> str:
    return settings()["models"][model]


def long_name(name: str) -> str:
    return {v: k for k, v in settings()["models"].items()}[name]


def guard(model: str) -> float:
    return settings()["guard_usd"][model]


def effort(model: str) -> str | None:
    s = settings()
    return s.get("effort_override", {}).get(model, s.get("effort")) or None


def max_debug() -> int:
    return config.experiment()["max_debug"]


# ---------------------------------------------------------------- logs

def append(name: str, columns: list[str], row: dict) -> None:
    unknown = set(row) - set(columns)
    if unknown:
        raise KeyError(f"unknown {name} columns: {sorted(unknown)}")
    path = DATA / f"{name}.csv"
    with _CSV_LOCK:
        DATA.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            w = csv.writer(f)
            if new:
                w.writerow(columns)
            w.writerow([_fmt(row.get(c)) for c in columns])


def states() -> dict[str, dict]:
    return {r["state"]: r for r in read_csv(DATA / "states.csv")}


def state_metrics(sid: str) -> dict:
    row = states()[sid]
    return {k: (t(float(row[k])) if row[k] != "" else None) for k, t in METRIC_TYPES.items()}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def log(msg: str) -> None:
    line = f"{now()} {msg}"
    print(line, flush=True)
    with _CSV_LOCK:
        with open(root() / "run.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")


# ---------------------------------------------------------------- states

def state_id(producer: str, rep: int, k: int, maintainer: str | None = None) -> str:
    return f"{producer}-r{rep}-k{k}-" + (f"M{maintainer}" if maintainer else "R")


def parse_state(sid: str) -> dict:
    if sid == "v0":
        return {"producer": "", "rep": "", "k": 0, "kind": "V0", "maintainer": ""}
    prod, rep, k, kind = sid.split("-")
    return {"producer": prod, "rep": int(rep[1:]), "k": int(k[1:]),
            "kind": "R" if kind == "R" else "M", "maintainer": kind[1:] if kind != "R" else ""}


def maintained(base: str, model: str) -> str:
    assert base.endswith("-R"), base
    return base[:-1] + "M" + short(model)


def store_repo(sid: str) -> Path:
    if sid == "v0":
        return root() / "store" / "v0.git"
    p = parse_state(sid)
    return root() / "store" / f"{p['producer']}-r{p['rep']}.git"


def _git(cwd: Path, *args: str) -> str:
    res = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd}: {res.stderr.strip()}")
    return res.stdout.strip()


def has_state(sid: str) -> bool:
    repo = store_repo(sid)
    return repo.exists() and subprocess.run(
        ["git", "rev-parse", "-q", "--verify", f"refs/tags/{sid}"], cwd=repo,
        capture_output=True).returncode == 0


def save_state(sid: str, workdir: Path) -> str:
    repo = store_repo(sid)
    if not repo.exists():
        repo.parent.mkdir(parents=True, exist_ok=True)
        _git(repo.parent, "init", "-q", "--bare", repo.name)
    _git(workdir, "push", "-q", "--force", str(repo), f"HEAD:refs/tags/{sid}")
    return _git(workdir, "rev-parse", "HEAD")


def accepted_items(workdir: Path) -> list[str]:
    msgs = _git(workdir, "log", "--reverse", "--format=%s").splitlines()
    return [m.split()[1] for m in msgs if m.startswith("impl ")]


def _install(dest: Path) -> None:
    cache = root() / "node_modules_cache"
    lock = dest / "package-lock.json"
    if cache.exists() and lock.exists() and lock.read_bytes() == (root() / "v0.package-lock.json").read_bytes():
        shutil.copytree(cache, dest / "node_modules", symlinks=True)
        return
    res = run_tool(["npm", "ci", "--no-audit"], dest, timeout=600)
    if res.returncode != 0:
        raise RuntimeError(f"npm ci failed in {dest}: {res.stderr[-1000:]}")


def checkout(sid: str, dest: Path) -> list[str]:
    """Fresh working copy of a state, with node_modules; returns its accepted backlog items."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    _git(dest, "init", "-q", "-b", "work-base")
    _git(dest, "fetch", "-q", str(store_repo(sid)), f"refs/tags/{sid}:refs/tags/{sid}")
    _git(dest, "checkout", "-q", "-b", "work", sid)
    _install(dest)
    return accepted_items(dest)


def accepted_pass(workdir: Path, items: list[str]) -> bool:
    """Do the acceptance tests of the state's accepted items pass (sanity check)?"""
    if not items:
        return True
    ws = _ws(workdir)
    ws.stage_acceptance(items)
    res = run_tool(["node", "--test", "acceptance/*.test.js"], workdir, timeout=600)
    shutil.rmtree(workdir / "acceptance")
    return res.returncode == 0


def probe_check(workdir: Path) -> int:
    """Number of probe acceptance tests that fail on this state (all of them should)."""
    acc = workdir / "acceptance"
    if acc.exists():
        shutil.rmtree(acc)
    acc.mkdir()
    src = config.ROOT / "acceptance"
    shutil.copy2(src / "_helpers.js", acc / "_helpers.js")
    failing = 0
    for p in settings()["probes"]:
        shutil.copy2(src / f"{p}.test.js", acc / f"{p}.test.js")
        res = run_tool(["node", "--test", f"acceptance/{p}.test.js"], workdir, timeout=120)
        failing += res.returncode != 0
    shutil.rmtree(acc)
    return failing


def record_state(sid: str, workdir: Path, base: str = "", extra: dict | None = None) -> dict:
    p = parse_state(sid)
    items = accepted_items(workdir)
    m = RealMetrics(workdir).measure()
    row = {"state": sid, "producer": p["producer"], "rep": p["rep"], "k": p["k"],
           "kind": p["kind"], "maintainer": p["maintainer"], "base": base,
           "commit": _git(workdir, "rev-parse", "HEAD"), "n_accepted": len(items),
           "accepted_items": ";".join(items), "probes_failing": probe_check(workdir), **m,
           **(extra or {})}
    append("states", STATE_COLUMNS, row)
    return row


# ---------------------------------------------------------------- preparation (no model use)

def prepare() -> str:
    s = settings()
    r = root()
    (r / "store").mkdir(parents=True, exist_ok=True)
    done = states()
    if not store_repo("v0").exists():
        ws = Workspace(r / "tmp" / "v0", config.ROOT, START_REF, config.ROOT / "acceptance")
        ws.create()
        save_state("v0", ws.path)
        if (r / "node_modules_cache").exists():
            shutil.rmtree(r / "node_modules_cache")
        shutil.copytree(ws.path / "node_modules", r / "node_modules_cache", symlinks=True)
        shutil.copy2(ws.path / "package-lock.json", r / "v0.package-lock.json")
        shutil.rmtree(ws.path)
    manifest = json.loads((config.ROOT / "snapshots" / "manifest.json").read_text())
    for rep in s["reps"]:
        repo = r / "store" / f"sonnet55-r{rep}.git"
        if not repo.exists():
            _git(r / "store", "clone", "-q", "--bare",
                 str(config.ROOT / "snapshots" / f"nomaint-r{rep}.bundle"), repo.name)
        entry = next(e for e in manifest["series"] if e["series"] == f"nomaint-r{rep}")
        for k in s["sonnet_k"]:
            c = [c for c in entry["commits"] if c["items"] <= k][-1]
            if c["items"] != k:
                raise RuntimeError(f"nomaint-r{rep} has no state with exactly {k} items")
            _git(repo, "tag", "-f", state_id("sonnet55", rep, k), c["sha"])
    todo = ["v0"] + [state_id("sonnet55", rep, k) for rep in s["reps"] for k in s["sonnet_k"]]
    lines = []
    for sid in todo:
        if sid in done:
            continue
        dest = r / "tmp" / sid
        items = checkout(sid, dest)
        ok = accepted_pass(dest, items)
        row = record_state(sid, dest)
        shutil.rmtree(dest)
        lines.append(f"{sid}: items {row['n_accepted']}, loc {row['loc']}, "
                     f"max file {row['max_file_lines']}, coverage {row['coverage']}, "
                     f"dup {row['dup_ratio']}, probes failing "
                     f"{row['probes_failing']}/{len(s['probes'])}, accepted tests pass {ok}")
    return "\n".join(lines) or "already prepared"


# ---------------------------------------------------------------- jobs

@dataclass
class Job:
    id: str
    block: str
    kind: str              # feas_probe | feas_maint | produce | maint | probe
    model: str             # model that runs the sessions
    state: str = ""        # probe/maint: state worked on; produce: the R state it builds
    item: str = ""         # probe id
    deps: list = field(default_factory=list)
    order: float = 0.0
    attempt: int = 0

    @property
    def label(self) -> str:
        return self.id.replace(":", "_") + f"_a{self.attempt}"


def _executor(ws: Workspace, job: Job, accepted: list[str]) -> RealExecutor:
    s = settings()
    spec, _, _ = real_run.specs()
    return RealExecutor(ws, model=job.model, price_table=real_run.price_table(),
                        prompts=real_run.prompts(), specs=spec, ledger=ledger(),
                        session_timeout_s=s["session_timeout_s"],
                        transcript_dir=root() / "transcripts", accepted=accepted,
                        label=job.label, effort=effort(job.model),
                        ledger_meta={"block": job.block, "model": job.model, "job": job.id})


def _row(job: Job, r: TaskResult, task_type: str, item: str, debug_index: int, k: int,
         state: str, started: str) -> dict:
    p = parse_state(state)
    return {"job": job.id, "block": job.block, "kind": job.kind, "model": short(job.model),
            "producer": p["producer"], "rep": p["rep"], "k": k, "state": state,
            "state_kind": p["kind"], "maintainer": p["maintainer"], "item": item,
            "task_type": task_type, "debug_index": debug_index,
            "input_tokens": r.input_tokens, "cache_write_tokens": r.cache_write_tokens,
            "cache_read_tokens": r.cache_read_tokens, "output_tokens": r.output_tokens,
            "cost_usd": r.cost_usd, "cli_cost_usd": r.extra.get("cli_cost_usd"),
            "accepted": r.accepted, "rolled_back": False, "forced_stop": r.forced_stop,
            "num_turns": r.extra.get("num_turns"),
            "duration_s": round(r.duration_s, 1) if r.duration_s else None,
            "session_id": r.session_id, "model_reported": r.model, "effort": effort(job.model),
            "attempt": job.attempt, "started_at": started}


def _ws(path: Path) -> Workspace:
    return Workspace(path, config.ROOT, START_REF, config.ROOT / "acceptance")


def run_probe(job: Job) -> None:
    dest = root() / "runs" / job.label
    accepted = checkout(job.state, dest)
    ex = _executor(_ws(dest), job, accepted)
    ex.start("impl", job.item)
    rows = []
    for j in range(max_debug() + 1):
        started = now()
        r = ex.run("impl" if j == 0 else "debug", job.item, j, 0, guard(job.model),
                   {"debug_index": j})
        rows.append(_row(job, r, "impl" if j == 0 else "debug", job.item, j,
                         parse_state(job.state)["k"], job.state, started))
        if r.accepted:
            break
    rows[-1]["rolled_back"] = not rows[-1]["accepted"]
    for row in rows:
        append("sessions", SESSION_COLUMNS, row)
    shutil.rmtree(dest, ignore_errors=True)


def run_maint(job: Job, agents: list[str] | None = None, save: bool = True) -> None:
    base = job.state
    dest = root() / "runs" / job.label
    accepted = checkout(base, dest)
    ws = _ws(dest)
    ex = _executor(ws, job, accepted)
    m = state_metrics(base)
    baseline = state_metrics("v0")
    thr = config.thresholds()
    rows, fired_agents, kept, cost = [], [], [], 0.0
    for agent in agents or settings()["maint_agents"]:
        fired = check_trigger(agent, m, baseline, thr)
        if not fired:
            continue
        task_type = f"maint_{agent}"
        ex.start(task_type, None)
        started = now()
        r = ex.run(task_type, None, 0, 0, guard(job.model), {"trigger": fired})
        ex.finish(keep=r.accepted)
        row = _row(job, r, task_type, "", 0, parse_state(base)["k"], base, started)
        row["rolled_back"] = not r.accepted
        rows.append(row)
        fired_agents.append(agent)
        cost += r.cost_usd
        if r.accepted:
            kept.append(agent)
    for row in rows:
        append("sessions", SESSION_COLUMNS, row)
    if save:
        out = maintained(base, job.model)
        save_state(out, dest)
        record_state(out, dest, base=base, extra={
            "maint_fired": ";".join(fired_agents), "maint_kept": ";".join(kept),
            "maint_cost_usd": cost})
    shutil.rmtree(dest, ignore_errors=True)


def run_produce(job: Job) -> None:
    s = settings()
    p = parse_state(job.state)
    wdir = root() / "produce" / f"{p['producer']}-r{p['rep']}"
    prog_path = root() / "progress" / f"{p['producer']}-r{p['rep']}.json"
    prog = json.loads(prog_path.read_text()) if prog_path.exists() else None
    ws = _ws(wdir)
    if prog and wdir.exists():
        ws.reset(prog["head"])
        accepted, start = prog["accepted"], prog["next"]
    else:
        ws.create()
        accepted, start = [], 0
    ex = _executor(ws, job, accepted)
    backlog = real_run.specs()[1][:s["producer_k"]]
    for idx in range(start, len(backlog)):
        item = backlog[idx]
        ex.start("impl", item)
        rows = []
        for j in range(max_debug() + 1):
            started = now()
            r = ex.run("impl" if j == 0 else "debug", item, j, 0, guard(job.model),
                       {"debug_index": j})
            rows.append(_row(job, r, "impl" if j == 0 else "debug", item, j, idx, job.state,
                             started))
            if r.accepted:
                break
        ex.finish(keep=rows[-1]["accepted"])
        rows[-1]["rolled_back"] = not rows[-1]["accepted"]
        for row in rows:
            append("sessions", SESSION_COLUMNS, row)
        prog_path.parent.mkdir(parents=True, exist_ok=True)
        prog_path.write_text(json.dumps({"next": idx + 1, "head": ws.head(),
                                         "accepted": ex.accepted}))
    save_state(job.state, wdir)
    if job.state not in states():
        record_state(job.state, wdir)


RUNNERS = {
    "probe": run_probe,
    "feas_probe": run_probe,
    "maint": run_maint,
    "feas_maint": lambda job: run_maint(job, agents=["tests"], save=False),
    "produce": run_produce,
}


# ---------------------------------------------------------------- job lists

def _order(job_id: str) -> float:
    return random.Random(f"{settings()['seed']}:{job_id}").random()


def feasibility_jobs(models: list[str]) -> list[Job]:
    jobs = []
    for m in models:
        n = short(m)
        jobs += [Job(f"feas:{n}:C1:{i}", "feas", "feas_probe", m, "v0", "C1") for i in (1, 2)]
        jobs.append(Job(f"feas:{n}:maint_tests", "feas", "feas_maint", m,
                        state_id("sonnet55", 1, 29)))
    return jobs


def main_jobs(blocks: list[str]) -> list[Job]:
    s = settings()
    b = s["blocks"]
    ref, probes, reps = s["reference"], s["probes"], s["reps"]
    K = s["producer_k"]
    jobs: dict[str, Job] = {}

    def add(job: Job) -> str:
        job.order = _order(job.id)
        jobs.setdefault(job.id, job)
        return job.id

    def maint(model: str, base: str, block: str, deps=()) -> str:
        return add(Job(f"maint:{short(model)}:{base}", block, "maint", model, base,
                       deps=list(deps)))

    def probe(model: str, state: str, block: str, deps) -> None:
        for p in probes:
            add(Job(f"probe:{short(model)}:{state}:{p}", block, "probe", model, state, p,
                    deps=sorted(set(deps))))

    def consumer_on_sonnet(c: str, block: str) -> None:
        probe(c, "v0", block, [])
        for rep in reps:
            for k in s["sonnet_k"]:
                base = state_id("sonnet55", rep, k)
                ms = maint(ref, base, "core2")
                mine = maint(c, base, block) if c != ref else ms
                for st in {base, maintained(base, ref), maintained(base, c)}:
                    probe(c, st, block, [ms, mine])

    def producer(pm: str, block: str) -> None:
        for rep in reps:
            base = state_id(short(pm), rep, K)
            prod = add(Job(f"produce:{short(pm)}:r{rep}", block, "produce", pm, base))
            ms = maint(ref, base, block, [prod])
            mp = maint(pm, base, block, [prod])
            probe(ref, base, block, [ms, mp])
            probe(ref, maintained(base, ref), block, [ms, mp])
            probe(pm, base, block, [ms, mp])
            probe(pm, maintained(base, pm), block, [ms, mp])

    if "core2" in blocks:
        for c in b["core_consumers"]:
            consumer_on_sonnet(c, "core2")
    if "core3" in blocks:
        for pm in b["core_producers"]:
            producer(pm, "core3")
    if "A2" in blocks:
        consumer_on_sonnet(b["option_a"], "A2")
    if "A3" in blocks:
        producer(b["option_a"], "A3")
    if "A2s" in blocks and "A2" not in blocks:
        # reduced option A: the top model as consumer at k = 29 only, against the fixed
        # maintainer (v0, R and MS states; no self-maintenance)
        fable = b["option_a"]
        probe(fable, "v0", "A2s", [])
        for rep in reps:
            base = state_id("sonnet55", rep, 29)
            ms = maint(ref, base, "core2")
            probe(fable, base, "A2s", [ms])
            probe(fable, maintained(base, ref), "A2s", [ms])
    if "D" in blocks:
        # Sonnet as the fixed maintainer: every non-reference consumer on every
        # non-reference producer's R and MS states (diagonal R probes exist in core3).
        for pm in b["core_producers"]:
            for c in b["core_consumers"]:
                if c == ref:
                    continue
                for rep in reps:
                    base = state_id(short(pm), rep, K)
                    ms = f"maint:{short(ref)}:{base}"
                    probe(c, base, "D", [ms])
                    probe(c, maintained(base, ref), "D", [ms])
    return list(jobs.values())


# ---------------------------------------------------------------- scheduler

def _done_ids() -> set[str]:
    path = root() / "jobs.jsonl"
    if not path.exists():
        return set()
    return {json.loads(line)["id"] for line in path.read_text().splitlines()
            if line.strip() and json.loads(line)["status"] == "done"}


def _mark(job: Job, status: str, note: str = "") -> None:
    with _CSV_LOCK:
        with open(root() / "jobs.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": job.id, "status": status, "attempt": job.attempt,
                                "t": now(), "note": note[-500:]}) + "\n")


def spend_by_block() -> dict[str, float]:
    out: dict[str, float] = {}
    path = root() / "ledger.jsonl"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                e = json.loads(line)
                out[e.get("block", "")] = out.get(e.get("block", ""), 0.0) + e["cost_usd"]
    return out


class Scheduler:
    def __init__(self, jobs: list[Job], parallel: int, deadline_h: float,
                 block_limits: dict[str, float] | None = None):
        self.jobs = {j.id: j for j in jobs}
        self.done = _done_ids() & set(self.jobs)
        self.failures: dict[str, int] = {}
        self.running: set[str] = set()
        self.lock = threading.Lock()
        self.parallel = parallel
        self.deadline = time.time() + deadline_h * 3600
        self.block_limits = block_limits or {}
        self.block_rank = {b: i for i, b in enumerate(["feas", *settings()["blocks"]["order"]])}
        self.pause_until = 0.0
        self.backoff = 60.0
        self.stop_reason = ""

    def _ready(self) -> list[Job]:
        spend = spend_by_block() if self.block_limits else {}
        over = {b for b, lim in self.block_limits.items() if spend.get(b, 0.0) > lim}
        return [j for j in self.jobs.values()
                if j.id not in self.done and j.id not in self.running
                and self.failures.get(j.id, 0) < 2 and j.block not in over
                and all(d in self.done for d in j.deps)]

    def _next(self) -> tuple[Job | None, bool]:
        with self.lock:
            if self.stop_reason:
                return None, True
            if time.time() > self.deadline:
                self.stop_reason = "deadline"
                return None, True
            ready = self._ready()
            if not ready:
                return None, not self.running
            job = min(ready, key=lambda j: (KIND_RANK[j.kind], self.block_rank[j.block], j.order))
            self.running.add(job.id)
            return job, False

    def _worker(self) -> None:
        while True:
            wait = self.pause_until - time.time()
            if wait > 0:
                time.sleep(min(wait, 30))
                continue
            job, finished = self._next()
            if finished:
                return
            if job is None:
                time.sleep(5)
                continue
            try:
                RUNNERS[job.kind](job)
            except InfraError as e:
                with self.lock:
                    self.pause_until = time.time() + self.backoff
                    log(f"infra error in {job.id}: {e}; pausing {self.backoff:.0f}s")
                    self.backoff = min(self.backoff * 2, 1800)
                    self.running.discard(job.id)
                job.attempt += 1
                _mark(job, "infra", str(e))
                continue
            except BudgetExhausted as e:
                with self.lock:
                    self.stop_reason = f"budget: {e}"
                    self.running.discard(job.id)
                log(f"budget cap reached in {job.id}: {e}")
                _mark(job, "budget", str(e))
                continue
            except Exception as e:  # noqa: BLE001 - a broken job must not stop the others
                tb = traceback.format_exc()
                with self.lock:
                    self.failures[job.id] = self.failures.get(job.id, 0) + 1
                    self.running.discard(job.id)
                job.attempt += 1
                log(f"job {job.id} failed: {e!r}")
                _mark(job, "error", tb)
                continue
            with self.lock:
                self.done.add(job.id)
                self.running.discard(job.id)
                self.backoff = 60.0
            _mark(job, "done")
            log(f"done {job.id} ({len(self.done)}/{len(self.jobs)}; "
                f"ledger {ledger().total():.2f} USD)")

    def run(self) -> str:
        threads = [threading.Thread(target=self._worker, daemon=True)
                   for _ in range(self.parallel)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        left = [j.id for j in self.jobs.values() if j.id not in self.done]
        return (f"done {len(self.done)}/{len(self.jobs)} jobs; ledger "
                f"{ledger().total():.2f} USD; stop: {self.stop_reason or 'none'}; "
                f"left {len(left)}")


# ---------------------------------------------------------------- plan after feasibility

# Sonnet 5.5 unit costs from the first experiment (USD per session) and its C1 cost there.
SONNET_PROBE, SONNET_ITEM, SONNET_C1 = 0.075, 0.060, 0.0698
DEBUG_MARGIN = 1.15
PLAN_MARGIN = 1.2


def unit_costs() -> dict[str, dict]:
    """Per-model unit costs measured in the feasibility phase."""
    rows = [r for r in read_csv(DATA / "sessions.csv") if r["block"] == "feas"]
    out = {}
    for m in settings()["models"]:
        n = short(m)
        probe_jobs: dict[str, float] = {}
        for r in rows:
            if r["model"] == n and r["kind"] == "feas_probe":
                probe_jobs[r["job"]] = probe_jobs.get(r["job"], 0.0) + float(r["cost_usd"])
        maint = [float(r["cost_usd"]) for r in rows
                 if r["model"] == n and r["kind"] == "feas_maint"]
        if not probe_jobs:
            continue
        c1 = fmean(probe_jobs.values())
        out[m] = {"c1": c1, "probe": c1 * SONNET_PROBE / SONNET_C1,
                  "item": c1 * SONNET_ITEM / SONNET_C1,
                  "maint": fmean(maint) if maint else c1 * 1.5}
    return out


def projected(jobs: list[Job], units: dict) -> float:
    total = 0.0
    for j in jobs:
        u = units[j.model]
        if j.kind == "probe":
            total += u["probe"] * DEBUG_MARGIN
        elif j.kind == "maint":
            total += 2 * u["maint"]
        elif j.kind == "produce":
            total += settings()["producer_k"] * u["item"] * DEBUG_MARGIN
    return total


def make_plan() -> dict:
    s = settings()
    # units.json, when present, holds the feasibility unit costs after reconciliation
    # (maintenance sessions stopped by the old guard are counted at the new guard)
    path = DATA / "units.json"
    units = json.loads(path.read_text()) if path.exists() else unit_costs()
    spent = ledger().total()
    budget = s["total_cap_usd"] - spent
    included, rows, seen = [], [], set()
    for block in s["blocks"]["order"]:
        trial = main_jobs(included + [block])
        new = [j for j in trial if j.id not in seen and j.block == block]
        measured = all(j.model in units for j in new)
        cost = projected(new, units) if measured else float("inf")
        prev = sum(r["projected_usd"] for r in rows if r["included"])
        ok = measured and (prev + cost) * PLAN_MARGIN <= budget
        rows.append({"block": block, "jobs": len(new), "projected_usd": cost, "included": ok})
        if ok:
            included.append(block)
            seen |= {j.id for j in trial}
    plan = {"generated_at": now(), "spent_before_usd": spent, "cap_usd": s["total_cap_usd"],
            "plan_margin": PLAN_MARGIN, "debug_margin": DEBUG_MARGIN, "units": units,
            "blocks": rows, "included": included,
            "block_limits": {r["block"]: 1.5 * r["projected_usd"] for r in rows if r["included"]}}
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    return plan


# ---------------------------------------------------------------- commands

def _write_meta(extra: dict) -> None:
    s = settings()
    path = DATA / "run.json"
    meta = json.loads(path.read_text()) if path.exists() else {}
    meta.update({
        "settings": s, "experiment_rules": {"max_debug": max_debug()},
        "thresholds": config.thresholds(),
        "prices": {m: real_run.price_table()[m] for m in s["models"]},
        "prices_source": "config/prices.toml", "cli_version": real_run._cli_version(),
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=config.ROOT,
                                     capture_output=True, text=True).stdout.strip(),
    })
    meta.setdefault("runs", []).append({"t": now(), **extra})
    DATA.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")


def cmd_feasibility(parallel: int) -> str:
    models = list(settings()["models"])
    _write_meta({"command": "feasibility", "models": models})
    out = Scheduler(feasibility_jobs(models), parallel, deadline_h=2).run()
    return out + "\n" + json.dumps(unit_costs(), indent=2)


def cmd_run(parallel: int, deadline_h: float) -> str:
    plan = json.loads((DATA / "plan.json").read_text())
    jobs = main_jobs(plan["included"])
    _write_meta({"command": "run", "blocks": plan["included"], "jobs": len(jobs)})
    return Scheduler(jobs, parallel, deadline_h, plan["block_limits"]).run()


def cmd_status() -> str:
    plan_path = DATA / "plan.json"
    lines = [f"ledger {ledger().total():.2f} USD of {settings()['total_cap_usd']:.0f}",
             "spend by block: " + ", ".join(f"{b or '-'} {v:.2f}"
                                            for b, v in sorted(spend_by_block().items()))]
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())
        jobs = main_jobs(plan["included"])
        done = _done_ids()
        for block in plan["included"]:
            bj = [j for j in jobs if j.block == block]
            lines.append(f"{block}: {sum(j.id in done for j in bj)}/{len(bj)} jobs done")
    return "\n".join(lines)


def cmd_archive() -> str:
    """Bundle every state repository and pack transcripts, ledger and job log."""
    import tarfile
    out = config.ROOT / "snapshots" / "capability"
    out.mkdir(parents=True, exist_ok=True)
    names = []
    for repo in sorted((root() / "store").glob("*.git")):
        bundle = out / (repo.name[:-4] + ".bundle")
        subprocess.run(["git", "bundle", "create", str(bundle), "--all"], cwd=repo,
                       capture_output=True, check=True)
        subprocess.run(["git", "bundle", "verify", str(bundle)], cwd=repo, capture_output=True,
                       check=True)
        names.append(bundle.name)
    with tarfile.open(out / "logs.tar.xz", "w:xz") as tar:
        for f in sorted((root() / "transcripts").glob("*.jsonl")):
            tar.add(f, arcname=f"transcripts/{f.name}")
        for name in ("ledger.jsonl", "jobs.jsonl", "run.log"):
            if (root() / name).exists():
                tar.add(root() / name, arcname=name)
    return f"{len(names)} bundles and logs.tar.xz in {out.relative_to(config.ROOT)}/"


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="harness capability")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    p_f = sub.add_parser("feasibility")
    p_f.add_argument("--parallel", type=int, default=None)
    sub.add_parser("plan")
    p_r = sub.add_parser("run")
    p_r.add_argument("--parallel", type=int, default=None)
    p_r.add_argument("--deadline-h", type=float, default=10.0)
    sub.add_parser("status")
    sub.add_parser("archive")
    sub.add_parser("report")
    args = ap.parse_args(argv)
    root().mkdir(parents=True, exist_ok=True)
    parallel = getattr(args, "parallel", None) or settings()["parallel"]
    if args.cmd == "prepare":
        print(prepare())
    elif args.cmd == "feasibility":
        print(cmd_feasibility(parallel))
    elif args.cmd == "plan":
        print(json.dumps(make_plan(), indent=2))
    elif args.cmd == "run":
        print(cmd_run(parallel, args.deadline_h))
    elif args.cmd == "status":
        print(cmd_status())
    elif args.cmd == "archive":
        print(cmd_archive())
    elif args.cmd == "report":
        from . import capability_report
        print(capability_report.build())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
