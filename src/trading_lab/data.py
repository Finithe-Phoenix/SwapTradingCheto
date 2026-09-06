"""Hourly CSV datasets with provenance; public GET requests only."""
from dataclasses import asdict
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .market import Candle, iso, utc_timestamp

PAIRS = ("BTC/USDT", "ETH/USDT")
PUBLIC_BASE = "https://data-api.binance.vision/api/v3/"


def filename(pair):
    if pair not in PAIRS:
        raise ValueError("Unsupported pair")
    return pair.replace("/", "_") + "-1h.csv"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(candles, start=None, end=None):
    if not candles:
        raise ValueError("Empty dataset")
    previous = None
    for c in candles:
        c.validate()
        if c.timestamp % 3600:
            raise ValueError("Candle not aligned to UTC hour")
        if previous is not None and c.timestamp != previous + 3600:
            raise ValueError(f"Gap, duplicate or unordered candle at {iso(c.timestamp)}")
        previous = c.timestamp
    if start is not None and candles[0].timestamp != start:
        raise ValueError("Missing start of requested coverage")
    if end is not None and candles[-1].timestamp + 3600 != end:
        raise ValueError("Missing end of requested coverage")
    return {"rows": len(candles), "start": iso(candles[0].timestamp),
            "end_exclusive": iso(candles[-1].timestamp + 3600), "gaps": 0}


def write_dataset(path, datasets, origin, rules=None):
    path = Path(path)
    if path.exists() and any(path.iterdir()):
        raise ValueError("Dataset directory must be empty; preserve previous experiments")
    path.mkdir(parents=True, exist_ok=True)
    if set(datasets) != set(PAIRS):
        raise ValueError("Both research pairs are required")
    manifest = {"schema": 1, "origin": origin, "timeframe": "1h", "timestamp_unit": "seconds",
                "downloaded_at": iso(int(time.time())), "files": {}, "market_rules": rules or {}}
    for pair, candles in datasets.items():
        stats = audit(candles)
        target = path / filename(pair)
        with target.open("w", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=list(asdict(candles[0])))
            writer.writeheader()
            writer.writerows(asdict(c) for c in candles)
        manifest["files"][pair] = {"name": target.name, "sha256": digest(target), **stats}
    (path / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def load_dataset(path):
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text())
    if manifest.get("schema") != 1 or manifest.get("timeframe") != "1h" or set(manifest["files"]) != set(PAIRS):
        raise ValueError("Unsupported dataset schema or universe")
    datasets = {}
    for pair in PAIRS:
        info = manifest["files"][pair]
        if info["name"] != filename(pair):
            raise ValueError("Unexpected dataset filename")
        target = path / info["name"]
        if digest(target) != info["sha256"]:
            raise ValueError(f"Checksum mismatch for {pair}")
        with target.open(newline="") as source:
            candles = [Candle(int(r["timestamp"]), *(float(r[k]) for k in ("open", "high", "low", "close", "volume")))
                       for r in csv.DictReader(source)]
        stats = audit(candles, utc_timestamp(info["start"]), utc_timestamp(info["end_exclusive"]))
        if stats["rows"] != info["rows"]:
            raise ValueError("Manifest row count mismatch")
        datasets[pair] = candles
    if [c.timestamp for c in datasets[PAIRS[0]]] != [c.timestamp for c in datasets[PAIRS[1]]]:
        raise ValueError("Both assets must have identical hourly coverage")
    return datasets, manifest


def public_get(endpoint, params, attempts=4):
    if endpoint not in {"klines", "exchangeInfo"}:
        raise ValueError("Only public market-data endpoints are supported")
    url = PUBLIC_BASE + endpoint + "?" + urlencode(params)
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "SwapTradingCheto/0.1 research"})
            with urlopen(request, timeout=20) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise ValueError(f"Public data request failed (HTTP {exc.code}); no alternative origin was substituted") from exc
            delay = min(10, max(1, int(exc.headers.get("Retry-After", 2 ** attempt))))
            time.sleep(delay)
        except (URLError, TimeoutError) as exc:
            if attempt == attempts - 1:
                raise ValueError("Market-data network request failed") from exc
            time.sleep(min(8, 2 ** attempt))
    raise ValueError("Market-data retries exhausted")


def download(path, start, end, fetch=public_get):
    if start >= end or start % 3600 or end % 3600:
        raise ValueError("Use increasing UTC hour-aligned dates")
    if end > int(time.time()) // 3600 * 3600:
        raise ValueError("Only completed hourly candles can be downloaded")
    datasets, rules = {}, {}
    for pair in PAIRS:
        symbol = pair.replace("/", "")
        metadata = fetch("exchangeInfo", {"symbol": symbol})
        market = metadata["symbols"][0]
        if market["symbol"] != symbol or market["status"] != "TRADING" or not market.get("isSpotTradingAllowed", False):
            raise ValueError(f"Unavailable spot market: {pair}")
        filters = {x["filterType"]: x for x in market["filters"]}
        lot = filters.get("MARKET_LOT_SIZE", filters["LOT_SIZE"])
        if float(lot["stepSize"]) == 0:
            lot = filters["LOT_SIZE"]
        notionals = [float(filters[k]["minNotional"]) for k in ("NOTIONAL", "MIN_NOTIONAL") if k in filters]
        rules[pair] = {"step": float(lot["stepSize"]), "min_qty": float(lot["minQty"]),
                       "min_notional": max(notionals, default=0), "metadata": market,
                       "historical_limit_caveat": "Current market filters; historical changes are not reconstructed"}
        cursor, candles = start, []
        while cursor < end:
            rows = fetch("klines", {"symbol": symbol, "interval": "1h", "startTime": cursor * 1000,
                                     "endTime": end * 1000 - 1, "limit": 1000})
            if not rows:
                raise ValueError(f"Insufficient coverage for {pair} at {iso(cursor)}")
            batch = [Candle(int(row[0]) // 1000, *(float(row[i]) for i in range(1, 6))) for row in rows]
            if batch[0].timestamp != cursor or batch[-1].timestamp >= end:
                raise ValueError("Unexpected page boundary")
            candles.extend(batch)
            cursor = batch[-1].timestamp + 3600
        audit(candles, start, end)
        datasets[pair] = candles
    return write_dataset(path, datasets, "binance-spot-public", rules)


def synthetic(path, days=520, seed=42):
    """Deterministic mechanics fixture, never evidence of market profitability."""
    if days < 2:
        raise ValueError("At least two days required")
    datasets = {}
    start = utc_timestamp("2020-01-01")
    for index, pair in enumerate(PAIRS):
        rng = random.Random(seed + index)
        price = 9000.0 if index == 0 else 200.0
        rows = []
        for hour in range(days * 24):
            drift = 0.00013 + 0.0005 * math.sin(hour / 130)
            change = drift + rng.gauss(0, 0.0035)
            close = max(1, price * math.exp(change))
            high = max(price, close) * (1 + rng.uniform(0.0002, 0.004))
            low = min(price, close) * (1 - rng.uniform(0.0002, 0.004))
            rows.append(Candle(start + hour * 3600, price, high, low, close, 10 + rng.random() * 100))
            price = close
        datasets[pair] = rows
    manifest = write_dataset(path, datasets, "SYNTHETIC-TEST-DATA")
    manifest["seed"] = seed
    # Deterministic fixtures also have deterministic provenance timestamps.
    manifest["downloaded_at"] = iso(start)
    (Path(path) / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
