"""Usage parsing for the real executor."""
import json
import unittest
from pathlib import Path

from harness.real_executor import UsageUnavailable, infra_error, price, usage_by_model

PRICES = {"m": {"input": 2.0, "cache_write_5m": 2.5, "cache_write_1h": 4.0, "cache_read": 0.1,
                "output": 10.0}}


def result(inp, cw, read, out, cum):
    return {"type": "result", "usage": {"input_tokens": inp, "cache_creation_input_tokens": cw,
                                        "cache_read_input_tokens": read, "output_tokens": out,
                                        "cache_creation": {"ephemeral_1h_input_tokens": cw,
                                                           "ephemeral_5m_input_tokens": 0}},
            "modelUsage": {"m": {"inputTokens": cum[0], "cacheCreationInputTokens": cum[1],
                                 "cacheReadInputTokens": cum[2], "outputTokens": cum[3]}}}


class Usage(unittest.TestCase):
    def test_single_result(self):
        s = {"results": [result(2, 100, 1000, 10, (2, 100, 1000, 10))], "per_message": {}}
        self.assertEqual(usage_by_model(s, "m"), {"m": {"input": 2, "cw5": 0, "cw1": 100,
                                                        "read": 1000, "output": 10}})

    def test_several_results_are_summed(self):
        # a session with a background task: two turns, cumulative modelUsage in the last one
        s = {"results": [result(26, 20081, 304261, 5303, (26, 20081, 304261, 5303)),
                         result(2, 1014, 29348, 112, (28, 21095, 333609, 5415))],
             "per_message": {}}
        t = usage_by_model(s, "m")
        self.assertEqual(t["m"]["read"], 333609)
        self.assertEqual(t["m"]["output"], 5415)
        self.assertAlmostEqual(price(t, PRICES), 0.1719469, places=6)

    def test_mismatch_is_an_error(self):
        s = {"results": [result(2, 100, 1000, 10, (2, 100, 999, 10))], "per_message": {}}
        with self.assertRaises(UsageUnavailable):
            usage_by_model(s, "m")


TIERED = {"h": {"input": 0.1, "cache_write_5m": 0.125, "cache_write_1h": 0.2, "cache_read": 0.01,
                "output": 0.5, "tier_prompt_tokens": 100000,
                "above_tier": {"input": 0.5, "cache_write_5m": 0.625, "cache_write_1h": 1.0,
                               "cache_read": 0.05, "output": 2.5}}}


def msg_usage(inp, cw, read, out):
    return {"input_tokens": inp, "cache_creation_input_tokens": cw,
            "cache_read_input_tokens": read, "output_tokens": out}


class Tiered(unittest.TestCase):
    def test_all_requests_below_the_tier(self):
        per = {"a": ("h", msg_usage(1, 1000, 20000, 5)), "b": ("h", msg_usage(1, 500, 21000, 5))}
        t = {"h": {"input": 2, "cw5": 0, "cw1": 1500, "read": 41000, "output": 30}}
        expected = (2 * 0.1 + 1500 * 0.2 + 41000 * 0.01 + 30 * 0.5) / 1e6
        self.assertAlmostEqual(price(t, TIERED, per), expected, places=12)

    def test_long_request_uses_the_higher_rate(self):
        per = {"a": ("h", msg_usage(1, 1000, 20000, 10)), "b": ("h", msg_usage(1, 500, 120000, 30))}
        t = {"h": {"input": 2, "cw5": 0, "cw1": 1500, "read": 140000, "output": 80}}
        base = (1 * 0.1 + 1000 * 0.2 + 20000 * 0.01 + 20 * 0.5) / 1e6      # 80 * 10/40 output
        above = (1 * 0.5 + 500 * 1.0 + 120000 * 0.05 + 60 * 2.5) / 1e6     # 80 * 30/40 output
        self.assertAlmostEqual(price(t, TIERED, per), base + above, places=12)


class Infra(unittest.TestCase):
    def test_limit_message_is_infra(self):
        s = {"result": {"is_error": True, "subtype": "success",
                        "result": "Claude AI usage limit reached|1760000000"}, "stderr": ""}
        self.assertTrue(infra_error(s))

    def test_budget_guard_is_not_infra(self):
        s = {"result": {"is_error": True, "subtype": "error_max_budget_usd", "result": ""},
             "stderr": ""}
        self.assertIsNone(infra_error(s))

    def test_normal_result_is_not_infra(self):
        s = {"result": {"is_error": False, "subtype": "success",
                        "result": "Added retry on HTTP 429 to the client"}, "stderr": ""}
        self.assertIsNone(infra_error(s))


if __name__ == "__main__":
    unittest.main()
