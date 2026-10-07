"""Simulated codebase, executor and metrics source (phase 1). No model is called.

All coefficients come from config/sim/*.toml and are assumptions.
Random draws use common random numbers: the same backlog item and attempt, the same
maintenance agent in the same week, and the same weekly event get the same draws in
both groups and both hypotheses, so differences come from the codebase state and the
coefficients, not from luck.
"""
from __future__ import annotations

import hashlib
import math
import random

from .interfaces import TaskResult
from .pricing import cost_usd


def make_rng(*parts) -> random.Random:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


class SimWorld:
    """State of one simulated codebase (one group, one rep)."""

    def __init__(self, params: dict, root_seed: str, rep: int):
        self.p = params
        init = params["initial"]
        self.state = {
            "loc": float(init["loc"]),
            "dup_ratio": float(init["dup_ratio"]),
            "coverage": float(init["coverage"]),
            "max_file_lines": float(init["max_file_lines"]),
            "vulns": int(init["vulns"]),
            "outdated_deps": int(init["outdated_deps"]),
            "context_factor": float(init["context_factor"]),
        }
        self.init = dict(self.state)
        # The hypothesis is deliberately not part of the seed: both hypotheses see the same
        # draws, so they differ only in their coefficients.
        self.seed_parts = (root_seed, rep)

    def rng(self, *key) -> random.Random:
        return make_rng(*self.seed_parts, *key)

    def noise(self, rng: random.Random) -> float:
        sigma = self.p["tokens"]["noise_sigma"]
        return rng.lognormvariate(-sigma * sigma / 2, sigma)

    def deviations(self) -> dict:
        s, i = self.state, self.init
        return {
            "xL": s["loc"] / i["loc"] - 1,
            "xD": max(0.0, s["dup_ratio"] / i["dup_ratio"] - 1),
            "xM": max(0.0, s["max_file_lines"] / i["max_file_lines"] - 1),
            "xC": max(0.0, 1 - s["coverage"] / i["coverage"]),
        }

    def impl_input(self) -> float:
        t, e, x = self.p["tokens"], self.p["effects"], self.deviations()
        return t["fixed_input"] + t["explore_input"] * (
            (1 + x["xL"]) ** e["loc_elasticity"] * self.state["context_factor"]
            * (1 + e["dup_input"] * x["xD"] + e["max_file_input"] * x["xM"]))

    def pass_factor(self) -> float:
        e, x = self.p["effects"], self.deviations()
        return math.exp(-(e["coverage_fail"] * x["xC"] + e["dup_fail"] * x["xD"]
                          + e["max_file_fail"] * x["xM"]))

    def apply_item(self, item: str) -> None:
        d, e, s = self.p["drift"], self.p["effects"], self.state
        rng = self.rng("delta", item)
        added = max(d["loc_added_min"], rng.gauss(d["loc_added_mean"], d["loc_added_sd"]))
        s["coverage"] = (s["coverage"] * s["loc"] + d["new_code_coverage"] * added) / (
            s["loc"] + added)
        s["loc"] += added
        s["dup_ratio"] = min(0.95, s["dup_ratio"] + d["dup_ratio_step"])
        s["max_file_lines"] += d["hot_file_share"] * added
        s["context_factor"] += e["context_step"]

    def apply_maint(self, agent: str) -> None:
        s, i, mp = self.state, self.init, self.p["maint"][agent]
        if agent == "security":
            s["vulns"] = 0
            s["outdated_deps"] = 0
        elif agent == "tests":
            s["coverage"] = max(s["coverage"], i["coverage"] - mp["coverage_after_gap"])
        elif agent == "refactor":
            target = i["dup_ratio"] * mp["dup_after_factor"]
            if s["dup_ratio"] > target:
                s["loc"] -= (s["dup_ratio"] - target) * s["loc"]
                s["dup_ratio"] = target
            s["max_file_lines"] = min(s["max_file_lines"],
                                      i["max_file_lines"] * mp["max_file_after_factor"])
        elif agent == "knowledge":
            s["context_factor"] = min(s["context_factor"],
                                      self.p["effects"]["context_after_knowledge"])
        else:
            raise ValueError(agent)

    def weekly_events(self, week: int) -> None:
        ev = self.p["weekly_events"]
        rng = self.rng("week", week)
        if rng.random() < ev["p_new_vuln"]:
            self.state["vulns"] += 1
        if rng.random() < ev["p_new_outdated"]:
            self.state["outdated_deps"] += 1

    def metrics(self) -> dict:
        s = self.state
        return {
            "loc": round(s["loc"]),
            "max_file_lines": round(s["max_file_lines"]),
            "dup_ratio": round(s["dup_ratio"], 6),
            "coverage": round(s["coverage"], 6),
            "vulns": s["vulns"],
            "outdated_deps": s["outdated_deps"],
            "build_ok": 1,
            "tests_ok": 1,
        }


class SimExecutor:
    def __init__(self, world: SimWorld, prices: dict, model: str):
        self.world = world
        self.prices = prices
        self.model = model
        self._pending: tuple[str, str | None] | None = None

    def start(self, task_type: str, item: str | None) -> None:
        self._pending = (task_type, item)

    def run(self, task_type: str, item: str | None, debug_index: int, week: int,
            guard_usd: float, context: dict) -> TaskResult:
        w, t = self.world, self.world.p["tokens"]
        if task_type in ("calib", "impl", "debug"):
            rng = w.rng("calib" if task_type == "calib" else "item", item, debug_index)
            eps = w.noise(rng)
            u = rng.random()
            acc = w.p["acceptance"]
            if debug_index == 0:
                tin, tout, p = w.impl_input() * eps, t["impl_output"] * eps, acc["p_impl"]
            else:
                tin = w.impl_input() * t["debug_input_ratio"] * eps
                tout, p = t["debug_output"] * eps, acc["p_debug"]
            p *= w.pass_factor()
        elif task_type.startswith("maint_"):
            agent = task_type[len("maint_"):]
            mp = w.p["maint"][agent]
            rng = w.rng("maint", agent, week)
            eps = w.noise(rng)
            u = rng.random()
            xl = w.deviations()["xL"]
            tin = mp["base_input"] * (1 + xl) ** mp["loc_exponent"] * eps
            tout, p = mp["output"] * eps, mp["p_success"]
        else:
            raise ValueError(task_type)
        cache_read = round(tin * t["cache_read_share"])
        cache_write = round(tin * t["cache_write_share"])
        uncached = max(0, round(tin) - cache_read - cache_write)
        out = round(tout)
        cost = cost_usd(self.prices, uncached, 0, cache_write, cache_read, out)
        return TaskResult(input_tokens=uncached, cache_write_tokens=cache_write,
                          cache_read_tokens=cache_read, output_tokens=out, cost_usd=cost,
                          accepted=u < p, model=self.model)

    def finish(self, keep: bool) -> None:
        if self._pending is None:
            raise RuntimeError("finish() without start()")
        task_type, item = self._pending
        self._pending = None
        if not keep or task_type == "calib":
            return
        if task_type == "impl":
            self.world.apply_item(item)
        elif task_type.startswith("maint_"):
            self.world.apply_maint(task_type[len("maint_"):])


class SimMetrics:
    def __init__(self, world: SimWorld):
        self.world = world

    def begin_week(self, week: int) -> None:
        self.world.weekly_events(week)

    def measure(self) -> dict:
        return self.world.metrics()
