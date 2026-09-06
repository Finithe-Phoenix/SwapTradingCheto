import argparse
from dataclasses import asdict
import csv
import json
from pathlib import Path
import secrets
import sqlite3
import sys

from . import __version__
from .config import LabConfig
from .data import download, extract_cache, inspect_cache, load_dataset, synthetic
from .market import utc_timestamp
from .metrics import summarize
from .replay import replay
from .reporting import provenance, render_report
from .research import ResearchPlan, evidence_checks, warmup_diagnostics
from .storage import Journal
from .status import paper_status


def write_csv(path, rows):
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_experiment(data, output, config, start=None, end=None, *, research_plan=None, stage=None):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty; use a new run name")
    datasets, manifest = load_dataset(data)
    if research_plan is not None:
        if start is not None or end is not None:
            raise ValueError("A declared research stage supplies its own dates")
        datasets, start, end = research_plan.prepare(datasets, config, stage)
    elif stage is not None:
        raise ValueError("A research stage requires its plan")
    output.mkdir(parents=True, exist_ok=True)
    source = provenance()
    first = start if start is not None else next(iter(datasets.values()))[0].timestamp
    report = {"engine_version": __version__, "commit": source["commit"], "provenance": source, "config": asdict(config),
              "config_sha256": config.fingerprint(), "data_manifest": manifest,
              "simulation_only": True, "live_eligible": False, "scenarios": {},
              "evaluation_stage": stage or "exploratory", "warmup": warmup_diagnostics(datasets, first, config)}
    if research_plan is not None:
        report["research_plan"] = asdict(research_plan)
        report["research_plan_sha256"] = research_plan.fingerprint()
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
            write_csv(folder / "monthly.csv", stats["monthly"])
            write_csv(folder / "annual.csv", stats["annual"])
            report["scenarios"][name] = {"metrics": stats, "period": result["period"], **result["scenario"]}
            journal.save(name, {"risk": result["risk_state"], "metrics": stats},
                         ((f"{name}:{i}", e) for i, e in enumerate(result["decisions"])))
    finally:
        journal.close()
    report["evidence"] = evidence_checks(report["scenarios"], config)
    (output / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    (output / "REPORT.md").write_text(render_report(report))
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
    status = subs.add_parser("paper-status", help="Read the last paper-risk heartbeat without changing its state")
    status.add_argument("--directory", default="user_data")
    demo = subs.add_parser("demo", help="Generate deterministic synthetic data and run all scenarios")
    demo.add_argument("--output", default="runs/demo")
    dl = subs.add_parser("download", help="Download public hourly market data; no API keys")
    dl.add_argument("--start", required=True)
    dl.add_argument("--end", required=True)
    dl.add_argument("--output", required=True)
    dl.add_argument("--resume", action="store_true", help="Reuse verified download pages from an interrupted request")
    check = subs.add_parser("audit")
    check.add_argument("--data", required=True)
    inspect = subs.add_parser("inspect-download", help="Report verified cached coverage and common continuous spans")
    inspect.add_argument("--cache", required=True)
    extract = subs.add_parser("extract", help="Extract an explicitly selected, gap-free diagnostic subset")
    extract.add_argument("--cache", required=True)
    extract.add_argument("--start", required=True)
    extract.add_argument("--end", required=True)
    extract.add_argument("--output", required=True)
    run = subs.add_parser("run")
    run.add_argument("--data", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--start")
    run.add_argument("--end")
    evaluate = subs.add_parser("evaluate", help="Evaluate one declared stage with full warmup; keep final holdout reserved")
    evaluate.add_argument("--data", required=True)
    evaluate.add_argument("--output", required=True)
    evaluate.add_argument("--stage", choices=("development", "validation"), default="development")
    evaluate.add_argument("--plan", default="configs/research.json")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            print("Local credentials created:", initialize(args.directory))
        elif args.command == "paper-status":
            result = paper_status(args.directory)
            print(json.dumps(result, indent=2))
            return 0 if result["ready_for_new_entries"] else 3
        elif args.command == "download":
            result = download(args.output, utc_timestamp(args.start), utc_timestamp(args.end), resume=args.resume,
                              progress=lambda pair, done, total: print(f"{pair}: {done}/{total} hours", file=sys.stderr))
            print(json.dumps(result, indent=2))
        elif args.command == "audit":
            _, manifest = load_dataset(args.data)
            print(json.dumps(manifest, indent=2))
        elif args.command == "inspect-download":
            print(json.dumps(inspect_cache(args.cache), indent=2))
        elif args.command == "extract":
            print(json.dumps(extract_cache(args.cache, args.output, utc_timestamp(args.start), utc_timestamp(args.end)), indent=2))
        else:
            config = LabConfig.load(args.config)
            if args.command == "demo":
                base = Path(args.output)
                if base.exists() and any(base.iterdir()):
                    raise ValueError("Use a new output directory")
                synthetic(base / "synthetic-data")
                report = run_experiment(base / "synthetic-data", base / "results", config,
                                        start=utc_timestamp("2020-08-08"))
            elif args.command == "evaluate":
                report = run_experiment(args.data, args.output, config,
                                        research_plan=ResearchPlan.load(args.plan), stage=args.stage)
            else:
                report = run_experiment(args.data, args.output, config,
                                        start=utc_timestamp(args.start) if args.start else None,
                                        end=utc_timestamp(args.end) if args.end else None)
            print(json.dumps({"origin": report["data_manifest"]["origin"], "simulation_only": True,
                              "scenarios": {k: v["metrics"] for k, v in report["scenarios"].items()}}, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
