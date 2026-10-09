"""Build docs/methodology.html from docs/methodology_template.html.

Every number on the page is computed here from the committed logs, so the page can be
rebuilt after any run. The template holds the text; placeholders look like {{name}}.
"""
from __future__ import annotations

import math
import random
import re
from collections import defaultdict
from statistics import fmean

from . import config, stats

TEMPLATE = config.ROOT / "docs" / "methodology_template.html"
OUTPUT = config.ROOT / "docs" / "methodology.html"
DATASETS = {"strong": ("sim", "strong"), "weak": ("sim", "weak"), "real": ("real", "real")}
COLORS = {"strong": "#B8860B", "weak": "#8E8E93", "real": "#2E8B57"}
BOOT = 2000


def _ols(xs: list[float], ys: list[float]) -> tuple[float, float]:
    mx, my = fmean(xs), fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b


def _item_costs(run: dict) -> dict[str, float]:
    cost: dict[str, float] = defaultdict(float)
    for t in run["tasks"]:
        if t["task_type"] in ("impl", "debug"):
            cost[t["item"]] += t["cost_usd"]
    return cost


def _quantile(sorted_vals: list[float], q: float) -> float:
    return sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))]


def payback_weeks(beta: float, mc: float, v: float, r: float | None) -> float:
    """Horizon T (weeks) where Q(T) = 1. r = maintenance runs per week; None = one reset."""
    if beta <= 0:
        return math.inf
    if r is None:
        return math.sqrt(4 * mc / beta) / v
    a, b, c = beta * v * v, -2 * r * mc, -2 * mc
    return (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)


def q_of_t(beta: float, mc: float, v: float, r: float, t: float) -> float:
    return 2 * (r * t + 1) * mc / (beta * (v * t) ** 2) if beta > 0 else math.inf


def estimate(key: str) -> dict:
    phase, hyp = DATASETS[key]
    data = stats.load(phase, hyp)
    runs = stats.runs_of(data)
    weeks = data["meta"]["experiment"]["weeks"]
    pts = []
    for (g, _r), run in runs.items():
        if g == "nomaint":
            pts += [(int(item[1:]), c) for item, c in _item_costs(run).items()]
    c0, slope = _ols([p[0] for p in pts], [p[1] for p in pts])
    rng = random.Random(7)
    boots = []
    for _ in range(BOOT):
        s = [pts[rng.randrange(len(pts))] for _ in pts]
        a, b = _ols([p[0] for p in s], [p[1] for p in s])
        boots.append(b / a)
    boots.sort()
    maint = [t["cost_usd"] for (g, _r), run in runs.items() if g == "maint"
             for t in run["tasks"] if t["task_type"].startswith("maint_")]
    n_maint_series = len({r for (g, r) in runs if g == "maint"})
    summ = stats.summarize(data)
    beta = slope / c0
    R = len(maint) / n_maint_series
    m = fmean(maint)
    mc = m / c0
    n0 = summ["nomaint"]["cum_completed"]["mean"]
    nm = summ["maint"]["cum_completed"]["mean"]
    v, r = n0 / weeks, R / weeks
    out = {
        "n_points": len(pts), "c0": c0, "slope": slope, "beta": beta,
        "beta_lo": _quantile(boots, 0.05), "beta_hi": _quantile(boots, 0.95),
        "R": R, "m": m, "mc": mc, "N0": n0, "NM": nm, "delta": nm - n0, "v": v, "r": r,
        "Q_obs": 2 * (R + 1) * mc / (beta * n0 * n0) if beta > 0 else math.inf,
        "Q_one": 4 * mc / (beta * n0 * n0) if beta > 0 else math.inf,
        "T_obs": payback_weeks(beta, mc, v, r), "T_one": payback_weeks(beta, mc, v, None),
        "T_obs_hi": payback_weeks(_quantile(boots, 0.95), mc, v, r),
        "cum0": summ["nomaint"]["cum_completed_values"],
        "cumM": summ["maint"]["cum_completed_values"],
    }
    # end-of-run metrics and unused budget share per group
    for g in ("nomaint", "maint"):
        ends = [next(m_ for m_ in run["metrics"] if m_["point"] == "end" and m_["week"] == weeks)
                for (gg, _r), run in runs.items() if gg == g]
        out[f"{g}_cov"] = (min(e["coverage"] for e in ends), max(e["coverage"] for e in ends))
        out[f"{g}_maxfile"] = (min(e["max_file_lines"] for e in ends),
                               max(e["max_file_lines"] for e in ends))
        out[f"{g}_loc"] = (min(e["loc"] for e in ends), max(e["loc"] for e in ends))
        shares = [sum(w["unused_usd"] for w in run["weeks"])
                  / sum(w["available_usd"] for w in run["weeks"])
                  for (gg, _r), run in runs.items() if gg == g]
        out[f"{g}_unused"] = (min(shares), max(shares))
    if key == "real":
        cost = defaultdict(dict)
        for (g, rep), run in runs.items():
            for item, c in _item_costs(run).items():
                cost[(g, item)][rep] = c
        n_reps = len({rep for (_g, rep) in runs})
        items = {i for (_g, i) in list(cost)}
        both = sorted((i for i in items if len(cost.get(("nomaint", i), {})) == n_reps
                       and len(cost.get(("maint", i), {})) == n_reps), key=lambda i: int(i[1:]))
        ratios = [fmean(cost[("maint", i)].values()) / fmean(cost[("nomaint", i)].values())
                  for i in both]
        bs = sorted(fmean(ratios[rng.randrange(len(ratios))] for _ in ratios)
                    for _ in range(BOOT))
        out.update(paired_n=len(both), paired_first=both[0], paired_last=both[-1],
                   paired=fmean(ratios), paired_lo=_quantile(bs, 0.05),
                   paired_hi=_quantile(bs, 0.95))
        sessions = [t for run in runs.values() for t in run["tasks"]]
        out["sessions"] = len(sessions)
        out["failed"] = sum(1 for t in sessions if not t["accepted"])
        out["debug"] = sum(1 for t in sessions if t["task_type"] == "debug")
        xs, ys = [], []
        for (g, _r), run in runs.items():
            if g == "nomaint":
                for item, c in _item_costs(run).items():
                    xs.append(int(item[1:]))
                    ys.append(c)
        out["corr_index_cost"] = stats.pearson(xs, ys)
    return out


