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

from . import __version__
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
    if set(datasets) != set(PAIRS):
        raise ValueError("Both research pairs are required")
    # Validate everything before publishing even the first CSV.
    stats_by_pair = {pair: audit(rows) for pair, rows in datasets.items()}
    if len({(s["start"], s["end_exclusive"]) for s in stats_by_pair.values()}) != 1:
        raise ValueError("Both assets must have identical hourly coverage")
    path.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": 1, "origin": origin, "timeframe": "1h", "timestamp_unit": "seconds",
                "downloaded_at": iso(int(time.time())), "files": {}, "market_rules": rules or {}}
    for pair, candles in datasets.items():
        stats = stats_by_pair[pair]
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
    if (manifest.get("schema") != 1 or manifest.get("timeframe") != "1h"
            or manifest.get("timestamp_unit") != "seconds" or set(manifest["files"]) != set(PAIRS)):
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
            request = Request(url, headers={"User-Agent": f"SwapTradingCheto/{__version__} research"})
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


def atomic_json(path, value):
    """Replace a checkpoint only after its complete JSON has reached disk."""
    import os

    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as out:
        json.dump(value, out, allow_nan=False, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    temporary.replace(path)


def coverage(candles, start, end):
    """Describe missing hours without inventing prices or silently repairing them."""
    cursor, gaps = start, []
    for candle in candles:
        candle.validate()
        if candle.timestamp % 3600 or not cursor <= candle.timestamp < end:
            raise ValueError("Duplicate, unordered, unaligned or out-of-range candle")
        if candle.timestamp > cursor:
            gaps.append({"start": iso(cursor), "end_exclusive": iso(candle.timestamp),
                         "hours": (candle.timestamp - cursor) // 3600})
        cursor = candle.timestamp + 3600
    if cursor < end:
        gaps.append({"start": iso(cursor), "end_exclusive": iso(end), "hours": (end - cursor) // 3600})
    return {"rows": len(candles), "expected_rows": (end - start) // 3600,
            "missing_hours": sum(g["hours"] for g in gaps), "gaps": gaps}


def decode_klines(rows):
    candles = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6 or type(row[0]) is not int or row[0] % 3600000:
            raise ValueError("Expected hourly kline timestamps in integer milliseconds")
        candles.append(Candle(row[0] // 1000, *(float(row[i]) for i in range(1, 6))))
    return candles


def cached_candles(cache, pair, state):
    """Read only pages named and hashed by the checkpoint, in request order."""
    symbol = pair.replace("/", "")
    cursor, rows = state["request"]["start"], []
    for page in state["pages"].get(pair, []):
        expected = f"{symbol}-{cursor}.json"
        if page["name"] != expected or digest(Path(cache) / expected) != page["sha256"]:
            raise ValueError("Download checkpoint page checksum or sequence mismatch")
        batch = [Candle(**row) for row in json.loads((Path(cache) / expected).read_text())]
        coverage(batch, cursor, state["request"]["end"])
        if not batch:
            raise ValueError("Empty checkpoint page")
        rows.extend(batch)
        cursor = batch[-1].timestamp + 3600
    return rows


def read_cache(cache):
    state = json.loads((Path(cache) / "checkpoint.json").read_text())
    request = state["request"]
    if (request.get("schema") != 1 or request.get("origin") != PUBLIC_BASE or request.get("pairs") != list(PAIRS)
            or type(request.get("start")) is not int or type(request.get("end")) is not int
            or request["start"] >= request["end"] or request["start"] % 3600 or request["end"] % 3600):
        raise ValueError("Unsupported download checkpoint")
    return state, {pair: cached_candles(cache, pair, state) for pair in PAIRS}


def inspect_cache(cache):
    state, datasets = read_cache(cache)
    common = sorted(set.intersection(*(set(c.timestamp for c in rows) for rows in datasets.values())))
    spans = []
    for ts in common:
        if not spans or ts != spans[-1][1]:
            spans.append([ts, ts + 3600])
        else:
            spans[-1][1] += 3600
    return {"request": state["request"], "retrieval_complete": state.get("retrieval_complete", False),
            "coverage": {pair: coverage(rows, state["request"]["start"], state["request"]["end"]) for pair, rows in datasets.items()},
            "common_contiguous_spans": [{"start": iso(a), "end_exclusive": iso(b), "hours": (b - a) // 3600} for a, b in spans],
            "note": "Choose diagnostic intervals by coverage before inspecting strategy returns. Missing hours are never filled."}


def market_rule(market, observed_at):
    filters = {x["filterType"]: x for x in market["filters"]}
    lot = filters.get("MARKET_LOT_SIZE", filters["LOT_SIZE"])
    if float(lot["stepSize"]) == 0:
        lot = filters["LOT_SIZE"]
    notionals = [float(filters[k]["minNotional"]) for k in ("NOTIONAL", "MIN_NOTIONAL") if k in filters]
    return {"step": float(lot["stepSize"]), "min_qty": float(lot["minQty"]),
            "min_notional": max(notionals, default=0), "metadata": market, "observed_at": observed_at,
            "historical_limit_caveat": "Current market filters; historical changes are not reconstructed"}


def extract_cache(cache, path, start, end):
    """Publish an explicitly requested continuous subset without fetching or filling."""
    if start >= end or start % 3600 or end % 3600:
        raise ValueError("Use increasing UTC hour-aligned extraction dates")
    state, datasets = read_cache(cache)
    if start < state["request"]["start"] or end > state["request"]["end"]:
        raise ValueError("Extraction outside the cached request")
    selected = {p: [c for c in rows if start <= c.timestamp < end] for p, rows in datasets.items()}
    for rows in selected.values():
        audit(rows, start, end)
    rules = {p: market_rule(state["markets"][p], state["started_at"]) for p in PAIRS}
    manifest = write_dataset(path, selected, "binance-spot-public", rules)
    manifest["extraction"] = {"source_request": state["request"], "start": iso(start), "end_exclusive": iso(end),
                              "checkpoint_sha256": digest(Path(cache) / "checkpoint.json"),
                              "note": "Explicit continuous subset. It does not represent the complete requested history."}
    atomic_json(Path(path) / "manifest.json", manifest)
    return manifest


def download(path, start, end, fetch=public_get, *, resume=False, progress=None):
    if start >= end or start % 3600 or end % 3600:
        raise ValueError("Use increasing UTC hour-aligned dates")
    if end > int(time.time()) // 3600 * 3600:
        raise ValueError("Only completed hourly candles can be downloaded")
    path = Path(path)
    if path.exists() and any(path.iterdir()):
        raise ValueError("Dataset directory must be empty; preserve previous experiments")
    cache = path.with_name(path.name + ".download")
    checkpoint = cache / "checkpoint.json"
    identity = {"schema": 1, "origin": PUBLIC_BASE, "start": start, "end": end, "pairs": list(PAIRS)}
    if checkpoint.exists():
        if not resume:
            raise ValueError("Download checkpoint exists; repeat with --resume and the same dates")
        state = json.loads(checkpoint.read_text())
        if state.get("request") != identity:
            raise ValueError("Checkpoint belongs to a different request")
    else:
        if cache.exists() and any(cache.iterdir()):
            raise ValueError("Unrecognized download cache; preserve it and use a new output name")
        cache.mkdir(parents=True, exist_ok=True)
        state = {"request": identity, "started_at": iso(int(time.time())), "markets": {}, "pages": {}}
        atomic_json(checkpoint, state)
    datasets, rules = {}, {}
    for pair in PAIRS:
        symbol = pair.replace("/", "")
        if pair not in state["markets"]:
            state["markets"][pair] = fetch("exchangeInfo", {"symbol": symbol})["symbols"][0]
            atomic_json(checkpoint, state)
        market = state["markets"][pair]
        if market["symbol"] != symbol or market["status"] != "TRADING" or not market.get("isSpotTradingAllowed", False):
            raise ValueError(f"Unavailable spot market: {pair}")
        rules[pair] = market_rule(market, state["started_at"])
        candles = cached_candles(cache, pair, state)
        cursor = candles[-1].timestamp + 3600 if candles else start
        pages = state["pages"].setdefault(pair, [])
        if progress:
            progress(pair, len(candles), (end - start) // 3600)
        while cursor < end:
            rows = fetch("klines", {"symbol": symbol, "interval": "1h", "startTime": cursor * 1000,
                                     "endTime": end * 1000 - 1, "limit": 1000})
            if not rows:
                break  # Diagnose trailing coverage together with any interior gaps.
            batch = decode_klines(rows)
            coverage(batch, cursor, end)
            target = cache / f"{symbol}-{cursor}.json"
            atomic_json(target, [asdict(c) for c in batch])
            pages.append({"name": target.name, "sha256": digest(target)})
            atomic_json(checkpoint, state)
            candles.extend(batch)
            cursor = batch[-1].timestamp + 3600
            if progress:
                progress(pair, len(candles), (end - start) // 3600)
        datasets[pair] = candles
    state["retrieval_complete"] = True
    atomic_json(checkpoint, state)
    diagnostics = {p: coverage(rows, start, end) for p, rows in datasets.items()}
    atomic_json(cache / "coverage.json", diagnostics)
    if any(d["missing_hours"] for d in diagnostics.values()):
        raise ValueError(f"Historical coverage has missing hours; preserved pages and details in {cache / 'coverage.json'}")
    for candles in datasets.values():
        audit(candles, start, end)
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
