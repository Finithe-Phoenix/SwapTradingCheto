"""Predeclared chronological stages and evidence diagnostics; no optimizer or live gate."""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

from .market import aggregate, iso, utc_timestamp


@dataclass(frozen=True)
class ResearchPlan:
    development_start: str = "2020-01-01"
    validation_start: str = "2024-01-01"
    holdout_start: str = "2026-01-01"
    holdout_end: str = "2026-09-01"
    warmup_days: int = 365

    def __post_init__(self):
        dates = [utc_timestamp(x) for x in (self.development_start, self.validation_start, self.holdout_start, self.holdout_end)]
        if any(x % 86400 for x in dates) or any(b <= a for a, b in zip(dates, dates[1:])):
            raise ValueError("Research boundaries must be strictly increasing UTC midnights")
        if type(self.warmup_days) is not int or self.warmup_days <= 0:
            raise ValueError("warmup_days must be a positive integer")

    @classmethod
    def load(cls, path):
        return cls(**json.loads(Path(path).read_text()))

    def fingerprint(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()

    def period(self, stage):
        periods = {"development": (self.development_start, self.validation_start),
                   "validation": (self.validation_start, self.holdout_start)}
        if stage not in periods:
            raise ValueError("Use development or validation; this runner keeps the final holdout reserved")
        return tuple(utc_timestamp(x) for x in periods[stage])

    def prepare(self, datasets, config, stage):
        start, end = self.period(stage)
        warmup = start - self.warmup_days * 86400
        required = max(config.trend_period * 86400,
                       (max(config.breakout_period, config.exit_period, config.atr_period) + 1) * 14400)
        if self.warmup_days * 86400 < required:
            raise ValueError("Research warmup is shorter than the strategy requires")
        selected = {pair: [c for c in rows if warmup <= c.timestamp < end] for pair, rows in datasets.items()}
        for rows in selected.values():
            if not rows or rows[0].timestamp != warmup or rows[-1].timestamp + 3600 != end:
                raise ValueError(f"Stage requires complete coverage {iso(warmup)} through {iso(end)}")
        return selected, start, end


def warmup_diagnostics(datasets, start, config):
    return {pair: {"complete_daily_candles_before_start": len(aggregate([c for c in rows if c.timestamp < start], 86400)),
                   "required_daily_candles": config.trend_period,
                   "daily_warmup_sufficient": len(aggregate([c for c in rows if c.timestamp < start], 86400)) >= config.trend_period}
            for pair, rows in datasets.items()}


def evidence_checks(scenarios, config):
    """Declared research filters. Their success cannot establish future profitability."""
    base = scenarios["base"]["metrics"]
    checks = []

    def add(name, value, passed, rule):
        checks.append({"name": name, "value": value, "passed": bool(passed), "rule": rule})

    add("closed_trade_sample", base["closed_trades"], base["closed_trades"] >= 100, ">= 100; review target, not proof")
    add("net_expectancy", base["expectancy_quote"], base["expectancy_quote"] is not None and base["expectancy_quote"] > 0, "> 0 after modeled costs")
    add("profit_factor", base["profit_factor"], base["profit_factor"] is not None and base["profit_factor"] >= 1.2, ">= 1.20; proposed research filter")
    add("drawdown", base["max_drawdown"], base["max_drawdown"] <= config.drawdown_limit, f"<= {config.drawdown_limit}")
    add("drawdown_halt", base["risk_diagnostics"]["drawdown_halt_at_end"], not base["risk_diagnostics"]["drawdown_halt_at_end"], "no persistent drawdown halt")
    for scenario in ("double_cost", "delayed_1h"):
        value = scenarios[scenario]["metrics"]["net_return"]
        add(scenario, value, value > 0, "positive net return under the stated stress")
    intervals = base["bootstrap_daily_mean"]
    add("bootstrap_sensitivity", [x["lower"] if x else None for x in intervals],
        all(x and x["lower"] > 0 for x in intervals), "exploratory lower bound > 0 for blocks of 3, 7 and 14 days")
    return {"checks": checks, "all_research_filters_pass": all(c["passed"] for c in checks),
            "live_eligible": False, "interpretation": "Research diagnostics only; prospective evidence and independent review are still required."}