def online_rule(beta: float, c0: float, per_type: bool) -> list[dict]:
    """Corollary 6 applied to every maintenance task of the real maint group.

    k = accepted items since the previous accepted maintenance (of the same type when
    per_type is True); n_rem = items the series actually completed after the task.
    """
    data = stats.load(*DATASETS["real"])
    events = []
    for (g, rep), run in sorted(stats.runs_of(data).items()):
        if g != "maint":
            continue
        tasks = sorted(run["tasks"], key=lambda t: (t["week"], t["seq"]))
        done, last = 0, {}
        for i, t in enumerate(tasks):
            if t["task_type"] == "impl" and t["accepted"]:
                done += 1
            elif t["task_type"].startswith("maint_"):
                key = t["task_type"] if per_type else "any"
                k = done - last.get(key, 0)
                n_rem = sum(1 for u in tasks[i + 1:] if u["task_type"] == "impl" and u["accepted"])
                mc = t["cost_usd"] / c0
                events.append({"rep": rep, "week": t["week"], "type": t["task_type"], "k": k,
                               "n_rem": n_rem, "score": beta * k * n_rem, "mc": mc,
                               "worth": beta * k * n_rem > mc})
                if t["accepted"]:
                    last[key] = done
    return events


def payback_chart(est: dict, labels: dict) -> str:
    """Inline SVG: Q(T) per dataset for the observed policy, log scale, Q = 1 is break-even."""
    W, H = 720, 320
    ml, mr, mt, mb = 56, 150, 16, 40
    t_min, t_max = 2, 24
    y_min, y_max = 0.1, 20.0
    X = lambda t: ml + (t - t_min) / (t_max - t_min) * (W - ml - mr)
    Y = lambda q: mt + (math.log10(y_max) - math.log10(q)) / (
        math.log10(y_max) - math.log10(y_min)) * (H - mt - mb)
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{labels["aria"]}">']
    for q in (0.1, 0.2, 0.5, 1, 2, 5, 10, 20):
        cls = "axis-strong" if q == 1 else "grid"
        parts.append(f'<line class="{cls}" x1="{ml}" x2="{W - mr}" y1="{Y(q):.1f}" y2="{Y(q):.1f}"/>')
        parts.append(f'<text x="{ml - 6}" y="{Y(q) + 4:.1f}" text-anchor="end">{q:g}</text>')
    for t in range(t_min, t_max + 1, 2):
        parts.append(f'<text x="{X(t):.1f}" y="{H - mb + 16}" text-anchor="middle">{t}</text>')
    parts.append(f'<line class="mark" x1="{X(8):.1f}" x2="{X(8):.1f}" y1="{mt}" y2="{H - mb}"/>')
    parts.append(f'<text x="{X(8) + 4:.1f}" y="{mt + 12}">{labels["horizon"]}</text>')
    parts.append(f'<text x="{(ml + W - mr) / 2:.1f}" y="{H - 6}" text-anchor="middle">{labels["x"]}</text>')
    parts.append(f'<text x="{W - mr + 4}" y="{Y(1) + 4:.1f}">{labels["breakeven"]}</text>')
    legend_y = mt + 40
    for key in ("strong", "weak", "real"):
        e = est[key]
        pts = []
        t = t_min
        while t <= t_max + 1e-9:
            q = q_of_t(e["beta"], e["mc"], e["v"], e["r"], t)
            if y_min <= q <= y_max:
                pts.append(f"{X(t):.1f},{Y(q):.1f}")
            t += 0.25
        dash = ' stroke-dasharray="6 4"' if key == "real" else ""
        parts.append(f'<polyline fill="none" stroke="{COLORS[key]}" stroke-width="2.2"{dash} points="{" ".join(pts)}"/>')
        q8 = q_of_t(e["beta"], e["mc"], e["v"], e["r"], 8)
        parts.append(f'<circle cx="{X(8):.1f}" cy="{Y(q8):.1f}" r="4" fill="{COLORS[key]}"/>')
        parts.append(f'<line x1="{W - mr + 8}" x2="{W - mr + 30}" y1="{legend_y}" y2="{legend_y}" stroke="{COLORS[key]}" stroke-width="2.2"{dash}/>')
        parts.append(f'<text x="{W - mr + 34}" y="{legend_y + 4}">{labels[key]}</text>')
        legend_y += 20
    parts.append("</svg>")
    return "\n".join(parts)


