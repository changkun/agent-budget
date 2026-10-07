"""Usage parsing for the real executor."""
import json
import unittest
from pathlib import Path

from harness.real_executor import UsageUnavailable, price, usage_by_model

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


if __name__ == "__main__":
    unittest.main()
