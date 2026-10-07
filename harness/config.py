"""Configuration loading."""
from __future__ import annotations

import copy
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "docs" / "data"
HYPOTHESES = ("strong", "weak")


def _load(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def experiment() -> dict:
    return _load(CONFIG_DIR / "experiment.toml")


def thresholds() -> dict:
    return _load(CONFIG_DIR / "thresholds.toml")


def prices() -> dict:
    return _load(CONFIG_DIR / "prices.toml")


def sim_params(hypothesis: str) -> dict:
    if hypothesis not in HYPOTHESES:
        raise ValueError(f"unknown hypothesis: {hypothesis}")
    common = _load(CONFIG_DIR / "sim" / "common.toml")
    return _merge(common, _load(CONFIG_DIR / "sim" / f"{hypothesis}.toml"))


def model_prices(model: str) -> dict:
    table = prices().get("models", {})
    if model not in table:
        raise KeyError(f"no prices for model {model!r} in config/prices.toml")
    entry = table[model]
    missing = [k for k in ("input", "cache_write_5m", "cache_write_1h", "cache_read", "output")
               if entry.get(k) is None]
    if missing:
        raise ValueError(f"prices for {model!r} missing: {missing}")
    return entry
