import tempfile
import unittest
from pathlib import Path

from sentinel_fund.paper_fund import Decision, PaperFund


class PaperFundTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fund = PaperFund(Path(self.tmp.name) / "fund.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def test_starts_with_virtual_100k_and_live_disabled(self):
        snap = self.fund.snapshot()
        self.assertEqual(snap["starting_cash"], 100_000.0)
        self.assertEqual(snap["cash"], 100_000.0)
        self.assertFalse(snap["live_trading_enabled"])
        self.assertEqual(snap["mode"], "PAPER ONLY")

    def test_accepts_small_paper_buy_and_persists_position(self):
        result = self.fund.submit_paper_decision(
            Decision("BTC", "BUY", 0.05, 50_000, "Test only; validated fixture")
        )
        self.assertTrue(result["accepted"])
        self.assertAlmostEqual(result["snapshot"]["cash"], 97_500)
        self.assertEqual(result["snapshot"]["positions"][0]["symbol"], "BTC")

    def test_rejects_position_over_limit(self):
        result = self.fund.submit_paper_decision(
            Decision("BTC", "BUY", 0.3, 50_000, "Too large for 10% cap")
        )
        self.assertFalse(result["accepted"])
        self.assertIn("per-position", result["reason"])

    def test_rejects_sell_without_existing_holding(self):
        result = self.fund.submit_paper_decision(
            Decision("BTC", "SELL", 0.01, 50_000, "No position held")
        )
        self.assertFalse(result["accepted"])
        self.assertIn("cannot sell more", result["reason"])

    def test_rejects_buy_without_cash(self):
        fund = PaperFund(Path(self.tmp.name) / "small.sqlite3",
                         limits=__import__("sentinel_fund.paper_fund", fromlist=["RiskLimits"]).RiskLimits(starting_cash=1_000))
        result = fund.submit_paper_decision(
            Decision("BTC", "BUY", 0.03, 50_000, "Exceeds available cash")
        )
        self.assertFalse(result["accepted"])
        self.assertIn("Insufficient cash", result["reason"])


if __name__ == "__main__":
    unittest.main()
