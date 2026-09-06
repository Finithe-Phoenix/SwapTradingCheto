import math
import random
import statistics


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
        "note": "Null means undefined or insufficient data. These metrics do not authorize live trading."
    }
