import math
import random
import statistics

from .market import iso


def drawdown(values):
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = max(worst, 1 - value / peak)
    return worst


def block_interval(returns, block=7, samples=500, seed=42):
    """Exploratory circular moving-block bootstrap of daily portfolio mean."""
    if len(returns) < 30:
        return None
    rng, means = random.Random(seed), []
    n = len(returns)
    for _ in range(samples):
        sample = []
        while len(sample) < n:
            start = rng.randrange(n)
            sample.extend(returns[(start + j) % n] for j in range(block))
        means.append(statistics.mean(sample[:n]))
    means.sort()
    return {"lower": means[int(samples * 0.025)], "upper": means[min(samples - 1, int(samples * 0.975))],
            "block_days": block, "samples": samples, "seed": seed}


def calendar_returns(curve, frequency="month"):
    """Partition one continuous equity curve. Never reset positions or risk limits."""
    if frequency not in ("month", "year"):
        raise ValueError("Use month or year")
    groups = {}
    for left, right in zip(curve, curve[1:]):
        if right["timestamp"] - left["timestamp"] != 3600:
            raise ValueError("Calendar statistics require contiguous hourly equity marks")
        key = iso(left["timestamp"])[:7 if frequency == "month" else 4]
        groups.setdefault(key, [left]).append(right)
    return [{"period": key, "start": iso(rows[0]["timestamp"]), "end_exclusive": iso(rows[-1]["timestamp"]),
             "hours": len(rows) - 1, "starting_equity": rows[0]["equity"], "ending_equity": rows[-1]["equity"],
             "net_pnl": rows[-1]["equity"] - rows[0]["equity"],
             "net_return": rows[-1]["equity"] / rows[0]["equity"] - 1,
             "buy_hold_return": rows[-1]["buy_hold"] / rows[0]["buy_hold"] - 1,
             "max_drawdown_within_period": drawdown([r["equity"] for r in rows]),
             "halted_hourly_marks": sum(r["halted"] for r in rows[1:])}
            for key, rows in groups.items()]


def risk_diagnostics(curve):
    peak, peak_time, longest = curve[0]["equity"], curve[0]["timestamp"], 0
    underwater = False
    for row in curve:
        # Measure recovery time before resetting the peak clock.
        if underwater or row["equity"] < peak:
            longest = max(longest, row["timestamp"] - peak_time)
        underwater = row["equity"] < peak
        if row["equity"] >= peak:
            peak, peak_time = row["equity"], row["timestamp"]
    marks = curve[1:]
    first_halt = next((row["timestamp"] for row in marks if row["halted"]), None)
    return {"first_drawdown_halt_at": iso(first_halt) if first_halt is not None else None,
            "drawdown_halt_at_end": curve[-1]["halted"],
            "halted_hourly_marks": sum(row["halted"] for row in marks),
            "daily_paused_hourly_marks": sum(row["daily_paused"] for row in marks),
            "max_underwater_hours": longest / 3600,
            "underwater_hours_at_end": (curve[-1]["timestamp"] - peak_time) / 3600,
            "fraction_hourly_marks_in_position": statistics.mean(row["positions"] > 0 for row in marks) if marks else 0,
            "mean_exposure_fraction_at_hourly_marks": statistics.mean(row["exposure"] / row["equity"] for row in marks) if marks else 0}


def summarize(result, initial):
    trades, curve = result["trades"], result["equity"]
    pnl = [t["pnl"] for t in trades]
    wins = sum(x for x in pnl if x > 0)
    losses = -sum(x for x in pnl if x < 0)
    # UTC midnight points bound complete 24-hour returns. Partial days are excluded.
    daily_points = [row for row in curve if row["timestamp"] % 86400 == 0]
    returns = [b["equity"] / a["equity"] - 1 for a, b in zip(daily_points, daily_points[1:])
               if b["timestamp"] - a["timestamp"] == 86400]
    mean = statistics.mean(returns) if returns else 0.0
    std = statistics.stdev(returns) if len(returns) > 1 else 0.0
    downside = math.sqrt(statistics.mean([min(0, r) ** 2 for r in returns])) if returns else 0.0
    return {
        "initial_balance": initial, "ending_balance": curve[-1]["equity"],
        "net_pnl": curve[-1]["equity"] - initial, "net_return": curve[-1]["equity"] / initial - 1,
        "closed_trades": len(trades), "win_rate": sum(x > 0 for x in pnl) / len(pnl) if pnl else None,
        "profit_factor": wins / losses if losses else None,
        "expectancy_quote": statistics.mean(pnl) if pnl else None,
        "expectancy_r": statistics.mean(t["r_multiple"] for t in trades) if trades else None,
        "max_drawdown": drawdown([x["equity"] for x in curve]),
        "fees": sum(t["entry_fee"] + t["exit_fee"] for t in trades),
        "sharpe_daily_365": math.sqrt(365) * mean / std if std else None,
        "sortino_daily_365": math.sqrt(365) * mean / downside if downside else None,
        "complete_days": len(returns), "risk_free_rate_assumption": 0.0,
        "bootstrap_daily_mean": [block_interval(returns, block=n) for n in (3, 7, 14)],
        "buy_hold_50_50_return": curve[-1]["buy_hold"] / initial - 1,
        "buy_hold_max_drawdown": drawdown([x["buy_hold"] for x in curve]),
        "cash_reference_return": 0.0,
        "pnl_by_pair": {p: sum(t["pnl"] for t in trades if t["pair"] == p) for p in ("BTC/USDT", "ETH/USDT")},
        "rejected_entries": sum(d["action"] == "reject" for d in result["decisions"]),
        "rejection_reasons": {reason: sum(d["action"] == "reject" and d["reason"] == reason for d in result["decisions"])
                              for reason in sorted({d["reason"] for d in result["decisions"] if d["action"] == "reject"})},
        "mean_holding_hours": statistics.mean((t["closed_at"] - t["opened_at"]) / 3600 for t in trades) if trades else None,
        "risk_diagnostics": risk_diagnostics(curve),
        "monthly": calendar_returns(curve),
        "annual": calendar_returns(curve, "year"),
        "note": "Null means undefined or insufficient data. These metrics do not authorize live trading."
    }
