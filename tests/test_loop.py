"""Rule tests for the scheduling loop, using a scripted executor."""
import csv
import tempfile
import unittest
from pathlib import Path

from harness import config
from harness.interfaces import TaskResult
from harness.logs import RunLog
from harness.loop import Ident, Plan, SeriesState, check_trigger, percentile, run_series
from harness.sim_model import SimExecutor, SimMetrics, SimWorld

BASE_METRICS = {"loc": 1000, "max_file_lines": 100, "dup_ratio": 0.05, "coverage": 0.8,
                "vulns": 0, "outdated_deps": 0, "build_ok": 1, "tests_ok": 1}
THRESHOLDS = {"security": {"vulns_gt": 0}, "tests": {"coverage_rel_drop_gt": 0.05},
              "refactor": {"dup_rel_rise_gt": 0.3, "max_file_rel_rise_gt": 0.5},
              "knowledge": {"avg_input_tokens_rel_rise_gt": 0.2}}


def exp(**over):
    e = {"weeks": 1, "backlog_size": 40, "budget_multiplier": 4.5, "cap_quantile": 0.8,
         "cap_multiplier": 1.5, "maint_cap_multiplier": 1.0, "max_debug": 2,
         "carry_overspend": True, "maint_order": ["security", "tests", "refactor", "knowledge"],
         "runaway_guard_multiplier": 3.0, "groups": ["nomaint", "maint"]}
    e.update(over)
    return e


def plan(budget=10.0, cap=4.0, maint_cap=4.0, calib_mean=2.0, avg_input=100.0):
    base = dict(BASE_METRICS, avg_input_tokens=avg_input)
    return Plan(calib_costs=[calib_mean], calib_mean=calib_mean, calib_quantile=cap / 1.5,
                budget=budget, cap=cap, maint_cap=maint_cap, baseline=base)


class Scripted:
    """Executor whose cost/acceptance per (task_type, item, attempt) is scripted."""

    def __init__(self, script, default=(1.0, True)):
        self.script = script
        self.default = default
        self.calls = []
        self.finished = []

    def start(self, task_type, item):
        self.current = (task_type, item)

    def run(self, task_type, item, debug_index, week, guard_usd, context):
        key = (task_type, item, debug_index) if item else (task_type, week)
        cost, ok = self.script.get(key, self.default)
        self.calls.append(key)
        return TaskResult(input_tokens=100, cache_write_tokens=0, cache_read_tokens=0,
                          output_tokens=10, cost_usd=cost, accepted=ok)

    def finish(self, keep):
        self.finished.append((self.current, keep))


class Metrics:
    def __init__(self, values=None):
        self.values = dict(BASE_METRICS, **(values or {}))

    def begin_week(self, week):
        pass

    def measure(self):
        return dict(self.values)


def run(executor, metrics=None, p=None, e=None, group="nomaint", backlog=None, state=None):
    tmp = tempfile.mkdtemp()
    log = RunLog(Path(tmp), fresh=True)
    st = run_series(executor, metrics or Metrics(), p or plan(), e or exp(), THRESHOLDS,
                    backlog or [f"B{i:02d}" for i in range(1, 41)], log,
                    Ident("test", "t", group, 1), state=state)
    rows = {k: list(csv.DictReader(open(Path(tmp) / f"{k}.csv"))) for k in
            ("tasks", "weeks", "metrics")}
    return st, rows