def _fmt(v, nd=2):
    if isinstance(v, float) and math.isinf(v):
        return "∞"
    return f"{v:.{nd}f}"


def values() -> dict[str, str]:
    est = {k: estimate(k) for k in DATASETS}
    out: dict[str, str] = {}
    for k, e in est.items():
        out.update({
            f"{k}.c0": _fmt(e["c0"], 4 if k == "real" else 3),
            f"{k}.beta": _fmt(100 * e["beta"], 2), f"{k}.beta_lo": _fmt(100 * e["beta_lo"], 2),
            f"{k}.beta_hi": _fmt(100 * e["beta_hi"], 2), f"{k}.R": _fmt(e["R"], 1),
            f"{k}.m": _fmt(e["m"], 3), f"{k}.mc": _fmt(e["mc"], 2), f"{k}.N0": _fmt(e["N0"], 1),
            f"{k}.NM": _fmt(e["NM"], 1), f"{k}.delta": f"{e['delta']:+.1f}",
            f"{k}.delta_abs": _fmt(abs(e["delta"]), 1),
            f"{k}.v": _fmt(e["v"], 2), f"{k}.Q_obs": _fmt(e["Q_obs"], 2),
            f"{k}.Q_one": _fmt(e["Q_one"], 2), f"{k}.T_obs": _fmt(e["T_obs"], 1),
            f"{k}.T_one": _fmt(e["T_one"], 1), f"{k}.T_obs_hi": _fmt(e["T_obs_hi"], 1),
            f"{k}.n_points": str(e["n_points"]),
            f"{k}.beta_star_one": _fmt(100 * 4 * e["mc"] / e["N0"] ** 2, 2),
            f"{k}.beta_star_obs": _fmt(100 * 2 * (e["R"] + 1) * e["mc"] / e["N0"] ** 2, 2),
            f"{k}.cum0": ", ".join(str(x) for x in e["cum0"]),
            f"{k}.cumM": ", ".join(str(x) for x in e["cumM"]),
        })
    r = est["real"]
    out.update({
        "real.paired": _fmt(r["paired"], 3), "real.paired_lo": _fmt(r["paired_lo"], 3),
        "real.paired_hi": _fmt(r["paired_hi"], 3), "real.paired_n": str(r["paired_n"]),
        "real.paired_range": f"{r['paired_first']}–{r['paired_last']}",
        "real.sessions": str(r["sessions"]), "real.failed": str(r["failed"]),
        "real.debug": str(r["debug"]), "real.corr_index_cost": _fmt(r["corr_index_cost"], 2),
    })
    for g in ("nomaint", "maint"):
        lo, hi = r[f"{g}_cov"]
        out[f"real.{g}_cov"] = f"{100 * lo:.0f}–{100 * hi:.0f}%"
        lo, hi = r[f"{g}_maxfile"]
        out[f"real.{g}_maxfile"] = f"{lo}–{hi}"
        lo, hi = r[f"{g}_loc"]
        out[f"real.{g}_loc"] = f"{lo}–{hi}"
        lo, hi = r[f"{g}_unused"]
        out[f"real.{g}_unused"] = f"{100 * lo:.0f}–{100 * hi:.0f}%"
    out["real.baseline_loc"] = str(stats.load("real", "real")["meta"]["plan"]["baseline"]["loc"])
    out["real.L_star"] = _fmt(math.sqrt(2 * r["mc"] / r["beta"]), 1)
    out["real.single_premium"] = _fmt(100 * (r["beta"] * r["N0"] / 4 + r["mc"] / r["N0"]), 1)
    out["real.quad_share"] = _fmt(100 * (r["beta"] * r["N0"] / 2), 1)
    for name, beta, per_type in (("single", r["beta"], False), ("type", r["beta"], True),
                                 ("type_hi", r["beta_hi"], True)):
        ev = online_rule(beta, r["c0"], per_type)
        out[f"real.online_{name}_n"] = str(len(ev))
        out[f"real.online_{name}_worth"] = str(sum(e_["worth"] for e_ in ev))
        out[f"real.online_{name}_max"] = _fmt(max(e_["score"] / e_["mc"] for e_ in ev), 2)
        if name == "type":
            out["_online_rows"] = ev  # type: ignore[assignment]
    out["_est"] = est  # type: ignore[assignment]
    return out


