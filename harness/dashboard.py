"""Build docs/index.html: one self-contained page, data embedded, no external resources.

All numbers are computed here; the page only filters and draws. User-facing text comes
from labels_zh.json.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import fmean

from . import config, stats

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "dashboard_template.html"
LABELS = HERE / "labels_zh.json"
OUTPUT = config.ROOT / "docs" / "index.html"

SPEND_SEGMENTS = ("impl", "debug", "maint_security", "maint_tests", "maint_refactor",
                  "maint_knowledge", "unused")
METRICS = ("loc", "max_file_lines", "dup_ratio", "coverage", "vulns", "outdated_deps",
           "avg_input_tokens", "build_tests")
METRIC_AGENT = {"vulns": "security", "coverage": "tests", "dup_ratio": "refactor",
                "max_file_lines": "refactor", "avg_input_tokens": "knowledge"}
# A late/early ratio within this band counts as "flat" in the generated sentence.
TREND_BAND = (0.9, 1.1)


def _labels() -> dict:
    with open(LABELS, encoding="utf-8") as f:
        return json.load(f)


def _clean(v):
    """JSON-safe numbers: inf/nan become None."""
    if isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
        return None
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def _band(values: list) -> dict:
    vals = [v for v in values if v is not None]
    if not vals:
        return {"mean": None, "min": None, "max": None, "values": values}
    return {"mean": fmean(vals), "min": min(vals), "max": max(vals), "values": values}


def _thresholds(meta: dict) -> dict:
    thr, base = meta["thresholds"], meta["plan"]["baseline"]
    return {
        "vulns": thr["security"]["vulns_gt"],
        "coverage": base["coverage"] * (1 - thr["tests"]["coverage_rel_drop_gt"]),
        "dup_ratio": base["dup_ratio"] * (1 + thr["refactor"]["dup_rel_rise_gt"]),
        "max_file_lines": base["max_file_lines"] * (1 + thr["refactor"]["max_file_rel_rise_gt"]),
        "avg_input_tokens": base["avg_input_tokens"]
        * (1 + thr["knowledge"]["avg_input_tokens_rel_rise_gt"]),
    }


def _metric_value(row: dict, metric: str):
    if metric == "build_tests":
        if row.get("build_ok") is None or row.get("tests_ok") is None:
            return None
        return min(row["build_ok"], row["tests_ok"])
    return row.get(metric)


def _conclusion(L: dict, hyp_name: str, summ: dict, reps: list[int], all_reps: bool) -> str:
    c = L["conclusion"]
    a = summ["nomaint"]["cum_completed"]["mean"]
    b = summ["maint"]["cum_completed"]["mean"]
    r1 = summ["nomaint"]["ratio"]["mean"]
    r2 = summ["maint"]["ratio"]["mean"]
    if r1 is None:
        trend = c["trend_none"]
    elif r1 > TREND_BAND[1]:
        trend = c["trend_up"]
    elif r1 < TREND_BAND[0]:
        trend = c["trend_down"]
    else:
        trend = c["trend_flat"]
    if a is None or b is None or abs(a - b) < 1e-9:
        verdict = c["verdict_equal"]
    else:
        verdict = c["verdict_more"] if b > a else c["verdict_less"]
    scope = (c["scope_all"].format(n=len(reps)) if all_reps
             else c["scope_one"].format(rep=reps[0]))

    def num(v, nd):
        return "–" if v is None else f"{v:.{nd}f}"

    return c["template"].format(hyp=hyp_name, a=num(a, 1), b=num(b, 1), scope=scope,
                                r1=num(r1, 2), r2=num(r2, 2), trend=trend, verdict=verdict)


def _view(data: dict, reps: list[int], all_reps: bool, L: dict, hyp_name: str) -> dict:
    meta = data["meta"]
    exp = meta["experiment"]
    groups = exp["groups"]
    runs = stats.runs_of(data)
    summ = stats.summarize(data, reps)
    weeks = list(range(1, exp["weeks"] + 1))

    cost, cum, spend, forecast = {}, {}, {}, {}
    metrics = {m: {"groups": {}, "trig": {}} for m in METRICS}
    thr = _thresholds(meta)
    for g in groups:
        series = {rep: {s["week"]: s for s in stats.weekly_series(runs[(g, rep)])}
                  for rep in reps if (g, rep) in runs}
        wrows = {rep: {w["week"]: w for w in runs[(g, rep)]["weeks"]}
                 for rep in reps if (g, rep) in runs}
        cost[g] = [{"week": w, **_band([series[r].get(w, {}).get("cost_per_item")
                                        for r in series])} for w in weeks]
        cum[g] = [{"week": w, **_band([series[r].get(w, {}).get("cum_completed")
                                       for r in series])} for w in weeks]
        forecast[g] = [{
            "week": w,
            "predicted": _band([series[r].get(w, {}).get("predicted") for r in series]),
            "actual": _band([series[r].get(w, {}).get("completed") for r in series]),
        } for w in weeks]
        spend[g] = []
        for w in weeks:
            rows = [wrows[r][w] for r in wrows if w in wrows[r]]
            if not rows:
                spend[g].append({"week": w})
                continue
            seg = {
                "impl": fmean(x["spend_impl"] for x in rows),
                "debug": fmean(x["spend_debug"] for x in rows),
                "maint_security": fmean(x["spend_maint_security"] for x in rows),
                "maint_tests": fmean(x["spend_maint_tests"] for x in rows),
                "maint_refactor": fmean(x["spend_maint_refactor"] for x in rows),
                "maint_knowledge": fmean(x["spend_maint_knowledge"] for x in rows),
                "unused": fmean(x["unused_usd"] for x in rows),
                "overspend": fmean(x["week_overspend_usd"] for x in rows),
                "budget": fmean(x["budget_usd"] for x in rows),
                "available": fmean(x["available_usd"] for x in rows),
                "carry": fmean(x["carryover_in_usd"] for x in rows),
            }
            spend[g].append({"week": w, **seg})
        # metric series: week 0 baseline, then start-of-week values
        for m in METRICS:
            pts = []
            for w in [0, *weeks]:
                vals = []
                for r in reps:
                    if (g, r) not in runs:
                        continue
                    if w == 0:
                        row = next((x for x in runs[(g, r)]["metrics"]
                                    if x["week"] == 0 and x["point"] == "start"), None)
                    else:
                        row = wrows[r].get(w)
                    vals.append(_metric_value(row, m) if row else None)
                pts.append({"week": w, **_band(vals)})
            metrics[m]["groups"][g] = pts
        if g == "maint":
            for r in reps:
                if (g, r) not in runs:
                    continue
                for t in runs[(g, r)]["tasks"]:
                    if not t["task_type"].startswith("maint_") or not t["trigger_metric"]:
                        continue
                    for m in t["trigger_metric"].split(";"):
                        if m in metrics:
                            trig = metrics[m]["trig"]
                            trig[t["week"]] = trig.get(t["week"], 0) + 1
    for m in METRICS:
        metrics[m]["threshold"] = thr.get(m)
        metrics[m]["agent"] = METRIC_AGENT.get(m)

    headline = {g: {
        "cum": summ[g]["cum_completed"],
        "cum_values": summ[g]["cum_completed_values"],
        "ratio": summ[g]["ratio"],
        "ratio_values": summ[g]["ratio_values"],
        "item_overspends": summ[g]["item_overspends"],
        "week_overspends": summ[g]["week_overspends"],
    } for g in groups}
    return {
        "reps": reps,
        "headline": headline,
        "conclusion": _conclusion(L, hyp_name, summ, reps, all_reps),
        "cost": cost, "cum": cum, "spend": spend, "metrics": metrics, "forecast": forecast,
    }


def _dataset(phase: str, hyp: str, L: dict) -> dict:
    data = stats.load(phase, hyp)
    meta = data["meta"]
    exp = meta["experiment"]
    runs = stats.runs_of(data)
    reps = sorted({rep for (_g, rep) in runs})
    hyp_name = L["hypothesis_names"].get(hyp, hyp)
    views = {"all": _view(data, reps, True, L, hyp_name)}
    for r in reps:
        views[str(r)] = _view(data, [r], False, L, hyp_name)
    task_keys = ("week", "seq", "item", "task_type", "debug_index", "input_tokens",
                 "cache_write_tokens", "cache_read_tokens", "output_tokens", "cost_usd",
                 "accepted", "rolled_back", "item_cost_usd", "overspend_usd", "forced_stop",
                 "trigger_metric", "trigger_value", "trigger_baseline", "trigger_threshold")
    week_keys = ("week", "budget_usd", "carryover_in_usd", "available_usd", "spend_maint",
                 "spend_impl", "spend_debug", "unused_usd", "week_overspend_usd",
                 "predicted_items", "completed_items", "failed_items", "item_overspend_count",
                 "triggered", "maint_skipped")
    raw = defaultdict(dict)
    for (g, r), run in runs.items():
        raw[str(r)][g] = {
            "tasks": [{k: t.get(k) for k in task_keys} for t in run["tasks"]],
            "weeks": [{k: w.get(k) for k in week_keys} for w in run["weeks"]],
        }
    plan = meta["plan"]
    base = f"data/{phase}/{hyp}/"
    return {
        "phase": phase,
        "hypothesis": hyp,
        "reps": reps,
        "groups": exp["groups"],
        "weeks": exp["weeks"],
        "settings": {
            "budget": plan["budget"], "cap": plan["cap"], "maint_cap": plan["maint_cap"],
            "calib_mean": plan["calib_mean"], "calib_n": len(plan["calib_costs"]),
            "model": meta.get("model"), "prices": meta.get("prices"),
            "generated_at": meta.get("generated_at"), "git_commit": meta.get("git_commit"),
        },
        "views": views,
        "runs": raw,
        "links": {k: base + f for k, f in (("tasks", "tasks.csv"), ("weeks", "weeks.csv"),
                                           ("metrics", "metrics.csv"), ("run", "run.json"))},
    }


def build() -> str:
    L = _labels()
    datasets = {}
    for phase, hyp in stats.available_datasets():
        datasets[f"{phase}/{hyp}"] = _dataset(phase, hyp, L)
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "datasets": _clean(datasets),
    }
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("/*__LABELS__*/null", json.dumps(L, ensure_ascii=False))
    html = html.replace("/*__DATA__*/null",
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    return f"wrote {OUTPUT.relative_to(config.ROOT)} ({len(html) // 1024} KiB, " \
           f"{len(datasets)} datasets)"
