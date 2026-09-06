"""Freqtrade adapter for the shared S1 signals. Intentionally rejects live mode."""
from dataclasses import asdict, replace
from datetime import datetime, timezone
import math
from pathlib import Path

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute

from trading_lab.config import LabConfig
from trading_lab.market import Candle, evaluate
from trading_lab.risk import Costs, RiskState, position_size
from trading_lab.storage import Journal


def candles(frame):
    return [Candle(int(r.date.timestamp()), float(r.open), float(r.high), float(r.low), float(r.close), float(r.volume))
            for r in frame.itertuples()]


class SwingBreakoutS1(IStrategy):
    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "4h"
    startup_candle_count = 400
    process_only_new_candles = True
    minimal_roi = {}
    stoploss = -0.99  # Replaced by the persisted ATR stop immediately after entry.
    use_custom_stoploss = True
    use_exit_signal = True
    exit_profit_only = False
    position_adjustment_enable = False

    def __init__(self, config):
        if config.get("dry_run") is not True or config.get("trading_mode", "spot") != "spot":
            raise ValueError("SwingBreakoutS1 is restricted to spot simulation")
        if config.get("force_entry_enable", False):
            raise ValueError("Manual force-entry is not supported by the lab")
        super().__init__(config)
        config_path = Path(__file__).resolve().parents[2] / "configs" / "lab.json"
        if not config_path.exists():
            config_path = Path("/lab/configs/lab.json")
        self.lab = LabConfig.load(config_path)
        mode = getattr(config.get("runmode"), "value", config.get("runmode"))
        if mode == "dry_run" and config.get("dry_run_wallet", 1000) != self.lab.initial_balance:
            raise ValueError("Paper wallet must match lab initial_balance")
        if mode != "dry_run":
            self.lab = replace(self.lab, initial_balance=float(config.get("dry_run_wallet", 1000)))
        self.costs = Costs(self.lab.fee, self.lab.slippage_bps, self.lab.spread_bps)
        self.state = RiskState(self.lab.initial_balance, self.lab.initial_balance, self.lab.initial_balance)
        self.journal = None
        self.ready = False
        self.intents = {}
        self.reservations = {}
        self.snapshot = None

    def informative_pairs(self):
        return [(p, "1d") for p in self.lab.pairs]

    def populate_indicators(self, dataframe, metadata):
        daily = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe="1d")
        values = evaluate(candles(dataframe), candles(daily), self.lab)
        dataframe["lab_atr"] = [s.atr for s in values]
        dataframe["lab_enter"] = [s.enter for s in values]
        dataframe["lab_exit"] = [s.exit for s in values]
        dataframe["lab_trend"] = [s.trend for s in values]
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        dataframe["enter_long"] = dataframe["lab_enter"].astype(int)
        dataframe.loc[dataframe["lab_enter"], "enter_tag"] = "S1_breakout"
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        dataframe["exit_long"] = dataframe["lab_exit"].astype(int)
        dataframe.loc[dataframe["lab_exit"], "exit_tag"] = "S1_channel"
        return dataframe

    def bot_start(self, **kwargs):
        self.ready = False
        mode = self.config.get("runmode")
        if getattr(mode, "value", mode) == "dry_run":
            self.journal = Journal(Path(self.config["user_data_dir"]) / "risk.paper.sqlite")
            saved = self.journal.get("risk")
            if saved:
                if saved["config_sha256"] != self.lab.fingerprint():
                    raise ValueError("Risk configuration changed; archive the previous paper experiment first")
                self.state = RiskState(**saved["state"])
        self.ready = True

    def _row(self, pair, current_time):
        frame, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        closed = frame[frame["date"].map(lambda x: x.timestamp() + 14400 <= current_time.timestamp())]
        if closed.empty:
            raise ValueError("No closed signal candle")
        row = closed.iloc[-1]
        return row

    def _persist(self):
        if self.journal:
            self.journal.save("risk", {"config_sha256": self.lab.fingerprint(), "state": asdict(self.state)})

    def bot_loop_start(self, current_time: datetime, **kwargs):
        self.snapshot = None  # A failed refresh must never reuse a previous admission snapshot.
        if not self.ready:
            return
        try:
            trades = Trade.get_trades_proxy(is_open=True)
            equity = self.lab.initial_balance + Trade.get_total_closed_profit()
            exposure = risk = 0.0
            for trade in trades:
                if trade.pair not in self.lab.pairs:
                    raise ValueError("Unknown position in paper database")
                mode = self.config.get("runmode")
                if getattr(mode, "value", mode) == "dry_run":
                    ticker = self.dp.ticker(trade.pair)
                    rate = ticker.get("bid") or ticker.get("last")
                    stamp = ticker.get("timestamp")
                    if stamp is not None and abs(current_time.timestamp() - stamp / 1000) > 60:
                        raise ValueError("Stale valuation ticker")
                else:
                    rate = float(self._row(trade.pair, current_time)["close"])
                if not rate or not math.isfinite(rate) or rate <= 0:
                    raise ValueError("Invalid valuation price")
                equity += trade.calculate_profit(rate).profit_abs
                exposure += trade.amount * rate
                reserved = trade.get_custom_data("initial_risk")
                if reserved is None:
                    raise ValueError("Missing persisted trade risk")
                risk += float(reserved)
            self.state.observe(int(current_time.timestamp()), equity, self.lab)
            self._persist()
            self.reservations = {p: r for p, r in self.reservations.items() if r["expires"] > current_time.timestamp()}
            self.snapshot = {"equity": equity, "cash": self.wallets.get_free("USDT"), "exposure": exposure,
                             "risk": risk, "pairs": {t.pair for t in trades}, "time": current_time.timestamp()}
        except Exception:
            self.snapshot = None
            self.logger.warning("Risk snapshot unavailable; new entries are blocked", exc_info=True) if hasattr(self, "logger") else None

    def _context(self, pair, current_time):
        if not self.ready or self.snapshot is None or self.state.blocked or pair not in self.lab.pairs:
            return None
        if abs(current_time.timestamp() - self.snapshot["time"]) > 15:
            return None
        if pair in self.snapshot["pairs"] or pair in self.reservations:
            return None
        if len(self.snapshot["pairs"]) + len(self.reservations) >= self.lab.max_open_trades:
            return None
        ctx = dict(self.snapshot)
        ctx["risk"] += sum(r["risk"] for r in self.reservations.values())
        ctx["exposure"] += sum(r["notional"] for r in self.reservations.values())
        ctx["cash"] -= sum(r["notional"] * (1 + self.costs.fee) for r in self.reservations.values())
        return ctx

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        try:
            ctx = self._context(pair, current_time)
            if ctx is None or side != "long" or leverage != 1:
                return 0.0
            row = self._row(pair, current_time)
            age = current_time.timestamp() - (row["date"].timestamp() + 14400)
            if age > 300 or not bool(row["lab_enter"]):
                return 0.0
            volatility = float(row["lab_atr"])
            stop = current_rate - self.lab.atr_multiple * volatility
            qty = position_size(self.lab, self.costs, equity=ctx["equity"], cash=min(ctx["cash"], max_stake),
                                entry=current_rate, stop=stop, open_risk=ctx["risk"], exposure=ctx["exposure"],
                                min_notional=min_stake or 0)
            self.intents[pair] = {"atr": volatility, "available_at": row["date"].timestamp() + 14400}
            return qty * current_rate
        except Exception:
            return 0.0

    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs):
        try:
            ctx = self._context(pair, current_time)
            intent = self.intents.get(pair)
            if ctx is None or not intent or side != "long" or current_time.timestamp() - intent["available_at"] > 300:
                return False
            stop = rate - self.lab.atr_multiple * intent["atr"]
            qty = position_size(self.lab, self.costs, equity=ctx["equity"], cash=ctx["cash"], entry=rate, stop=stop,
                                open_risk=ctx["risk"], exposure=ctx["exposure"])
            if not math.isfinite(amount) or amount <= 0 or amount > qty + 1e-10:
                return False  # Recheck the actual amount after Freqtrade's minimum/precision handling.
            self.reservations[pair] = {"risk": amount * self.costs.loss_per_unit(rate, stop),
                                       "notional": amount * rate, "expires": current_time.timestamp() + 120}
            return True
        except Exception:
            return False

    def order_filled(self, pair, trade, order, current_time, **kwargs):
        if order.ft_order_side != trade.entry_side:
            return
        intent = self.intents.get(pair)
        if intent is None:
            row = self._row(pair, trade.open_date_utc)
            intent = {"atr": float(row["lab_atr"])}
        stop = trade.open_rate - self.lab.atr_multiple * intent["atr"]
        trade.set_custom_data("initial_atr", intent["atr"])
        trade.set_custom_data("fixed_stop", stop)
        trade.set_custom_data("initial_risk", trade.amount * self.costs.loss_per_unit(trade.open_rate, stop))
        self.reservations.pop(pair, None)
        # Force a refreshed snapshot before the next admission in this loop.
        self.bot_loop_start(current_time)

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill=False, **kwargs):
        stop = trade.get_custom_data("fixed_stop")
        if stop is None:
            row = self._row(pair, trade.open_date_utc)
            stop = trade.open_rate - self.lab.atr_multiple * float(row["lab_atr"])
        if current_rate <= stop:
            return 0.000001
        return stoploss_from_absolute(stop, current_rate, is_short=False, leverage=1.0)

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        stop = trade.get_custom_data("fixed_stop")
        if stop is not None and current_rate <= stop:
            return "fixed_stop_breached"
        return None
