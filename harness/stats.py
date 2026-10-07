"""Summary statistics shared by the dashboard and the report.

Nothing here tests significance; it only describes the logged runs.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from statistics import fmean

from . import config
from .logs import read_csv

MAINT_AGENTS = ("security", "tests", "refactor", "knowledge")
CORR_METRICS = ("loc", "max_file_lines", "dup_ratio", "coverage", "vulns", "outdated_deps",
                "avg_input_tokens")
INT_FIELDS = {"rep", "week", "seq", "debug_index", "input_tokens", "cache_write_tokens",
              "cache_read_tokens", "output_tokens", "total_input_tokens", "accepted",
              "rolled_back", "forced_stop", "completed_items", "failed_items",
              "item_overspend_count", "vulns", "outdated_deps", "build_ok", "tests_ok", "loc",
              "max_file_lines"}
STR_FIELDS = {"phase", "hypothesis", "group", "item", "task_type", "trigger_metric",
              "trigger_value", "trigger_baseline", "trigger_threshold", "model", "session_id",
              "triggered", "maint_skipped", "point"}


def _convert(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if k in STR_FIELDS:
            out[k] = v
        elif v == "":
            out[k] = None
        elif k in INT_FIELDS:
            out[k] = int(float(v))
        else:
            out[k] = float(v)
    return out


def available_datasets() -> list[tuple[str, str]]:
    found = []
    for phase_dir in sorted(config.DATA_DIR.glob("*")):
        for hyp_dir in sorted(phase_dir.glob("*")):
            if (hyp_dir / "weeks.csv").exists() and (hyp_dir / "run.json").exists():
                found.append((phase_dir.name, hyp_dir.name))
    return found


def load(phase: str, hypothesis: str) -> dict:
    d = config.DATA_DIR / phase / hypothesis
    with open(d / "run.json", encoding="utf-8") as f:
        meta = json.load(f)
    return {
        "meta": meta,
        "tasks": [_convert(r) for r in read_csv(d / "tasks.csv")],
        "weeks": [_convert(r) for r in read_csv(d / "weeks.csv")],
        "metrics": [_convert(r) for r in read_csv(d / "metrics.csv")],
    }


def runs_of(data: dict) -> dict[tuple[str, int], dict]:
    """Group rows by (group, rep); calibration rows are excluded."""
    runs: dict[tuple[str, int], dict] = defaultdict(lambda: {"weeks": [], "tasks": [],
                                                             "metrics": []})
    for kind in ("weeks", "tasks", "metrics"):
        for r in data[kind]:
            if r["group"] == "calib":
                continue
            runs[(r["group"], r["rep"])][kind].append(r)
    for run in runs.values():
        run["weeks"].sort(key=lambda r: r["week"])
        run["tasks"].sort(key=lambda r: (r["week"], r["seq"]))
    return dict(runs)


def weekly_series(run: dict) -> list[dict]:
    """Per-week derived values for one run."""
    tasks_by_week = defaultdict(list)
    for t in run["tasks"]:
        tasks_by_week[t["week"]].append(t)
    out, cum = [], 0
    for w in run["weeks"]:
        ts = tasks_by_week[w["week"]]
        firsts = [t["total_input_tokens"] for t in ts if t["task_type"] == "impl"]
        items = defaultdict(int)
        for t in ts:
            if t["task_type"] in ("impl", "debug"):
                items[t["item"]] = max(items[t["item"]], t["debug_index"])
        total_spend = w["spend_maint"] + w["spend_implementation"]
        cum += w["completed_items"]
        out.append({
            "week": w["week"],
            "completed": w["completed_items"],
            "failed": w["failed_items"],
            "cum_completed": cum,
            "impl_spend": w["spend_implementation"],
            "cost_per_item": (w["spend_implementation"] / w["completed_items"]
                              if w["completed_items"] else None),
            "avg_input_tokens_week": fmean(firsts) if firsts else None,
            "avg_debug": fmean(items.values()) if items else None,
            "maint_share": w["spend_maint"] / total_spend if total_spend else 0.0,
            "spend_maint": w["spend_maint"],
            "predicted": w["predicted_items"],
            "forecast_error": w["predicted_items"] - w["completed_items"],
            "item_overspend_count": w["item_overspend_count"],
            "week_overspend": w["week_overspend_usd"],
        })
    return out


def period_cost(series: list[dict], weeks: list[int]) -> float | None:
    sel = [s for s in series if s["week"] in weeks]
    done = sum(s["completed"] for s in sel)
    spend = sum(s["impl_spend"] for s in sel)
    if done == 0:
        return math.inf if spend > 0 else None
    return spend / done


def late_early_ratio(series: list[dict], exp: dict) -> float | None:
    early = period_cost(series, exp["early_weeks"])
    late = period_cost(series, exp["late_weeks"])
    if early is None or late is None or early in (0, math.inf):
        return None
    return late / early


def _rank(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    mx, my = fmean(xs), fmean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def spearman(xs: list[float], ys: list[float]) -> float | None:
    return pearson(_rank(xs), _rank(ys)) if len(xs) >= 3 else None


def correlations(runs: dict, group: str) -> dict:
    """Metric at week start vs. that week's cost per completed item, pooled over reps."""
    pairs = defaultdict(lambda: ([], []))
    for (g, _rep), run in runs.items():
        if g != group:
            continue
        series = {s["week"]: s for s in weekly_series(run)}
        for w in run["weeks"]:
            cpi = series[w["week"]]["cost_per_item"]
            if cpi is None:
                continue
            for m in CORR_METRICS:
                if w.get(m) is not None:
                    pairs[m][0].append(float(w[m]))
                    pairs[m][1].append(cpi)
    return {m: {"n": len(xs), "pearson": pearson(xs, ys), "spearman": spearman(xs, ys)}
            for m, (xs, ys) in pairs.items()}


