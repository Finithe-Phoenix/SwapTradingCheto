from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from trading_lab.cli import run_experiment
from trading_lab.config import LabConfig
from trading_lab.data import PAIRS, decode_klines, download, extract_cache, inspect_cache, load_dataset, synthetic, write_dataset
from trading_lab.market import Candle, utc_timestamp
from trading_lab.metrics import calendar_returns, risk_diagnostics
from trading_lab.research import ResearchPlan
from trading_lab.risk import RiskState
from trading_lab.status import paper_status
from trading_lab.storage import Journal


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data"
        self.calls = []

    def fetch(self, endpoint, params):
        self.calls.append((endpoint, dict(params)))
        if endpoint == "exchangeInfo":
            return {"symbols": [{"symbol": params["symbol"], "status": "TRADING", "isSpotTradingAllowed": True,
                                 "filters": [{"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                                             {"filterType": "MIN_NOTIONAL", "minNotional": "5"}]}]}
        start = params["startTime"] // 1000
        end = (params["endTime"] + 1) // 1000
        return [[ts * 1000, "100", "102", "99", "101", "5"] for ts in range(start, min(end, start + 7200), 3600)]

    def test_interrupted_download_resumes_without_refetching_verified_pages(self):
        def unreliable(endpoint, params):
            if endpoint == "klines" and params["startTime"] == 7200000:
                raise ValueError("network interrupted")
            return self.fetch(endpoint, params)

        with self.assertRaisesRegex(ValueError, "network interrupted"):
            download(self.path, 0, 14400, unreliable)
        self.calls.clear()
        download(self.path, 0, 14400, self.fetch, resume=True)
        rows, manifest = load_dataset(self.path)
        self.assertEqual(manifest["origin"], "binance-spot-public")
        self.assertEqual(len(rows[PAIRS[0]]), 4)
        btc = [p["startTime"] for e, p in self.calls if e == "klines" and p["symbol"] == "BTCUSDT"]
        self.assertEqual(btc, [7200000])

    def test_mismatched_resume_is_rejected_before_network(self):
        def failure(endpoint, params):
            raise ValueError("offline")
        with self.assertRaises(ValueError):
            download(self.path, 0, 14400, failure)
        with self.assertRaisesRegex(ValueError, "different request"):
            download(self.path, 0, 18000, self.fetch, resume=True)
        self.assertEqual(self.calls, [])

    def test_existing_output_is_rejected_before_network(self):
        self.path.mkdir()
        (self.path / "previous.txt").write_text("preserve")
        with self.assertRaises(ValueError):
            download(self.path, 0, 14400, self.fetch)
        self.assertEqual(self.calls, [])

    def test_tampered_cached_page_is_rejected(self):
        def unreliable(endpoint, params):
            if endpoint == "klines" and params["startTime"] == 7200000:
                raise ValueError("offline")
            return self.fetch(endpoint, params)
        with self.assertRaises(ValueError):
            download(self.path, 0, 14400, unreliable)
        cache = self.path.with_name("data.download")
        (cache / "BTCUSDT-0.json").write_text("[]")
        with self.assertRaisesRegex(ValueError, "checksum"):
            download(self.path, 0, 14400, self.fetch, resume=True)

    def test_gaps_are_preserved_and_diagnosed_without_fabrication(self):
        def gap(endpoint, params):
            rows = self.fetch(endpoint, params)
            return [r for r in rows if r[0] != 3600000] if endpoint == "klines" else rows
        with self.assertRaisesRegex(ValueError, "missing hours"):
            download(self.path, 0, 14400, gap)
        diagnostic = json.loads((self.path.with_name("data.download") / "coverage.json").read_text())
        self.assertEqual(diagnostic[PAIRS[0]]["missing_hours"], 1)
        self.assertFalse((self.path / "manifest.json").exists())

    def test_dataset_validates_both_assets_before_writing(self):
        rows = [Candle(i * 3600, 100, 101, 99, 100, 1) for i in range(4)]
        with self.assertRaises(ValueError):
            write_dataset(self.path, {PAIRS[0]: rows, PAIRS[1]: rows[:-1]}, "test")
        self.assertFalse(self.path.exists())

    def test_kline_decoder_rejects_truncated_or_misaligned_timestamps(self):
        for row in ([1, 100, 102, 99, 101, 5], [3600000], ["3600000", 100, 102, 99, 101, 5]):
            with self.assertRaises(ValueError):
                decode_klines([row])

    def test_extraction_preserves_real_origin_and_refuses_to_cross_gap(self):
        def gap(endpoint, params):
            rows = self.fetch(endpoint, params)
            return [r for r in rows if r[0] != 3600000] if endpoint == "klines" else rows
        with self.assertRaises(ValueError):
            download(self.path, 0, 14400, gap)
        cache = self.path.with_name("data.download")
        spans = inspect_cache(cache)["common_contiguous_spans"]
        self.assertEqual([s["hours"] for s in spans], [1, 2])
        with self.assertRaises(ValueError):
            extract_cache(cache, self.path, 0, 14400)
        extract_cache(cache, self.path, 7200, 14400)
        rows, manifest = load_dataset(self.path)
        self.assertEqual(len(rows[PAIRS[0]]), 2)
        self.assertEqual(manifest["origin"], "binance-spot-public")
        self.assertIn("extraction", manifest)


class TemporalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / "data"
        synthetic(cls.path, days=50)
        cls.datasets, _ = load_dataset(cls.path)
        cls.config = replace(LabConfig(), trend_period=5, breakout_period=5, exit_period=3, atr_period=3)
        cls.plan = ResearchPlan("2020-01-10", "2020-02-01", "2020-02-10", "2020-02-20", 8)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_reserved_period_cannot_be_selected_as_an_ordinary_stage(self):
        with self.assertRaisesRegex(ValueError, "reserved"):
            self.plan.period("holdout")

    def test_invalid_boundaries_and_insufficient_warmup_are_rejected(self):
        with self.assertRaises(ValueError):
            replace(self.plan, validation_start=self.plan.development_start)
        with self.assertRaisesRegex(ValueError, "warmup"):
            replace(self.plan, warmup_days=1).prepare(self.datasets, self.config, "development")

    def test_stage_slices_future_and_requires_full_history(self):
        selected, start, end = self.plan.prepare(self.datasets, self.config, "development")
        self.assertEqual(start, utc_timestamp("2020-01-10"))
        self.assertTrue(all(rows[-1].timestamp < end for rows in selected.values()))
        truncated = {p: rows[100:] for p, rows in self.datasets.items()}
        with self.assertRaisesRegex(ValueError, "coverage"):
            self.plan.prepare(truncated, self.config, "development")

    def test_evaluation_report_reconciles_calendar_returns_and_freezes_plan(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "run"
            result = run_experiment(self.path, out, self.config, research_plan=self.plan, stage="development")
            self.assertEqual(result["research_plan_sha256"], self.plan.fingerprint())
            self.assertEqual(result["evaluation_stage"], "development")
            self.assertTrue(all(w["daily_warmup_sufficient"] for w in result["warmup"].values()))
            for scenario in result["scenarios"].values():
                m = scenario["metrics"]
                compounded = 1.0
                for month in m["monthly"]:
                    compounded *= 1 + month["net_return"]
                self.assertAlmostEqual(compounded - 1, m["net_return"])
                self.assertAlmostEqual(sum(x["net_pnl"] for x in m["monthly"]), m["net_pnl"])
            self.assertFalse(result["evidence"]["live_eligible"])
            self.assertTrue((out / "base/monthly.csv").is_file())

    def test_calendar_boundary_uses_prior_period_close_and_carries_equity(self):
        start = utc_timestamp("2020-01-31T23:00:00Z")
        curve = [dict(timestamp=start + i * 3600, equity=v, buy_hold=v, halted=True)
                 for i, v in enumerate([100, 110, 99])]
        rows = calendar_returns(curve)
        self.assertEqual([r["period"] for r in rows], ["2020-01", "2020-02"])
        self.assertAlmostEqual(rows[0]["net_return"], .1)
        self.assertAlmostEqual(rows[1]["net_return"], -.1)
        self.assertEqual(rows[1]["starting_equity"], rows[0]["ending_equity"])

    def test_underwater_duration_counts_recovery_but_not_flat_peaks(self):
        def curve(values):
            return [dict(timestamp=i * 3600, equity=v, positions=0, exposure=0, halted=False, daily_paused=False)
                    for i, v in enumerate(values)]
        self.assertEqual(risk_diagnostics(curve([100, 100, 101]))["max_underwater_hours"], 0)
        result = risk_diagnostics(curve([100, 90, 95, 100]))
        self.assertEqual(result["max_underwater_hours"], 3)
        self.assertEqual(result["underwater_hours_at_end"], 0)


class PaperHealthTests(unittest.TestCase):
    def test_missing_status_is_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(paper_status(folder)["ready_for_new_entries"])
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_health_staleness_and_persistent_drawdown_block_admissions(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = Journal(Path(folder) / "risk.paper.sqlite")
            self.addCleanup(journal.close)
            state = dict(high_water=1000, day_start=1000, last_equity=1000, halted=False)
            journal.save("risk", {"state": state})
            journal.save("health", {"timestamp": 1000, "status": "ready"})
            self.assertTrue(paper_status(folder, now=1001)["ready_for_new_entries"])
            self.assertEqual(paper_status(folder, now=1100)["reason"], "stale_health")
            self.assertEqual(paper_status(folder, now=900)["reason"], "clock_skew")
            journal.save("risk", {"state": {**state, "halted": True}})
            self.assertEqual(paper_status(folder, now=1001)["reason"], "drawdown_pause")

    def test_corrupt_risk_cannot_be_restored_as_an_unpaused_account(self):
        for kwargs in ({"high_water": float("nan")}, {"halted": "false"}, {"high_water": 900}, {"day": -2}):
            values = dict(high_water=1000, day_start=1000, last_equity=1000)
            values.update(kwargs)
            with self.assertRaises(ValueError):
                RiskState(**values)


if __name__ == "__main__":
    unittest.main()
