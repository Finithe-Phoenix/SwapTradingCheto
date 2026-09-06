"""Read-only paper health check. Never creates or resets a trading database."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import time

from .risk import RiskState


def paper_status(directory, *, now=None, max_age=60):
    path = Path(directory) / "risk.paper.sqlite"
    if not path.is_file():
        return {"ready_for_new_entries": False, "reason": "risk_database_missing", "simulation_only": True}
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
        db.execute("PRAGMA query_only=ON")
        values = {name: json.loads(body) for name, body in db.execute(
            "SELECT name,body FROM snapshots WHERE name IN ('risk','health')")}
    if not all(name in values for name in ("risk", "health")):
        return {"ready_for_new_entries": False, "reason": "risk_or_health_snapshot_missing", "simulation_only": True}
    risk = RiskState(**values["risk"]["state"])
    health = values["health"]
    if type(health.get("timestamp")) is not int or health.get("status") not in ("ready", "blocked"):
        raise ValueError("Invalid persisted health snapshot")
    age = (time.time() if now is None else now) - health["timestamp"]
    reason = "clock_skew" if age < 0 else "stale_health" if age > max_age else (
        "drawdown_pause" if risk.halted else "daily_pause" if risk.daily_paused else (
            "valuation_unavailable" if health["status"] != "ready" else "ready"))
    return {"ready_for_new_entries": reason == "ready", "reason": reason, "health_age_seconds": round(age, 3),
            "health": health, "simulation_only": True,
            "note": "Recent strategy heartbeat only; this does not prove uninterrupted exchange connectivity or future execution."}
