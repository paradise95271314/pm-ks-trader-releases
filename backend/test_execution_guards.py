import unittest

from execute_arb import _kalshi_resting_volume, _pm_ask_volume


class ExecutionGuardTests(unittest.TestCase):
    def test_yes_purchase_uses_resting_no_volume(self):
        book = {"orderbook_fp": {
            "yes_dollars": [["0.20", "99"]],
            "no_dollars": [["0.65", "3"], ["0.66", "4"], ["0.70", "8"]],
        }}
        self.assertEqual(_kalshi_resting_volume(book, "yes", 0.34), 12.0)

    def test_no_purchase_uses_resting_yes_volume(self):
        book = {"orderbook_fp": {
            "yes_dollars": [["0.65", "3"], ["0.66", "4"], ["0.70", "8"]],
            "no_dollars": [["0.20", "99"]],
        }}
        self.assertEqual(_kalshi_resting_volume(book, "no", 0.34), 12.0)

    def test_pm_volume_only_counts_prices_within_limit(self):
        asks = [
            {"price": "0.50", "size": "4"},
            {"price": "0.51", "size": "7"},
            {"price": "0.55", "size": "100"},
        ]
        self.assertEqual(_pm_ask_volume(asks, 0.51), 11.0)


if __name__ == "__main__":
    unittest.main()
