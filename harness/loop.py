"""Scheduling loop shared by the simulated and the real phase."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from statistics import fmean
from typing import Callable

from .interfaces import Executor, MetricsSource, TaskResult
from .logs import RunLog

MAINT_SPEND_KEYS = ("security", "tests", "refactor", "knowledge")


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolation percentile (same as numpy's default)."""
    xs = sorted(values)
    if not xs:
        raise ValueError("empty sample")
    k = (len(xs) - 1) * q
    lo = math.floor(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


@dataclass
class Plan:
    """Budget rules derived from calibration; identical for both groups and all reps."""
    calib_costs: list[float]
    calib_mean: float
    calib_quantile: float
    budget: float
    cap: float
    maint_cap: float
    baseline: dict

    @classmethod
    def from_calibration(cls, costs: list[float], first_inputs: list[float],
                         baseline_metrics: dict, exp: dict) -> "Plan":
        mean = fmean(costs)
        quant = percentile(costs, exp["cap_quantile"])
        cap = exp["cap_multiplier"] * quant
        baseline = dict(baseline_metrics)
        baseline["avg_input_tokens"] = fmean(first_inputs)
        return cls(calib_costs=list(costs), calib_mean=mean, calib_quantile=quant,
                   budget=exp["budget_multiplier"] * mean, cap=cap,
                   maint_cap=cap * exp["maint_cap_multiplier"], baseline=baseline)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Ident:
    phase: str
    hypothesis: str
    group: str
    rep: int

    def row(self) -> dict:
        return {"phase": self.phase, "hypothesis": self.hypothesis, "group": self.group,
                "rep": self.rep}


@dataclass
class SeriesState:
    """Everything the loop carries from one week to the next (enough to resume)."""
    week_done: int = 0
    pointer: int = 0
    carry: float = 0.0
    prev_avg_input: float = 0.0
    cum_impl_spend: float = 0.0
    cum_completed: int = 0
    extra: dict = field(default_factory=dict)


def _task_row(ident: Ident, week: int, seq: int, task_type: str, item: str | None,
              debug_index: int, r: TaskResult) -> dict:
    row = ident.row()
    row.update({
        "week": week, "seq": seq, "item": item or "", "task_type": task_type,
        "debug_index": debug_index, "input_tokens": r.input_tokens,
        "cache_write_tokens": r.cache_write_tokens, "cache_read_tokens": r.cache_read_tokens,
        "output_tokens": r.output_tokens, "total_input_tokens": r.total_input_tokens,
        "cost_usd": r.cost_usd, "accepted": r.accepted, "rolled_back": False,
        "forced_stop": r.forced_stop, "model": r.model, "session_id": r.session_id,
        "duration_s": round(r.duration_s, 1) if r.duration_s else None,
        "cli_cost_usd": r.extra.get("cli_cost_usd"),
    })
    return row


# Relative changes are compared with this tolerance so that a value exactly at the
# threshold does not fire because of floating-point rounding.
EPS = 1e-9


def check_trigger(agent: str, m: dict, baseline: dict, thr: dict) -> list[tuple]:
    """Return [(metric, value, baseline, threshold)] for each condition that fires."""
    fired = []
    keys = {"security": ("vulns",), "tests": ("coverage",),
            "refactor": ("dup_ratio", "max_file_lines"), "knowledge": ("avg_input_tokens",)}
    if any(m.get(k) is None for k in keys.get(agent, ())):
        return fired  # a metric that could not be measured never triggers
    if agent == "security":
        t = thr["security"]["vulns_gt"]
        if m["vulns"] > t:
            fired.append(("vulns", m["vulns"], baseline["vulns"], t))
    elif agent == "tests":
        t = thr["tests"]["coverage_rel_drop_gt"]
        c0 = baseline["coverage"]
        if c0 > 0 and (c0 - m["coverage"]) / c0 > t + EPS:
            fired.append(("coverage", m["coverage"], c0, t))
    elif agent == "refactor":
        t = thr["refactor"]["dup_rel_rise_gt"]
        d0 = max(baseline["dup_ratio"], thr["refactor"].get("dup_baseline_floor", 0.0))
        if d0 > 0 and (m["dup_ratio"] - d0) / d0 > t + EPS:
            fired.append(("dup_ratio", m["dup_ratio"], baseline["dup_ratio"], t))
        t = thr["refactor"]["max_file_rel_rise_gt"]
        m0 = baseline["max_file_lines"]
        if m0 > 0 and (m["max_file_lines"] - m0) / m0 > t + EPS:
            fired.append(("max_file_lines", m["max_file_lines"], m0, t))
    elif agent == "knowledge":
        t = thr["knowledge"]["avg_input_tokens_rel_rise_gt"]
        t0 = baseline["avg_input_tokens"]
        if t0 > 0 and (m["avg_input_tokens"] - t0) / t0 > t + EPS:
            fired.append(("avg_input_tokens", m["avg_input_tokens"], t0, t))
    else:
        raise ValueError(agent)
    return fired


def _join(values) -> str:
    return ";".join(f"{v:.6g}" if isinstance(v, float) else str(v) for v in values)


def calibrate(executor: Executor, items: list[str], exp: dict, log: RunLog, phase: str,
              hypothesis: str, guard_usd: float) -> tuple[list[float], list[float]]:
    """Run calibration items from the initial state; the codebase is restored after each."""
    ident = Ident(phase, hypothesis, "calib", 0)
    costs, first_inputs = [], []
    seq = 0
    for item in items:
        executor.start("calib", item)
        spent = 0.0
        rows = []
        accepted = False
        for j in range(exp["max_debug"] + 1):
            r = executor.run("calib", item, j, 0, guard_usd, {})
            spent += r.cost_usd
            if j == 0:
                first_inputs.append(r.total_input_tokens)
            seq += 1
            row = _task_row(ident, 0, seq, "calib", item, j, r)
            row.update(item_cost_usd=spent, overspend_usd=0.0)
            rows.append(row)
            accepted = r.accepted
            if accepted:
                break
        executor.finish(keep=False)
        rows[-1]["rolled_back"] = not accepted
        for row in rows:
            log.append("tasks", row)
        costs.append(spent)
    return costs, first_inputs


def run_series(executor: Executor, metrics: MetricsSource, plan: Plan, exp: dict, thr: dict,
               backlog: list[str], log: RunLog, ident: Ident, state: SeriesState | None = None,
               on_week_end: Callable[[int, SeriesState], None] | None = None) -> SeriesState:
    """Run weeks (state.week_done + 1) .. exp['weeks'] for one group and one rep."""
    if state is None:
        state = SeriesState(prev_avg_input=plan.baseline["avg_input_tokens"])
        base = ident.row()
        base.update(week=0, point="start", **{k: plan.baseline[k] for k in plan.baseline})
        log.append("metrics", base)
    guard_mult = exp["runaway_guard_multiplier"]
    cap, maint_cap = plan.cap, plan.maint_cap

    for week in range(state.week_done + 1, exp["weeks"] + 1):
        metrics.begin_week(week)
        m = metrics.measure()
        m["avg_input_tokens"] = state.prev_avg_input
        snap = ident.row()
        snap.update(week=week, point="start", **m)
        log.append("metrics", snap)

        carry_in = state.carry
        available = plan.budget - carry_in
        remaining = available
        seq = 0
        spend = {k: 0.0 for k in MAINT_SPEND_KEYS}
        spend_impl = spend_debug = 0.0
        triggered, skipped = [], []
        item_overspend_count, item_overspend_usd = 0, 0.0
        impl_first_inputs = []

        if ident.group == "maint":
            for agent in exp["maint_order"]:
                fired = check_trigger(agent, m, plan.baseline, thr)
                if not fired:
                    continue
                if remaining < maint_cap:
                    skipped.append(agent)
                    continue
                task_type = f"maint_{agent}"
                executor.start(task_type, None)
                r = executor.run(task_type, None, 0, week, maint_cap * guard_mult,
                                 {"trigger": fired})
                executor.finish(keep=r.accepted)
                remaining -= r.cost_usd
                spend[agent] += r.cost_usd
                triggered.append(agent)
                over = max(0.0, r.cost_usd - maint_cap)
                if over > 0:
                    item_overspend_count += 1
                    item_overspend_usd += over
                seq += 1
                row = _task_row(ident, week, seq, task_type, None, 0, r)
                row.update(rolled_back=not r.accepted, item_cost_usd=r.cost_usd,
                           overspend_usd=over,
                           trigger_metric=_join(f[0] for f in fired),
                           trigger_value=_join(f[1] for f in fired),
                           trigger_baseline=_join(f[2] for f in fired),
                           trigger_threshold=_join(f[3] for f in fired))
                log.append("tasks", row)

        avg_cost = (state.cum_impl_spend / state.cum_completed if state.cum_completed
                    else plan.calib_mean)
        predicted = max(remaining, 0.0) / avg_cost
        completed = failed = 0

        while state.pointer < len(backlog) and remaining >= cap:
            item = backlog[state.pointer]
            state.pointer += 1
            executor.start("impl", item)
            spent = 0.0
            accepted = False
            rows = []
            for j in range(exp["max_debug"] + 1):
                if spent >= cap:
                    break  # cap reached: no new debug session
                task_type = "impl" if j == 0 else "debug"
                r = executor.run(task_type, item, j, week, cap * guard_mult,
                                 {"debug_index": j})
                spent += r.cost_usd
                remaining -= r.cost_usd
                if j == 0:
                    spend_impl += r.cost_usd
                    impl_first_inputs.append(r.total_input_tokens)
                else:
                    spend_debug += r.cost_usd
                seq += 1
                row = _task_row(ident, week, seq, task_type, item, j, r)
                row.update(item_cost_usd=spent, overspend_usd=max(0.0, spent - cap))
                rows.append(row)
                accepted = r.accepted
                if accepted:
                    break
            executor.finish(keep=accepted)
            rows[-1]["rolled_back"] = not accepted
            for row in rows:
                log.append("tasks", row)
            if accepted:
                completed += 1
            else:
                failed += 1
            if spent > cap:
                item_overspend_count += 1
                item_overspend_usd += spent - cap

        week_overspend = max(0.0, -remaining)
        state.carry = week_overspend if exp["carry_overspend"] else 0.0
        state.cum_impl_spend += spend_impl + spend_debug
        state.cum_completed += completed
        if impl_first_inputs:
            state.prev_avg_input = fmean(impl_first_inputs)
        state.week_done = week

        wrow = ident.row()
        wrow.update(
            week=week, budget_usd=plan.budget, carryover_in_usd=carry_in,
            available_usd=available, **m,
            **{f"spend_maint_{k}": v for k, v in spend.items()},
            spend_maint=sum(spend.values()), spend_impl=spend_impl, spend_debug=spend_debug,
            spend_implementation=spend_impl + spend_debug, unused_usd=max(remaining, 0.0),
            week_overspend_usd=week_overspend, predicted_items=predicted,
            completed_items=completed, failed_items=failed,
            item_overspend_count=item_overspend_count, item_overspend_usd=item_overspend_usd,
            triggered=";".join(triggered), maint_skipped=";".join(skipped),
        )
        log.append("weeks", wrow)

        end = metrics.measure()
        end["avg_input_tokens"] = state.prev_avg_input
        snap = ident.row()
        snap.update(week=week, point="end", **end)
        log.append("metrics", snap)

        if on_week_end:
            on_week_end(week, state)
    return state