class LoopRules(unittest.TestCase):
    def test_week_ends_when_remaining_below_cap(self):
        # budget 10, cap 4, each item costs 3: start at 10, 7, 4 -> third starts (4 >= 4),
        # then 1 < 4 stops.
        ex = Scripted({}, default=(3.0, True))
        st, rows = run(ex)
        self.assertEqual(st.pointer, 3)
        w = rows["weeks"][0]
        self.assertEqual(w["completed_items"], "3")
        self.assertAlmostEqual(float(w["unused_usd"]), 1.0)

    def test_two_debug_attempts_then_rollback(self):
        script = {("impl", "B01", 0): (1.0, False), ("debug", "B01", 1): (0.5, False),
                  ("debug", "B01", 2): (0.5, False)}
        ex = Scripted(script, default=(9.0, True))
        st, rows = run(ex, p=plan(budget=10, cap=9))
        self.assertEqual(ex.calls[:3], [("impl", "B01", 0), ("debug", "B01", 1),
                                        ("debug", "B01", 2)])
        self.assertEqual(ex.finished[0], (("impl", "B01"), False))
        t = rows["tasks"]
        self.assertEqual([r["rolled_back"] for r in t[:3]], ["0", "0", "1"])
        self.assertEqual(rows["weeks"][0]["failed_items"], "1")

    def test_no_new_debug_after_cap_and_overspend_recorded(self):
        # first attempt costs 5 > cap 4: session runs to completion, no debug follows
        script = {("impl", "B01", 0): (5.0, False)}
        ex = Scripted(script, default=(1.0, True))
        st, rows = run(ex, p=plan(budget=10, cap=4))
        self.assertNotIn(("debug", "B01", 1), ex.calls)
        t = rows["tasks"][0]
        self.assertEqual(t["rolled_back"], "1")
        self.assertAlmostEqual(float(t["overspend_usd"]), 1.0)
        self.assertEqual(rows["weeks"][0]["item_overspend_count"], "1")

    def test_week_overspend_carries_into_next_week(self):
        # remaining 10 -> item1 costs 7 -> 3 < cap 3? no: 3 >= 3 starts item2 costing 5 -> -2
        script = {("impl", "B01", 0): (7.0, True), ("impl", "B02", 0): (5.0, True)}
        ex = Scripted(script, default=(1.0, True))
        st, rows = run(ex, p=plan(budget=10, cap=3), e=exp(weeks=2))
        w1, w2 = rows["weeks"]
        self.assertAlmostEqual(float(w1["week_overspend_usd"]), 2.0)
        self.assertAlmostEqual(float(w2["carryover_in_usd"]), 2.0)
        self.assertAlmostEqual(float(w2["available_usd"]), 8.0)

    def test_no_carry_when_disabled(self):
        script = {("impl", "B01", 0): (7.0, True), ("impl", "B02", 0): (5.0, True)}
        ex = Scripted(script, default=(1.0, True))
        st, rows = run(ex, p=plan(budget=10, cap=3), e=exp(weeks=2, carry_overspend=False))
        self.assertAlmostEqual(float(rows["weeks"][1]["available_usd"]), 10.0)

    def test_prediction_uses_calibration_then_history(self):
        ex = Scripted({}, default=(2.5, True))
        st, rows = run(ex, p=plan(budget=10, cap=4, calib_mean=2.0), e=exp(weeks=2))
        w1, w2 = rows["weeks"]
        self.assertAlmostEqual(float(w1["predicted_items"]), 5.0)       # 10 / 2.0
        self.assertAlmostEqual(float(w2["predicted_items"]), 4.0)       # 10 / 2.5

    def test_maintenance_only_in_maint_group(self):
        m = Metrics({"vulns": 1, "coverage": 0.70})
        ex = Scripted({}, default=(1.0, True))
        run(ex, metrics=m, group="nomaint")
        self.assertFalse(any(c[0].startswith("maint_") for c in ex.calls))
        ex = Scripted({}, default=(1.0, True))
        st, rows = run(ex, metrics=m, group="maint")
        maint = [c for c in ex.calls if c[0].startswith("maint_")]
        self.assertEqual(maint, [("maint_security", 1), ("maint_tests", 1)])
        t = rows["tasks"][0]
        self.assertEqual(t["trigger_metric"], "vulns")
        self.assertEqual(rows["weeks"][0]["triggered"], "security;tests")

    def test_maintenance_skipped_when_budget_short(self):
        m = Metrics({"vulns": 1, "coverage": 0.70})
        ex = Scripted({("maint_security", 1): (7.0, True)}, default=(1.0, True))
        st, rows = run(ex, metrics=m, group="maint", p=plan(budget=10, cap=4, maint_cap=4))
        self.assertEqual(rows["weeks"][0]["maint_skipped"], "tests")

    def test_failed_maintenance_is_rolled_back(self):
        m = Metrics({"vulns": 1})
        ex = Scripted({("maint_security", 1): (1.0, False)}, default=(1.0, True))
        run(ex, metrics=m, group="maint")
        self.assertEqual(ex.finished[0], (("maint_security", None), False))

    def test_backlog_exhaustion_stops(self):
        ex = Scripted({}, default=(0.1, True))
        st, rows = run(ex, backlog=["B01", "B02"])
        self.assertEqual(st.pointer, 2)
        self.assertEqual(rows["weeks"][0]["completed_items"], "2")

    def test_resume_from_state(self):
        ex = Scripted({}, default=(3.0, True))
        state = SeriesState(week_done=1, pointer=5, carry=0.0, prev_avg_input=100.0,
                            cum_impl_spend=9.0, cum_completed=3)
        st, rows = run(ex, e=exp(weeks=2), state=state)
        self.assertEqual([r["week"] for r in rows["weeks"]], ["2"])
        self.assertEqual(ex.calls[0], ("impl", "B06", 0))


