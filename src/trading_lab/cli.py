import argparse
from dataclasses import asdict
import csv
import json
from pathlib import Path
import secrets
import subprocess
import sys

from . import __version__
from .config import LabConfig
from .data import download, load_dataset, synthetic
from .market import utc_timestamp
from .metrics import summarize
from .replay import replay
from .storage import Journal


def write_csv(path, rows):
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_experiment(data, output, config, start=None, end=None):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty; use a new run name")
    datasets, manifest = load_dataset(data)
    output.mkdir(parents=True, exist_ok=True)
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        commit = None
    report = {"engine_version": __version__, "commit": commit, "config": asdict(config),
              "config_sha256": config.fingerprint(), "data_manifest": manifest,
              "simulation_only": True, "live_eligible": False, "scenarios": {}}
    journal = Journal(output / "journal.sqlite")
    try:
        for name, multiplier, delay in (("base", 1, 0), ("double_cost", 2, 0), ("delayed_1h", 1, 1)):
            result = replay(datasets, config, start=start, end=end, cost_multiplier=multiplier,
                            delay_hours=delay, market_rules=manifest.get("market_rules"))
            folder = output / name
            folder.mkdir()
            write_csv(folder / "trades.csv", result["trades"])
            write_csv(folder / "equity.csv", result["equity"])
            (folder / "decisions.jsonl").write_text("".join(json.dumps(x, allow_nan=False) + "\n" for x in result["decisions"]))
            stats = summarize(result, config.initial_balance)
            report["scenarios"][name] = {"metrics": stats, "period": result["period"], **result["scenario"]}
            journal.save(name, {"risk": result["risk_state"], "metrics": stats},
                         ((f"{name}:{i}", e) for i, e in enumerate(result["decisions"])))
    finally:
        journal.close()
    (output / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    lines = ["# Simulation report", "", f"Data origin: **{manifest['origin']}**", "",
             "Research only. Synthetic data validates mechanics, not profitability.", "",
             "| Scenario | Net return | Max drawdown | Closed trades |", "|---|---:|---:|---:|"]
    for name, scenario in report["scenarios"].items():
        m = scenario["metrics"]
        lines.append(f"| {name} | {m['net_return']:.2%} | {m['max_drawdown']:.2%} | {m['closed_trades']} |")
    lines += ["", "Detailed assumptions, provenance and undefined metrics are in summary.json.",
              "Profit factor / confidence intervals are not automatic promotion gates."]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n")
    return report


def initialize(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    env = path / ".env"
    # Exclusive creation prevents replacing credentials on subsequent initialization.
    with env.open("x") as out:
        out.write(f"LAB_UI_PASSWORD={secrets.token_urlsafe(24)}\nLAB_UI_JWT_SECRET={secrets.token_urlsafe(48)}\n")
    env.chmod(0o600)
    (path / "user_data").mkdir(exist_ok=True)
    return str(env)


def main(argv=None):
    parser = argparse.ArgumentParser(description="SwapTradingCheto — simulation-only BTC/ETH research")
    parser.add_argument("--config", default="configs/lab.json")
    subs = parser.add_subparsers(dest="command", required=True)
    init = subs.add_parser("init", help="Create local UI credentials; never overwrite existing .env")
    init.add_argument("--directory", default=".")
    demo = subs.add_parser("demo", help="Generate deterministic synthetic data and run all scenarios")
    demo.add_argument("--output", default="runs/demo")
    dl = subs.add_parser("download", help="Download public hourly market data; no API keys")
    dl.add_argument("--start", required=True)
    dl.add_argument("--end", required=True)
    dl.add_argument("--output", required=True)
    check = subs.add_parser("audit")
    check.add_argument("--data", required=True)
    run = subs.add_parser("run")
    run.add_argument("--data", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--start")
    run.add_argument("--end")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            print("Local credentials created:", initialize(args.directory))
        elif args.command == "download":
            result = download(args.output, utc_timestamp(args.start), utc_timestamp(args.end))
            print(json.dumps(result, indent=2))
        elif args.command == "audit":
            _, manifest = load_dataset(args.data)
            print(json.dumps(manifest, indent=2))
        else:
            config = LabConfig.load(args.config)
            if args.command == "demo":
                base = Path(args.output)
                if base.exists() and any(base.iterdir()):
                    raise ValueError("Use a new output directory")
                synthetic(base / "synthetic-data")
                report = run_experiment(base / "synthetic-data", base / "results", config,
                                        start=utc_timestamp("2020-08-08"))
            else:
                report = run_experiment(args.data, args.output, config,
                                        start=utc_timestamp(args.start) if args.start else None,
                                        end=utc_timestamp(args.end) if args.end else None)
            print(json.dumps({"origin": report["data_manifest"]["origin"], "simulation_only": True,
                              "scenarios": {k: v["metrics"] for k, v in report["scenarios"].items()}}, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
