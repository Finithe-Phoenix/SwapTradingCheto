from dataclasses import replace
import json
import math
from pathlib import Path
import tempfile
import unittest

from trading_lab.config import LabConfig
from trading_lab.data import audit, download, load_dataset, synthetic
from trading_lab.market import Candle, aggregate, atr, ema, signals
from trading_lab.metrics import block_interval, summarize
from trading_lab.replay import replay
from trading_lab.risk import Costs, RiskState, position_size
from trading_lab.storage import Journal
from trading_lab.cli import initialize, main, run_experiment


class ConfigTests(unittest.TestCase):
    def test_live_rejected(self):
        for value in (False, 1, "true"):
            with self.assertRaises(ValueError):
                LabConfig(dry_run=value)

    def test_bad_numbers_rejected(self):
        for value in (math.nan, math.inf, -1, True):
            with self.assertRaises(ValueError):
                LabConfig(initial_balance=value)

    def test_bad_limits_rejected(self):
        for kwargs in ({"risk_per_trade": .1}, {"max_asset_exposure": .8}, {"trend_period": 2.5}):
            with self.assertRaises(ValueError):
                LabConfig(**kwargs)

    def test_config_fingerprint(self):
        cfg = LabConfig()
        self.assertEqual(cfg.fingerprint(), LabConfig().fingerprint())
        self.assertNotEqual(cfg.fingerprint(), replace(cfg, fee=.002).fingerprint())


class MarketTests(unittest.TestCase):
    def test_ema_seed_is_sma(self):
        self.assertEqual(ema([1, 2, 3, 4], 3), [None, None, 2, 3])

    def test_true_range_includes_gaps(self):
        rows = [Candle(0, 100, 102, 99, 100, 1), Candle(3600, 120, 125, 120, 123, 1)]
        self.assertEqual(atr(rows, 1), [3, 25])

    def test_incomplete_buckets_omitted(self):
        rows = [Candle(i * 3600, 100, 101, 99, 100, 1) for i in range(7)]
        result = aggregate(rows, 14400)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].volume, 4)

    def test_invalid_ohlcv_rejected(self):
        for candle in (Candle(0, 100, 90, 80, 100, 1), Candle(0, 1, 2, 1, math.nan, 1)):
            with self.assertRaises(ValueError):
                candle.validate()

    def test_duplicate_and_gap_rejected(self):
        first = Candle(0, 100, 101, 99, 100, 1)
        for second in (first, replace(first, timestamp=7200)):
            with self.assertRaises(ValueError):
                audit([first, second])


class RiskTests(unittest.TestCase):
    def setUp(self):
        self.config = LabConfig()
        self.costs = Costs(.001, 5, 2)

    def size(self, **kwargs):
        values = dict(equity=1000, cash=1000, entry=100, stop=98)
        values.update(kwargs)
        return position_size(self.config, self.costs, **values)

    def test_quantity_respects_budget_with_costs(self):
        qty = self.size()
        self.assertGreater(qty, 0)
        self.assertLessEqual(qty * self.costs.loss_per_unit(100, 98), 2.5 + 1e-9)
        self.assertLess(qty, 1.25)

    def test_minimum_is_rejected_not_rounded_up(self):
        self.assertEqual(self.size(min_notional=500), 0)

    def test_joint_risk_budget(self):
        self.assertEqual(self.size(open_risk=5), 0)

    def test_exposure_and_precision(self):
        qty = self.size(exposure=390, step=.01)
        self.assertLessEqual(qty * 100, 10)
        self.assertAlmostEqual(qty / .01, round(qty / .01))

    def test_invalid_stop_and_nan_fail_closed(self):
        for kwargs in ({"stop": 100}, {"entry": math.nan}, {"cash": -1}):
            self.assertEqual(self.size(**kwargs), 0)

    def test_daily_budget_latches_until_next_day(self):
        state = RiskState(1000, 1000, 1000)
        state.observe(0, 989, self.config)
        self.assertTrue(state.daily_paused)
        state.observe(3600, 1000, self.config)
        self.assertTrue(state.daily_paused)
        state.observe(86400, 1000, self.config)
        self.assertFalse(state.daily_paused)

    def test_drawdown_pause_survives_days(self):
        state = RiskState(1000, 1000, 1000)
        state.observe(0, 940, self.config)
        state.observe(86400, 1000, self.config)
        self.assertTrue(state.halted)


class DatasetAndReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / "data"
        synthetic(cls.path, days=50)
        cls.data, cls.manifest = load_dataset(cls.path)
        cls.config = replace(LabConfig(), trend_period=5, breakout_period=5, exit_period=3, atr_period=3)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_data_are_explicitly_synthetic(self):
        self.assertEqual(self.manifest["origin"], "SYNTHETIC-TEST-DATA")

    def test_checksum_failure_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            synthetic(Path(folder) / "data", days=2)
            file = Path(folder) / "data" / "BTC_USDT-1h.csv"
            with file.open("a") as out:
                out.write("corrupt\n")
            with self.assertRaisesRegex(ValueError, "Checksum"):
                load_dataset(Path(folder) / "data")

    def test_prefix_signals_equal_full_history(self):
        rows = self.data["BTC/USDT"]
        full = signals(rows, self.config)
        for length in (145, 243, 498, 723):
            prefix = rows[:length]
            observed = signals(prefix, self.config)
            boundary = prefix[-1].timestamp + 3600
            expected = {k: v for k, v in full.items() if k <= boundary}
            self.assertEqual(observed, expected)

    def test_future_daily_extreme_cannot_change_past_signal(self):
        rows = self.data["BTC/USDT"]
        prefix = rows[:241]
        changed = prefix + [replace(c, open=c.open * 100, high=c.high * 100,
                                    low=c.low * 100, close=c.close * 100) for c in rows[241:]]
        left, right = signals(rows, self.config), signals(changed, self.config)
        for ts in left:
            if ts <= prefix[-1].timestamp + 3600:
                self.assertEqual(left[ts], right[ts])

    def test_replay_is_deterministic_and_self_financing(self):
        result = replay(self.data, self.config)
        self.assertEqual(result, replay(self.data, self.config))
        self.assertGreater(len(result["trades"]), 0)
        self.assertTrue(all(r["cash"] >= -1e-8 for r in result["equity"]))
        self.assertAlmostEqual(sum(t["pnl"] for t in result["trades"]), result["equity"][-1]["equity"] - 1000)
        self.assertTrue(all(d["timestamp"] >= d["signal_at"] for d in result["decisions"]))

    def test_sizing_is_recomputed_when_costs_change(self):
        normal = replay(self.data, self.config)
        stress = replay(self.data, self.config, cost_multiplier=2)
        a = next(d for d in normal["decisions"] if d["action"] == "buy")
        b = next(d for d in stress["decisions"] if d["action"] == "buy")
        self.assertLess(b["quantity"], a["quantity"])
        self.assertGreater(b["entry"], a["entry"])

    def test_gap_stop_can_exceed_planned_loss(self):
        base = replay(self.data, self.config)
        first = base["trades"][0]
        target = first["opened_at"] + 3600
        changed = {p: list(rows) for p, rows in self.data.items()}
        pair = first["pair"]
        idx = next(i for i, c in enumerate(changed[pair]) if c.timestamp == target)
        price = first["stop"] * .7
        changed[pair][idx] = Candle(target, price, price * 1.01, price * .99, price, 1)
        stressed = replay(changed, self.config)
        gaps = [t for t in stressed["trades"] if t["reason"] == "gap_stop"]
        self.assertTrue(gaps)
        self.assertTrue(any(-t["pnl"] > t["initial_risk"] for t in gaps))

    def test_delay_really_moves_execution(self):
        result = replay(self.data, self.config, delay_hours=1)
        self.assertTrue(result["decisions"])
        self.assertTrue(all(d["timestamp"] == d["signal_at"] + 3600 for d in result["decisions"]))

    def test_bad_coverage_rejected(self):
        data = {p: list(rows) for p, rows in self.data.items()}
        data["ETH/USDT"] = data["ETH/USDT"][1:]
        with self.assertRaises(ValueError):
            replay(data, self.config)

    def test_report_has_provenance_and_no_live_promotion(self):
        with tempfile.TemporaryDirectory() as folder:
            result = run_experiment(self.path, Path(folder) / "run", self.config)
            self.assertFalse(result["live_eligible"])
            self.assertEqual(result["config_sha256"], self.config.fingerprint())
            self.assertTrue((Path(folder) / "run" / "REPORT.md").is_file())

    def test_metrics_reconcile(self):
        result = replay(self.data, self.config)
        metrics = summarize(result, 1000)
        self.assertAlmostEqual(metrics["net_pnl"], sum(t["pnl"] for t in result["trades"]))
        self.assertGreaterEqual(metrics["max_drawdown"], 0)

    def test_insufficient_sample_has_no_confidence_interval(self):
        self.assertIsNone(block_interval([.01] * 20))


class PersistenceTests(unittest.TestCase):
    def test_atomic_snapshot_and_event_idempotency(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "risk.sqlite"
            journal = Journal(path)
            for _ in range(2):
                journal.save("risk", {"halted": True}, [("one", {"quantity": 1})])
            journal.close()
            restored = Journal(path)
            self.assertEqual(restored.get("risk"), {"halted": True})
            self.assertEqual(restored.db.execute("SELECT count(*) FROM events").fetchone()[0], 1)
            restored.close()

    def test_credentials_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            initialize(folder)
            original = (Path(folder) / ".env").read_text()
            with self.assertRaises(FileExistsError):
                initialize(folder)
            self.assertEqual((Path(folder) / ".env").read_text(), original)


if __name__ == "__main__":
    unittest.main()
