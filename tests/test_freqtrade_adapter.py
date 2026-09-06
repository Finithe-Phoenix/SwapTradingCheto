from dataclasses import replace
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from trading_lab.data import synthetic, load_dataset
from trading_lab.market import aggregate, signals

ROOT = Path(__file__).resolve().parents[1]
HAS_FREQTRADE = importlib.util.find_spec("freqtrade") is not None
if HAS_FREQTRADE:
    import pandas as pd
    from freqtrade.enums import RunMode
    from freqtrade.persistence import Trade
    from freqtrade.configuration.config_validation import validate_config_schema
    spec = importlib.util.spec_from_file_location("lab_strategy", ROOT / "user_data/strategies/SwingBreakoutS1.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    SwingBreakoutS1 = module.SwingBreakoutS1


@unittest.skipUnless(HAS_FREQTRADE, "Install requirements-freqtrade.txt for the native adapter tests")
class FreqtradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        synthetic(Path(cls.temp.name) / "data", days=50)
        cls.data, _ = load_dataset(Path(cls.temp.name) / "data")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def config(self):
        cfg = json.loads((ROOT / "configs/freqtrade.paper.json").read_text())
        cfg.update(user_data_dir=Path(self.temp.name), runmode=RunMode.DRY_RUN)
        cfg["api_server"].update(password="test-only-password-long", jwt_secret_key="test-only-jwt-key-32-characters-long")
        return cfg

    def setUp(self):
        self.strategy = SwingBreakoutS1(self.config())
        self.strategy.lab = replace(self.strategy.lab, trend_period=5, breakout_period=5, exit_period=3, atr_period=3)
        self.frames, daily = {}, {}
        for pair, rows in self.data.items():
            def frame(candles):
                return pd.DataFrame([dict(date=pd.Timestamp(c.timestamp, unit="s", tz="UTC"),
                                          open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume) for c in candles])
            self.frames[pair] = frame(aggregate(rows, 14400))
            daily[pair] = frame(aggregate(rows, 86400))
        self.strategy.dp = SimpleNamespace(get_pair_dataframe=lambda pair, timeframe: daily[pair])
        for pair in self.data:
            self.frames[pair] = self.strategy.populate_indicators(self.frames[pair], {"pair": pair})
        self.strategy.dp.get_analyzed_dataframe = lambda pair, timeframe: (self.frames[pair], None)
        self.strategy.ready = True
        sig = next(s for s in signals(self.data["BTC/USDT"], self.strategy.lab).values() if s.enter)
        self.now = datetime.fromtimestamp(sig.available_at, timezone.utc)
        self.rate = float(self.strategy._row("BTC/USDT", self.now)["close"])
        self.strategy.snapshot = {"equity": 1000, "cash": 1000, "exposure": 0, "risk": 0,
                                  "pairs": set(), "time": self.now.timestamp()}

    def stake(self, min_stake=0):
        return self.strategy.custom_stake_amount("BTC/USDT", self.now, self.rate, 500, min_stake, 1000, 1, "S1_breakout", "long")

    def confirm(self, amount):
        return self.strategy.confirm_trade_entry("BTC/USDT", "market", amount, self.rate, "GTC", self.now, "S1_breakout", "long")

    def test_actual_freqtrade_schema(self):
        validate_config_schema(self.config())

    def test_constructor_rejects_live_and_futures(self):
        for update in ({"dry_run": False}, {"trading_mode": "futures"}, {"force_entry_enable": True}):
            cfg = self.config()
            cfg.update(update)
            with self.assertRaises(ValueError):
                SwingBreakoutS1(cfg)

    def test_adapter_uses_same_signals_as_replay(self):
        for pair, rows in self.data.items():
            expected = signals(rows, self.strategy.lab)
            for row in self.frames[pair].itertuples():
                s = expected[int(row.date.timestamp()) + 14400]
                self.assertEqual(row.lab_enter, s.enter)
                self.assertAlmostEqual(row.lab_atr, s.atr)

    def test_entry_is_sized_and_confirmed(self):
        stake = self.stake()
        self.assertGreater(stake, 0)
        self.assertTrue(self.confirm(stake / self.rate))
        self.assertIn("BTC/USDT", self.strategy.reservations)
        self.assertFalse(self.confirm(stake / self.rate))

    def test_resized_minimum_cannot_bypass_risk(self):
        stake = self.stake()
        self.assertFalse(self.confirm(2 * stake / self.rate))
        self.assertEqual(self.stake(min_stake=500), 0)

    def test_snapshot_failure_and_staleness_block(self):
        self.strategy.snapshot["time"] -= 30
        self.assertEqual(self.stake(), 0)
        self.strategy.snapshot = None
        self.assertEqual(self.stake(), 0)

    def test_loop_uses_native_profit_object_and_refreshes_risk(self):
        trade = SimpleNamespace(pair="BTC/USDT", amount=.01,
                                calculate_profit=lambda rate: SimpleNamespace(profit_abs=-3),
                                get_custom_data=lambda key: 2.0)
        self.strategy.dp.ticker = lambda pair: {"bid": 10000, "timestamp": self.now.timestamp() * 1000}
        self.strategy.wallets = SimpleNamespace(get_free=lambda currency: 900)
        with patch.object(Trade, "get_trades_proxy", return_value=[trade]), patch.object(Trade, "get_total_closed_profit", return_value=1):
            self.strategy.bot_loop_start(self.now)
        self.assertEqual(self.strategy.snapshot["equity"], 998)
        self.assertEqual(self.strategy.snapshot["risk"], 2)

    def test_missing_trade_metadata_invalidates_snapshot(self):
        trade = SimpleNamespace(pair="BTC/USDT", amount=.01,
                                calculate_profit=lambda rate: SimpleNamespace(profit_abs=0),
                                get_custom_data=lambda key: None)
        self.strategy.dp.ticker = lambda pair: {"bid": 10000, "timestamp": self.now.timestamp() * 1000}
        with patch.object(Trade, "get_trades_proxy", return_value=[trade]), patch.object(Trade, "get_total_closed_profit", return_value=0):
            self.strategy.bot_loop_start(self.now)
        self.assertIsNone(self.strategy.snapshot)

    def test_stop_uses_persisted_entry_value(self):
        trade = SimpleNamespace(get_custom_data=lambda key: 96.0)
        value = self.strategy.custom_stoploss("BTC/USDT", trade, self.now, 100.0, 0.0)
        self.assertAlmostEqual(value, .04)
        self.assertEqual(self.strategy.custom_exit("BTC/USDT", trade, self.now, 95, -.05), "fixed_stop_breached")