def spread(values: list[float | None]) -> dict:
    finite = [v for v in values if v is not None and v != math.inf]
    inf = sum(1 for v in values if v == math.inf)
    if not finite:
        return {"mean": None, "min": None, "max": None, "n": 0, "inf": inf}
    return {"mean": fmean(finite), "min": min(finite), "max": max(finite), "n": len(finite),
            "inf": inf}


def summarize(data: dict, reps: list[int] | None = None) -> dict:
    """Headline numbers per group over the selected reps."""
    exp = data["meta"]["experiment"]
    runs = runs_of(data)
    out = {}
    for group in exp["groups"]:
        sel = sorted(rep for (g, rep) in runs if g == group and (reps is None or rep in reps))
        series = {rep: weekly_series(runs[(group, rep)]) for rep in sel}
        cum = [s[-1]["cum_completed"] if s else 0 for s in series.values()]
        ratios = [late_early_ratio(s, exp) for s in series.values()]
        errs = [x["forecast_error"] for s in series.values() for x in s]
        out[group] = {
            "reps": sel,
            "cum_completed": spread(cum),
            "cum_completed_values": cum,
            "ratio": spread(ratios),
            "ratio_values": ratios,
            "item_overspends": sum(x["item_overspend_count"] for s in series.values()
                                   for x in s),
            "week_overspends": sum(1 for s in series.values() for x in s
                                   if x["week_overspend"] > 0),
            "forecast_bias": fmean(errs) if errs else None,
            "forecast_mae": fmean(abs(e) for e in errs) if errs else None,
            "maint_share": (sum(x["spend_maint"] for s in series.values() for x in s)
                            / max(1e-12, sum(x["spend_maint"] + x["impl_spend"]
                                             for s in series.values() for x in s))),
        }
    return out


def _fmt(v, nd=2):
    if v is None:
        return "–"
    if v == math.inf:
        return "∞"
    if isinstance(v, int):
        return str(v)
    return f"{v:.{nd}f}"


def markdown_summary(phase: str) -> str:
    """Tables used by REPORT.md. Labels are kept in English; the report text is Chinese."""
    lines = []
    for ph, hyp in available_datasets():
        if ph != phase:
            continue
        data = load(ph, hyp)
        exp = data["meta"]["experiment"]
        runs = runs_of(data)
        summ = summarize(data)
        plan = data["meta"]["plan"]
        lines.append(f"## {ph} / {hyp}\n")
        lines.append(f"budget/week = {plan['budget']:.3f} USD, item cap = {plan['cap']:.3f} USD, "
                     f"calibration mean = {plan['calib_mean']:.3f} USD "
                     f"(n = {len(plan['calib_costs'])})\n")
        lines.append("| group | cum. completed (per rep) | late/early cost ratio (per rep) "
                     "| item overspends | week overspends | forecast bias | forecast MAE "
                     "| maint share |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for g, s in summ.items():
            lines.append(
                f"| {g} | {', '.join(map(str, s['cum_completed_values']))} "
                f"| {', '.join(_fmt(r) for r in s['ratio_values'])} "
                f"| {s['item_overspends']} | {s['week_overspends']} "
                f"| {_fmt(s['forecast_bias'])} | {_fmt(s['forecast_mae'])} "
                f"| {_fmt(100 * s['maint_share'], 1)}% |")
        lines.append("")
        lines.append("| group | rep | week | completed | cost/item | avg input tokens "
                     "| avg debug | maint share | predicted |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for (g, rep) in sorted(runs):
            for s in weekly_series(runs[(g, rep)]):
                lines.append(
                    f"| {g} | {rep} | {s['week']} | {s['completed']} "
                    f"| {_fmt(s['cost_per_item'], 3)} "
                    f"| {_fmt(s['avg_input_tokens_week'], 0)} | {_fmt(s['avg_debug'])} "
                    f"| {_fmt(100 * s['maint_share'], 1)}% | {_fmt(s['predicted'], 1)} |")
        lines.append("")
        lines.append("| group | metric | n | pearson | spearman |")
        lines.append("|---|---|---|---|---|")
        for g in exp["groups"]:
            for m, c in correlations(runs, g).items():
                lines.append(f"| {g} | {m} | {c['n']} | {_fmt(c['pearson'])} "
                             f"| {_fmt(c['spearman'])} |")
        lines.append("")
    return "\n".join(lines)
