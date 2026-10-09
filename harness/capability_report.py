"""Tables and the figure for REPORT-capability.md, built from docs/data/capability/.

The report text lives in docs/report_capability_template.md; placeholders {{name}} are
replaced by the tables built here, so the report can be rebuilt after any run.
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from statistics import fmean

from . import capability_stats as cs
from .capability import DATA, settings, spend_by_block
from .config import ROOT
from .logs import read_csv

TEMPLATE = ROOT / "docs" / "report_capability_template.md"
OUTPUT = ROOT / "REPORT-capability.md"
FIG_DIR = ROOT / "docs" / "img" / "capability"
LABEL = {"haiku55": "Haiku 5.5", "sonnet55": "Sonnet 5.5", "opus55": "Opus 5.5",
         "fable51": "Fable 5.1"}
ORDER = ["haiku55", "sonnet55", "opus55", "fable51"]


def _pct(x: float | None, digits: int = 1) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    return f"{x * 100:+.{digits}f}%"


def _ci_pct(e: dict, key: str) -> str:
    return f"{_pct(e[key])} [{_pct(e[key + '_lo'])}, {_pct(e[key + '_hi'])}]"


def _beta(e: dict) -> str:
    def f(x):
        return "–" if x is None or math.isnan(x) else f"{x * 100:+.2f}"
    return f"{f(e['beta'])} [{f(e['beta_lo'])}, {f(e['beta_hi'])}]"


def _n(x: float | None) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    return "∞" if math.isinf(x) else f"{x:.0f}"


def _nstar(e: dict) -> str:
    return f"{_n(e['nstar'])} [{_n(e['nstar_lo'])}, {_n(e['nstar_hi'])}]"


def _usd(x: float | None, digits: int = 3) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "–"
    return f"{x:.{digits}f}"


def _table(head: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def _sorted(entries: list[dict], key: str = "consumer") -> list[dict]:
    return sorted(entries, key=lambda e: (ORDER.index(e[key]), e.get("k", 0)))


def tables(summary: dict) -> dict[str, str]:
    t: dict[str, str] = {}
    plan = json.loads((DATA / "plan.json").read_text())
    spend = spend_by_block()
    t["blocks"] = _table(
        ["块", "内容", "纳入", "估计（美元）", "实际（美元）"],
        [[r["block"], BLOCK_TEXT[r["block"]], "是" if r["included"] else "否",
          _usd(r["projected_usd"], 1), _usd(spend.get(r["block"], 0.0), 2)]
         for r in plan["blocks"]] +
        [["feas", "阶段 1 可行性", "是", "–", _usd(spend.get("feas", 0.0), 2)]])
    t["total_spend"] = f"{sum(spend.values()):.2f}"
    rows = read_csv(DATA / "sessions.csv")
    t["sessions"] = str(sum(r["block"] != "feas" for r in rows))
    t["sessions_all"] = str(len(rows))

    cap = {c["model"]: c for c in summary["capability"]}
    t["capability"] = _table(
        ["模型", "V0 上单次成功成本（美元）", "V0 首次通过", "全部探针首次通过", "全部探针最终通过",
         "生产：通过 / 尝试", "生产：每项成本（美元）"],
        [[LABEL[m], _usd(c["c0_v0"]), _frac(c["v0_first_pass"]), _frac(c["probe_first_pass"]),
          _frac(c["probe_success"]),
          f"{c['produce_accepted']}/{c['produce_items']}" if "produce_items" in c else "–",
          _usd(c.get("produce_cost_per_item"))]
         for m in ORDER if (c := cap.get(m))])

    t["e1"] = _table(
        ["接手模型", "k", "溢价 π [90% 区间]", "β（%/项）[90% 区间]", "R 上成功成本", "MS 上成功成本",
         "R / MS 首次通过"],
        [[LABEL[e["consumer"]], str(e["k"]), _ci_pct(e, "pi"), _beta(e), _usd(e["cts_r"]),
          _usd(e["cts_m"]), f"{_frac(e['first_pass_r'])} / {_frac(e['first_pass_m'])}"]
         for e in _sorted(summary["E1_consumer_fixed_maintainer"])])
    t["e2"] = _table(
        ["模型", "k", "溢价 π [90% 区间]", "β（%/项）", "m（美元）", "m/c₀", "N* [90% 区间]"],
        [[LABEL[e["consumer"]], str(e["k"]), _ci_pct(e, "pi"), _beta(e), _usd(e["m"]),
          _usd(e["m_over_c0"], 2), _nstar(e)]
         for e in _sorted(summary["E1_consumer_fixed_maintainer"] + summary["E2_consumer_self_maintained"])
         if e["maintainer"] == e["consumer"]])
    growth = {g["producer"] + str(g["k"]): g for g in summary["E3_debt_growth"]}
    t["e3"] = _table(
        ["生产模型", "k", "通过项数", "行数", "最大文件", "覆盖率", "重复比例",
         "Sonnet 接手的溢价 π [90% 区间]"],
        [[LABEL[g["producer"]], str(g["k"]), f"{g['n_accepted']:.1f}", f"{g['loc']:.0f}",
          f"{g['max_file_lines']:.0f}", f"{g['coverage'] * 100:.1f}%", f"{g['dup_ratio'] * 100:.2f}%",
          _e3(summary, g)]
         for g in sorted(summary["E3_debt_growth"], key=lambda g: (ORDER.index(g["producer"]), g["k"]))])
    t["e4"] = _table(
        ["模型（写、维护、接手同一个）", "k", "溢价 π [90% 区间]", "β（%/项）[90% 区间]", "m/c₀",
         "N* [90% 区间]"],
        [[LABEL[e["consumer"]], str(e["k"]), _ci_pct(e, "pi"), _beta(e), _usd(e["m_over_c0"], 2),
          _nstar(e)] for e in _sorted(summary["E4_diagonal"])])
    mat = defaultdict(dict)
    for e in summary["E5_matrix_sonnet_maintainer"]:
        mat[e["producer"]][e["consumer"]] = e
    prods = [p for p in ORDER if p in mat]
    cons = [c for c in ORDER if any(c in mat[p] for p in prods)]
    t["e5"] = _table(["生产 \\ 接手"] + [LABEL[c] for c in cons],
                     [[LABEL[p]] + [_pct(mat[p][c]["pi"]) if c in mat[p] else "–" for c in cons]
                      for p in prods])
    t["maint"] = _table(
        ["维护模型", "代码来自", "k", "维护任务", "运行 / 保留的会话", "平均每次维护（美元）"],
        [[LABEL[m["maintainer"]], LABEL[m["producer"]], str(m["k"]), str(m["jobs"]),
          f"{m['sessions']}/{m['kept']}", _usd(m["mean_cost"])]
         for m in sorted(summary["maintenance"],
                         key=lambda m: (ORDER.index(m["maintainer"]), ORDER.index(m["producer"]), m["k"]))])
    t["states"] = states_table()
    return t


BLOCK_TEXT = {"core2": "Haiku / Sonnet / Opus 接手 Sonnet 的代码",
              "core3": "Haiku、Opus 自己写代码，再维护和接手",
              "A2": "Fable 接手 Sonnet 的代码",
              "A3": "Fable 自己写代码，再维护和接手",
              "A2s": "A2 的缩减版：Fable 只在 k=29 接手 Sonnet 的代码（对照为 Sonnet 维护版）",
              "D": "交叉：Haiku、Opus 接手对方的代码（Sonnet 维护）"}


def _frac(x: float | None) -> str:
    return "–" if x is None else f"{x * 100:.0f}%"


def _e3(summary: dict, g: dict) -> str:
    for e in summary["E3_producer_fixed_consumer"] + summary["E1_consumer_fixed_maintainer"]:
        if (e["producer"] == g["producer"] and e["k"] == g["k"] and e["consumer"] == "sonnet55"
                and e["maintainer"] == "sonnet55"):
            return _ci_pct(e, "pi")
    return "–"


def states_table() -> str:
    rows = read_csv(DATA / "states.csv")
    groups = defaultdict(list)
    for r in rows:
        if r["kind"] == "V0":
            groups[("v0", "", 0)].append(r)
        else:
            groups[(r["producer"], r["maintainer"] or "R", int(r["k"]))].append(r)
    out = []
    for (prod, maint, k), rs in sorted(groups.items(), key=lambda kv: (
            kv[0][0] != "v0", ORDER.index(kv[0][0]) if kv[0][0] in ORDER else -1, kv[0][2],
            kv[0][1] != "R", ORDER.index(kv[0][1]) if kv[0][1] in ORDER else -1)):
        name = "V0" if prod == "v0" else f"{LABEL[prod]} k={k} " + (
            "未维护" if maint == "R" else f"经 {LABEL[maint]} 维护")
        f = lambda key: fmean(float(r[key]) for r in rs if r[key] != "")  # noqa: E731
        out.append([name, str(len(rs)), f"{f('loc'):.0f}", f"{f('max_file_lines'):.0f}",
                    f"{f('coverage') * 100:.1f}%", f"{f('dup_ratio') * 100:.2f}%",
                    f"{f('probes_failing'):.1f}"])
    return _table(["状态", "份数", "行数", "最大文件", "覆盖率", "重复比例", "失败的探针数（应为 6）"],
                  out)


def build() -> str:
    summary = cs.summarize()
    (DATA / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    t = tables(summary)
    text = TEMPLATE.read_text(encoding="utf-8")
    missing = set(re.findall(r"\{\{(\w+)\}\}", text)) - set(t)
    if missing:
        raise KeyError(f"no value for placeholders: {sorted(missing)}")
    text = re.sub(r"\{\{(\w+)\}\}", lambda m: t[m.group(1)], text)
    OUTPUT.write_text(text, encoding="utf-8")
    return str(OUTPUT.relative_to(ROOT))


# ---------------------------------------------------------------- figure

FIG_CSS = """
.t1{fill:#1f2328}.t2{fill:#59636e}.grid{stroke:#d1d9e0}.zero{stroke:#59636e}
.s1{fill:#0072B2;stroke:#0072B2}.s2{fill:#D55E00;stroke:#D55E00}
@media (prefers-color-scheme: dark){
.t1{fill:#e6edf3}.t2{fill:#9198a1}.grid{stroke:#3d444d}.zero{stroke:#9198a1}
.s1{fill:#3987e5;stroke:#3987e5}.s2{fill:#d95926;stroke:#d95926}}
text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
"""


def figure_premium(summary: dict, k: int = 29) -> str:
    """Premium at k items per consumer: fixed maintainer (circle) and self-maintained (square)."""
    fixed = {e["consumer"]: e for e in summary["E1_consumer_fixed_maintainer"] if e["k"] == k}
    own = {e["consumer"]: e for e in summary["E2_consumer_self_maintained"] if e["k"] == k}
    models = [m for m in ORDER if m in fixed or m in own]
    vals = [v for d in (fixed, own) for e in d.values()
            for v in (e["pi_lo"], e["pi_hi"]) if v == v]
    lo = min(-0.1, min(vals, default=0) - 0.02)
    hi = max(0.1, max(vals, default=0) + 0.02)
    step = 0.1 if hi - lo <= 1.0 else 0.25
    lo, hi = math.floor(lo / step) * step, math.ceil(hi / step) * step
    W, left, right, top, row_h = 640, 110, 24, 56, 44
    H = top + row_h * len(models) + 48
    x = lambda v: left + (v - lo) / (hi - lo) * (W - left - right)  # noqa: E731
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" '
           f'height="{H}" role="img" aria-label="Premium at k={k} by consumer model">',
           f"<style>{FIG_CSS}</style>"]
    out.append(f'<text class="t1" x="{left}" y="20" font-size="14" font-weight="600">'
               f'接手 Sonnet 代码（k = {k}）时的成本溢价 π，90% 区间</text>')
    # legend
    out.append(f'<circle class="s1" cx="{left + 6}" cy="38" r="5"/>'
               f'<text class="t2" x="{left + 16}" y="42" font-size="12">对照：Sonnet 维护后</text>'
               f'<rect class="s2" x="{left + 171}" y="33" width="10" height="10"/>'
               f'<text class="t2" x="{left + 187}" y="42" font-size="12">对照：该模型自己维护后</text>')
    n = int(round((hi - lo) / step))
    for i in range(n + 1):
        v = lo + i * step
        cls = "zero" if abs(v) < 1e-9 else "grid"
        dash = ' stroke-dasharray="4 3"' if cls == "zero" else ""
        out.append(f'<line class="{cls}" x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{top}" '
                   f'y2="{top + row_h * len(models)}" stroke-width="1"{dash}/>')
        out.append(f'<text class="t2" x="{x(v):.1f}" y="{top + row_h * len(models) + 18}" '
                   f'font-size="12" text-anchor="middle">{v * 100:+.0f}%</text>')
    for i, m in enumerate(models):
        y0 = top + row_h * i + row_h / 2
        out.append(f'<text class="t1" x="{left - 12}" y="{y0 + 4:.1f}" font-size="13" '
                   f'text-anchor="end">{LABEL[m]}</text>')
        for d, cls, dy, shape in ((fixed, "s1", -7, "circle"), (own, "s2", 7, "rect")):
            e = d.get(m)
            if not e or e["pi"] != e["pi"]:
                continue
            yy = y0 + dy
            out.append(f'<line class="{cls}" x1="{x(e["pi_lo"]):.1f}" x2="{x(e["pi_hi"]):.1f}" '
                       f'y1="{yy:.1f}" y2="{yy:.1f}" stroke-width="2"/>')
            if shape == "circle":
                out.append(f'<circle class="{cls}" cx="{x(e["pi"]):.1f}" cy="{yy:.1f}" r="5">'
                           f'<title>{LABEL[m]}，对照 Sonnet 维护：{_ci_pct(e, "pi")}</title></circle>')
            else:
                out.append(f'<rect class="{cls}" x="{x(e["pi"]) - 5:.1f}" y="{yy - 5:.1f}" '
                           f'width="10" height="10"><title>{LABEL[m]}，对照自己维护：'
                           f'{_ci_pct(e, "pi")}</title></rect>')
    out.append(f'<text class="t2" x="{(left + W - right) / 2:.1f}" y="{H - 6}" font-size="12" '
               f'text-anchor="middle">π &gt; 0：不维护的代码更贵；π &lt; 0：维护后的代码更贵</text>')
    out.append("</svg>")
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / f"premium-k{k}.svg"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return str(path.relative_to(ROOT))