class Triggers(unittest.TestCase):
    def test_relative_thresholds(self):
        base = dict(BASE_METRICS, avg_input_tokens=100.0)
        m = dict(base, coverage=0.76, dup_ratio=0.0651, max_file_lines=150,
                 avg_input_tokens=120.0)
        self.assertEqual(check_trigger("tests", m, base, THRESHOLDS), [])   # exactly 5%
        self.assertEqual([f[0] for f in check_trigger("refactor", m, base, THRESHOLDS)],
                         ["dup_ratio"])
        self.assertEqual(check_trigger("knowledge", m, base, THRESHOLDS), [])
        m["avg_input_tokens"] = 121.0
        self.assertEqual(len(check_trigger("knowledge", m, base, THRESHOLDS)), 1)

    def test_percentile(self):
        self.assertAlmostEqual(percentile([1, 2, 3], 0.8), 2.6)
        self.assertAlmostEqual(percentile([5], 0.8), 5)


class Simulation(unittest.TestCase):
    def test_common_random_numbers_and_determinism(self):
        params = config.sim_params("strong")
        prices = config.model_prices(config.prices()["sim_model"])
        a, b = SimWorld(params, "s", 1), SimWorld(params, "s", 1)
        ea, eb = SimExecutor(a, prices, "m"), SimExecutor(b, prices, "m")
        ra = ea.run("impl", "B01", 0, 1, 0, {})
        rb = eb.run("impl", "B01", 0, 1, 0, {})
        self.assertEqual(ra, rb)
        SimMetrics(a).begin_week(3)
        SimMetrics(b).begin_week(3)
        self.assertEqual(a.state, b.state)

    def test_rollback_leaves_state_unchanged(self):
        params = config.sim_params("strong")
        prices = config.model_prices(config.prices()["sim_model"])
        w = SimWorld(params, "s", 1)
        ex = SimExecutor(w, prices, "m")
        before = dict(w.state)
        ex.start("impl", "B01")
        ex.run("impl", "B01", 0, 1, 0, {})
        ex.finish(keep=False)
        self.assertEqual(w.state, before)
        ex.start("impl", "B01")
        ex.finish(keep=True)
        self.assertGreater(w.state["loc"], before["loc"])
        self.assertLess(w.state["coverage"], before["coverage"])

    def test_maintenance_restores_toward_baseline(self):
        params = config.sim_params("strong")
        prices = config.model_prices(config.prices()["sim_model"])
        w = SimWorld(params, "s", 1)
        for i in range(20):
            w.apply_item(f"B{i}")
        w.apply_maint("tests")
        w.apply_maint("refactor")
        w.apply_maint("knowledge")
        self.assertAlmostEqual(w.state["coverage"], w.init["coverage"] - 0.01)
        self.assertAlmostEqual(w.state["dup_ratio"], w.init["dup_ratio"] * 1.1)
        self.assertAlmostEqual(w.state["context_factor"], 0.80)


if __name__ == "__main__":
    unittest.main()