def build() -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    vals = values()
    est = vals.pop("_est")  # type: ignore[arg-type]
    chart_labels = dict(re.findall(r'data-label-(\w+)="([^"]*)"',
                                   re.search(r'<div id="chart-labels"[^>]*>', text).group(0)))
    vals["chart.payback"] = payback_chart(est, chart_labels)
    rows = []
    for e_ in vals.pop("_online_rows"):  # type: ignore[union-attr]
        verdict = chart_labels["yes"] if e_["worth"] else chart_labels["no"]
        rows.append(f"<tr><td>{e_['rep']}</td><td>{e_['week']}</td>"
                    f"<td>{chart_labels[e_['type']]}</td><td>{e_['k']}</td><td>{e_['n_rem']}</td>"
                    f"<td>{e_['score']:.2f}</td><td>{e_['mc']:.2f}</td><td>{verdict}</td></tr>")
    vals["real.online_rows"] = "\n".join(rows)

    def repl(m):
        key = m.group(1)
        if key not in vals:
            raise KeyError(f"unknown placeholder {{{{{key}}}}} in {TEMPLATE.name}")
        return vals[key]

    html = re.sub(r"\{\{([\w.]+)\}\}", repl, text)
    OUTPUT.write_text(html, encoding="utf-8")
    return f"wrote {OUTPUT.relative_to(config.ROOT)} ({len(html) // 1024} KiB)"
