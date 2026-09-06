"""Run the pinned integration with an enforced paper profile and generated UI auth."""
import json
import os
from pathlib import Path
import sys

ALLOWED = {"trade", "backtesting", "download-data", "lookahead-analysis", "recursive-analysis", "list-strategies"}
FORBIDDEN = {"-c", "--config", "--strategy", "-s", "--strategy-path", "--trading-mode", "--dry-run-wallet",
             "--db-url", "--userdir", "--user-data-dir", "--freqaimodel", "--enable-position-stacking"}
OPTIONS = {"--timerange", "--timeframes", "--timeframe-detail", "--data-format-ohlcv", "--pairs", "-p",
           "--days", "--prepend", "--breakdown", "--export", "--cache", "--no-color", "--print-one-column",
           "--minimum-trade-amount", "--targeted-trade-amount", "--startup-candle"}


def build_command(argv, env, template, destination):
    if not argv or argv[0] not in ALLOWED:
        raise ValueError("Allowed commands: " + ", ".join(sorted(ALLOWED)))
    if any(arg.split("=", 1)[0] in FORBIDDEN or arg.startswith("-c") and not arg.startswith("--") for arg in argv[1:]):
        raise ValueError("Simulation profile and strategy overrides are not permitted")
    if any(arg.startswith("-") and arg.split("=", 1)[0] not in OPTIONS for arg in argv[1:]):
        raise ValueError("Unknown or abbreviated option; use the documented full option names")
    if any(key.startswith("FREQTRADE__") for key in env):
        raise ValueError("FREQTRADE__ overrides are not permitted in this lab entrypoint")
    config = json.loads(Path(template).read_text())
    if config.get("dry_run") is not True or config.get("trading_mode") != "spot":
        raise ValueError("A spot dry-run template is required")
    if any(config["exchange"].get(k) for k in ("key", "api_key", "secret", "password")):
        raise ValueError("Trading credentials must be absent")
    if config.get("force_entry_enable") or config.get("position_adjustment_enable"):
        raise ValueError("Force entry and position adjustment must be disabled")
    password, token = env.get("LAB_UI_PASSWORD", ""), env.get("LAB_UI_JWT_SECRET", "")
    if len(password) < 16 or len(token) < 32:
        raise ValueError("Run python -m trading_lab init to create local UI credentials")
    config["api_server"].update(password=password, jwt_secret_key=token, ws_token=token)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(config, out)
    destination.chmod(0o600)
    command = ["freqtrade", argv[0], "--config", str(destination)]
    if argv[0] in {"trade", "backtesting", "lookahead-analysis", "recursive-analysis"}:
        command += ["--strategy", "SwingBreakoutS1"]
    if argv[0] == "backtesting":
        command += ["--enable-protections"]
    return command + argv[1:]


def main():
    try:
        command = build_command(sys.argv[1:] or ["trade"], os.environ,
                                "/lab/configs/freqtrade.paper.json", "/freqtrade/user_data/config.runtime.json")
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
