"""Run the simulated phase for one hypothesis."""
from __future__ import annotations

import datetime as dt
import subprocess

from . import config
from .logs import RunLog
from .loop import Ident, Plan, calibrate, run_series
from .sim_model import SimExecutor, SimMetrics, SimWorld


def backlog_ids(n: int) -> list[str]:
    return [f"B{i:02d}" for i in range(1, n + 1)]


def _git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=config.ROOT, text=True,
                              capture_output=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def run(hypothesis: str) -> dict:
    exp, thr = config.experiment(), config.thresholds()
    params = config.sim_params(hypothesis)
    model = config.prices()["sim_model"]
    prices = config.model_prices(model)
    seed = exp["seed"]
    log = RunLog(config.DATA_DIR / "sim" / hypothesis, fresh=True)

    world0 = SimWorld(params, seed, rep=0)
    calib_items = [f"C{i}" for i in range(1, exp["calibration_items"] + 1)]
    costs, first_inputs = calibrate(SimExecutor(world0, prices, model), calib_items, exp, log,
                                    "sim", hypothesis, guard_usd=float("inf"))
    plan = Plan.from_calibration(costs, first_inputs, world0.metrics(), exp)

    backlog = backlog_ids(exp["backlog_size"])
    for rep in range(1, exp["reps"] + 1):
        for group in exp["groups"]:
            world = SimWorld(params, seed, rep)
            run_series(SimExecutor(world, prices, model), SimMetrics(world), plan, exp, thr,
                       backlog, log, Ident("sim", hypothesis, group, rep))

    meta = {
        "phase": "sim",
        "hypothesis": hypothesis,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git_head(),
        "model": model,
        "prices": prices,
        "prices_source": "config/prices.toml",
        "experiment": exp,
        "thresholds": thr,
        "sim_params": params,
        "plan": plan.to_dict(),
    }
    log.write_run_meta(meta)
    return meta
