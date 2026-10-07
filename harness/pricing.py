"""Token-to-USD conversion from config/prices.toml."""
from __future__ import annotations

PER = 1_000_000


def cost_usd(prices: dict, input_tokens: float, cache_write_5m: float, cache_write_1h: float,
             cache_read: float, output_tokens: float) -> float:
    return (input_tokens * prices["input"]
            + cache_write_5m * prices["cache_write_5m"]
            + cache_write_1h * prices["cache_write_1h"]
            + cache_read * prices["cache_read"]
            + output_tokens * prices["output"]) / PER
