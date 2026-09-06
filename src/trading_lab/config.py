from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class LabConfig:
    dry_run: bool = True
    initial_balance: float = 1000.0
    pairs: tuple[str, ...] = ("BTC/USDT", "ETH/USDT")
    risk_per_trade: float = 0.0025
    max_open_risk: float = 0.005
    max_asset_exposure: float = 0.20
    max_total_exposure: float = 0.40
    daily_loss_limit: float = 0.01
    drawdown_limit: float = 0.05
    max_open_trades: int = 2
    fee: float = 0.001
    slippage_bps: float = 5.0
    spread_bps: float = 2.0
    trend_period: int = 200
    breakout_period: int = 20
    exit_period: int = 10
    atr_period: int = 14
    atr_multiple: float = 2.0

    def __post_init__(self):
        if self.dry_run is not True:
            raise ValueError("This laboratory supports simulation only")
        if set(self.pairs) != {"BTC/USDT", "ETH/USDT"} or len(self.pairs) != 2:
            raise ValueError("The research universe is exactly BTC/USDT and ETH/USDT")
        for name, value in asdict(self).items():
            if name in ("dry_run", "pairs"):
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be numeric")
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        for name in ("trend_period", "breakout_period", "exit_period", "atr_period", "max_open_trades"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("risk_per_trade", "max_open_risk", "max_asset_exposure", "max_total_exposure", "daily_loss_limit", "drawdown_limit"):
            if not 0 < getattr(self, name) < 1:
                raise ValueError(f"Invalid ratio: {name}")
        if self.initial_balance <= 0 or self.atr_multiple <= 0:
            raise ValueError("Balance and ATR multiple must be positive")
        if not self.risk_per_trade <= self.max_open_risk <= self.max_total_exposure:
            raise ValueError("Inconsistent risk limits")
        if self.max_asset_exposure > self.max_total_exposure or self.max_open_trades > 2:
            raise ValueError("Inconsistent exposure limits")
        if self.fee >= 0.1 or self.slippage_bps + self.spread_bps / 2 >= 1000:
            raise ValueError("Cost assumptions outside supported range")

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text())
        if "pairs" in data:
            data["pairs"] = tuple(data["pairs"])
        return cls(**data)

    def fingerprint(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()
