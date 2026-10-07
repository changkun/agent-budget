"""Build REPORT.md: generated tables inserted into docs/report_template.md."""
from __future__ import annotations

import json
import math
import re
from statistics import fmean

from . import config, stats

TEMPLATE = config.ROOT / "docs" / "report_template.md"
OUTPUT = config.ROOT / "REPORT.md"


def _labels() -> dict:
    with open(config.ROOT / "harness" / "labels_zh.json", encoding="utf-8") as f:
        return json.load(f)


def _f(v, nd=2, L=None):
    if v is None:
        return "–"
    if v == math.inf:
        return L["report"]["inf"] if L else "∞"
    if isinstance(v, int):
        return str(v)
    return f"{v:.{nd}f}"


def _table(cols: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def dataset_section(phase: str, hyp: str) -> str:
    L = _labels()
    R = L["report"]
    data = stats.load(phase, hyp)
    exp = data["meta"]["experiment"]
    runs = stats.runs_of(data)
    groups = exp["groups"]
    reps = sorted({r for (_g, r) in runs})
    gname = L["group_names"]
    parts = []

    for g in groups:
        series = [stats.weekly_series(runs[(g, r)]) for r in reps if (g, r) in runs]
        rows = []
        for w in range(1, exp["weeks"] + 1):
            pick = [s[w - 1] for s in series if len(s) >= w]
            def mean_of(key):
                vals = [p[key] for p in pick if p[key] is not None]
                return fmean(vals) if vals else None
            rows.append([w, _f(mean_of("completed"), 2), _f(mean_of("cost_per_item"), 3),
                         _f(mean_of("avg_input_tokens_week"), 0), _f(mean_of("avg_debug"), 2),
                         _f(None if mean_of("maint_share") is None else 100 * mean_of("maint_share"), 1) + "%"])
        parts.append(f"#### {R['weekly_title'].format(group=gname[g])}\n\n"
                     + _table(R["weekly_cols"], rows))

    summ = stats.summarize(data)
    rep_cols = [R["rep_col"].format(rep=r) for r in reps]
    rows = []
    for g in groups:
        s = summ[g]
        sp = s["cum_completed"]
        rows.append([gname[g], *s["cum_completed_values"], _f(sp["mean"], 1),
                     f"{_f(sp['min'], 0)}–{_f(sp['max'], 0)}"])
    parts.append(f"#### {R['cum_title']}\n\n"
                 + _table([R["group_col"], *rep_cols, R["mean_col"], R["range_col"]], rows))

    rows = []
    for g in groups:
        s = summ[g]
        sp = s["ratio"]
        rng = f"{_f(sp['min'])}–{_f(sp['max'])}" if sp["min"] is not None else "–"
        rows.append([gname[g], *[_f(v, 2, L) for v in s["ratio_values"]], _f(sp["mean"]), rng])
    parts.append(f"#### {R['ratio_title']}\n\n"
                 + _table([R["group_col"], *rep_cols, R["mean_col"], R["range_col"]], rows))

    rows = []
    for g in groups:
        for m, c in stats.correlations(runs, g).items():
            rows.append([gname[g], L["metric_names"].get(m, m), c["n"], _f(c["pearson"]),
                         _f(c["spearman"])])
    parts.append(f"#### {R['corr_title']}\n\n" + _table(R["corr_cols"], rows))

    rows = []
    for g in groups:
        s = summ[g]
        n = sum(len(stats.weekly_series(runs[(g, r)])) for r in reps if (g, r) in runs)
        rows.append([gname[g], _f(s["forecast_bias"]), _f(s["forecast_mae"]), n])
    parts.append(f"#### {R['forecast_title']}\n\n" + _table(R["forecast_cols"], rows))

    rows = []
    for g in groups:
        s = summ[g]
        maint = [t for (gg, r), run in runs.items() if gg == g for t in run["tasks"]
                 if t["task_type"].startswith("maint_")]
        rows.append([gname[g], s["item_overspends"], s["week_overspends"],
                     _f(100 * s["maint_share"], 1) + "%", len(maint),
                     sum(1 for t in maint if t["rolled_back"])])
    parts.append(f"#### {R['overspend_title']}\n\n" + _table(R["overspend_cols"], rows))

    plan = data["meta"]["plan"]
    head = (f"budget/week = {plan['budget']:.3f} USD; item cap = {plan['cap']:.3f} USD; "
            f"calibration mean = {plan['calib_mean']:.3f} USD (n = {len(plan['calib_costs'])})")
    return f"`{head}`\n\n" + "\n\n".join(parts)


def build() -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    available = set(stats.available_datasets())

    def repl(m):
        phase, hyp = m.group(1), m.group(2)
        if (phase, hyp) not in available:
            return "_(no data)_"
        return dataset_section(phase, hyp)

    text = re.sub(r"\{\{TABLES:(\w+)/(\w+)\}\}", repl, text)
    OUTPUT.write_text(text, encoding="utf-8")
    return f"wrote {OUTPUT.relative_to(config.ROOT)}"
