"""Chronological hourly replay. Recomputes portfolio/risk under each cost scenario."""
from dataclasses import asdict, dataclass
import math

from .data import audit
from .market import iso, signals
from .risk import Costs, RiskState, position_size


@dataclass
class Position:
    pair: str
    opened_at: int
    quantity: float
    entry: float
    stop: float
    entry_fee: float
    initial_risk: float


def replay(datasets, config, *, start=None, end=None, cost_multiplier=1.0, delay_hours=0, market_rules=None):
    if not math.isfinite(cost_multiplier) or cost_multiplier < 0 or type(delay_hours) is not int or delay_hours < 0:
        raise ValueError("Invalid scenario")
    if set(datasets) != set(config.pairs):
        raise ValueError("Dataset universe mismatch")
    pairs = sorted(config.pairs)
    for rows in datasets.values():
        audit(rows)
    timeline = [c.timestamp for c in datasets[pairs[0]]]
    if any([c.timestamp for c in datasets[p]] != timeline for p in pairs):
        raise ValueError("Portfolio replay requires matching timestamps")
    costs = Costs(config.fee * cost_multiplier, config.slippage_bps * cost_multiplier, config.spread_bps * cost_multiplier)
    if costs.fee >= 0.1 or costs.impact >= 0.1:
        raise ValueError("Stress costs outside supported range")
    schedule = {p: {ts + delay_hours * 3600: s for ts, s in signals(datasets[p], config).items()} for p in pairs}
    cash, positions, trades, decisions, curve = config.initial_balance, {}, [], [], []
    risk = RiskState(cash, cash, cash)
    market_rules = market_rules or {}
    benchmark_qty = None

    def equity(prices):
        # Liquidation valuation includes estimated exit costs for open positions.
        return cash + sum(pos.quantity * costs.sell(prices[p]) * (1 - costs.fee) for p, pos in positions.items())

    def sell(pair, raw_price, timestamp, reason):
        nonlocal cash
        pos = positions.pop(pair)
        price = costs.sell(raw_price)
        proceeds = pos.quantity * price
        exit_fee = proceeds * costs.fee
        cash += proceeds - exit_fee
        pnl = proceeds - exit_fee - pos.quantity * pos.entry - pos.entry_fee
        trades.append({**asdict(pos), "closed_at": timestamp, "exit": price, "exit_fee": exit_fee,
                       "pnl": pnl, "r_multiple": pnl / pos.initial_risk, "reason": reason})

    selected = [(i, ts) for i, ts in enumerate(timeline) if (start is None or ts >= start) and (end is None or ts < end)]
    if not selected:
        raise ValueError("No candles in evaluation period")
    if start is not None and selected[0][1] != start:
        raise ValueError("Evaluation start unavailable or not hour-aligned")
    if end is not None and selected[-1][1] + 3600 != end:
        raise ValueError("Evaluation end unavailable or not hour-aligned")
    first_ts = selected[0][1]
    curve.append({"timestamp": first_ts, "equity": cash, "cash": cash, "exposure": 0.0, "open_risk": 0.0,
                  "positions": 0, "halted": False, "daily_paused": False, "buy_hold": cash})

    for i, timestamp in selected:
        bars = {p: datasets[p][i] for p in pairs}
        opens = {p: c.open for p, c in bars.items()}
        closes = {p: c.close for p, c in bars.items()}
        if benchmark_qty is None:
            benchmark_qty = {p: config.initial_balance / len(pairs) / (costs.buy(opens[p]) * (1 + costs.fee)) for p in pairs}
        risk.observe(timestamp, equity(opens), config)
        exited = set()
        for p in list(positions):
            intent = schedule[p].get(timestamp)
            if opens[p] <= positions[p].stop:
                sell(p, opens[p], timestamp, "gap_stop")
                exited.add(p)
            elif intent and intent.exit:
                sell(p, opens[p], timestamp, "channel_exit")
                exited.add(p)
        risk.observe(timestamp, equity(opens), config)
        for p in pairs:
            signal = schedule[p].get(timestamp)
            if not signal or not signal.enter:
                continue
            reason = None
            if risk.blocked:
                reason = "drawdown_pause" if risk.halted else "daily_pause"
            elif p in positions or p in exited:
                reason = "already_open_or_just_exited"
            elif len(positions) >= config.max_open_trades:
                reason = "position_limit"
            entry = costs.buy(opens[p])
            stop = entry - config.atr_multiple * signal.atr
            current_equity = equity(opens)
            rules = market_rules.get(p, {})
            qty = 0.0 if reason else position_size(
                config, costs, equity=current_equity, cash=cash, entry=entry, stop=stop,
                open_risk=sum(t.initial_risk for t in positions.values()),
                exposure=sum(t.quantity * opens[q] for q, t in positions.items()),
                step=rules.get("step", 0.00000001), min_qty=rules.get("min_qty", 0.0),
                min_notional=rules.get("min_notional", 0.0))
            if qty <= 0:
                reason = reason or "risk_budget_or_market_minimum"
            else:
                entry_fee = qty * entry * costs.fee
                reserved_risk = qty * costs.loss_per_unit(entry, stop)
                cash -= qty * entry + entry_fee
                positions[p] = Position(p, timestamp, qty, entry, stop, entry_fee, reserved_risk)
            decisions.append({"timestamp": timestamp, "signal_at": signal.available_at, "pair": p,
                              "action": "reject" if reason else "buy", "reason": reason or "S1_breakout",
                              "entry": entry, "stop": stop, "quantity": qty, "equity_before": current_equity,
                              "risk": qty * costs.loss_per_unit(entry, stop) if qty else 0.0})
        # Adverse intrabar stop evaluation, including the entry hour. Gaps use the open.
        for p in list(positions):
            if bars[p].low <= positions[p].stop:
                sell(p, min(bars[p].open, positions[p].stop), timestamp + 3600, "intrabar_stop")
        value = equity(closes)
        # Last second belongs to the old UTC day; next bar starts a new daily budget.
        risk.observe(timestamp + 3599, value, config)
        benchmark = sum(benchmark_qty[p] * costs.sell(closes[p]) * (1 - costs.fee) for p in pairs)
        curve.append({"timestamp": timestamp + 3600, "equity": value, "cash": cash,
                      "exposure": sum(t.quantity * closes[p] for p, t in positions.items()),
                      "open_risk": sum(t.initial_risk for t in positions.values()), "positions": len(positions),
                      "halted": risk.halted, "daily_paused": risk.daily_paused, "buy_hold": benchmark})
        if cash < -1e-7:
            raise RuntimeError("Negative cash invariant violated")
    for p in list(positions):
        sell(p, datasets[p][selected[-1][0]].close, selected[-1][1] + 3600, "end_of_test")
    curve[-1].update(equity=cash, cash=cash, exposure=0.0, open_risk=0.0, positions=0)
    return {"trades": trades, "decisions": decisions, "equity": curve, "risk_state": asdict(risk),
            "scenario": {"cost_multiplier": cost_multiplier, "delay_hours": delay_hours},
            "period": {"start": iso(first_ts), "end_exclusive": iso(selected[-1][1] + 3600)}}
