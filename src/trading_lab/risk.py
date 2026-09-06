from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
import math


@dataclass(frozen=True)
class Costs:
    fee: float
    slippage_bps: float
    spread_bps: float

    @property
    def impact(self):
        return (self.slippage_bps + self.spread_bps / 2) / 10000

    def buy(self, raw):
        return raw * (1 + self.impact)

    def sell(self, raw):
        return raw * (1 - self.impact)

    def loss_per_unit(self, entry, stop):
        return entry * (1 + self.fee) - self.sell(stop) * (1 - self.fee)


@dataclass
class RiskState:
    high_water: float
    day_start: float
    last_equity: float
    day: int = -1
    daily_paused: bool = False
    halted: bool = False

    def __post_init__(self):
        values = (self.high_water, self.day_start, self.last_equity)
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0 for x in values):
            raise ValueError("Invalid persisted risk balances")
        if self.high_water < max(self.day_start, self.last_equity):
            raise ValueError("Persisted high-water mark is inconsistent")
        if type(self.day) is not int or self.day < -1 or type(self.daily_paused) is not bool or type(self.halted) is not bool:
            raise ValueError("Invalid persisted risk flags")

    def observe(self, timestamp, equity, config):
        day = timestamp // 86400
        if day != self.day:
            self.day = day
            self.day_start = self.last_equity
            self.daily_paused = False
        if not math.isfinite(equity) or equity <= 0:
            self.halted = True
            return
        self.high_water = max(self.high_water, equity)
        self.daily_paused |= equity <= self.day_start * (1 - config.daily_loss_limit)
        self.halted |= equity <= self.high_water * (1 - config.drawdown_limit)
        self.last_equity = equity

    @property
    def blocked(self):
        return self.halted or self.daily_paused


def position_size(config, costs, *, equity, cash, entry, stop, open_risk=0.0,
                  exposure=0.0, asset_exposure=0.0, step=0.00000001, min_notional=0.0, min_qty=0.0):
    """Return quantity or zero. Never round an undersized order up to market minimum."""
    values = (equity, cash, entry, stop, open_risk, exposure, asset_exposure, step, min_notional, min_qty)
    if not all(math.isfinite(v) for v in values) or min(values) < 0 or step <= 0:
        return 0.0
    if not 0 < stop < entry or equity <= 0:
        return 0.0
    budget = min(equity * config.risk_per_trade, equity * config.max_open_risk - open_risk)
    notional = min(cash / (1 + costs.fee), equity * config.max_asset_exposure - asset_exposure,
                   equity * config.max_total_exposure - exposure)
    if budget <= 0 or notional <= 0:
        return 0.0
    loss = costs.loss_per_unit(entry, stop)
    qty = min(budget / loss, notional / entry)
    quantum = Decimal(str(step))
    rounded = float((Decimal(str(qty)) / quantum).to_integral_value(rounding=ROUND_DOWN) * quantum)
    if rounded < min_qty or rounded * entry < min_notional:
        return 0.0
    return rounded
