import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("entrypoint", ROOT / "scripts/freqtrade_entrypoint.py")
entrypoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entrypoint)


class EntrypointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = {"LAB_UI_PASSWORD": "test-only-password-long", "LAB_UI_JWT_SECRET": "test-only-jwt-32-characters-or-longer"}
        self.template = ROOT / "configs/freqtrade.paper.json"
        self.destination = Path(self.temp.name) / "runtime.json"

    def command(self, args, env=None):
        return entrypoint.build_command(args, env or self.env, self.template, self.destination)

    def test_generated_profile_is_paper_with_auth(self):
        cmd = self.command(["trade"])
        cfg = json.loads(self.destination.read_text())
        self.assertIs(cfg["dry_run"], True)
        self.assertEqual(cmd[-1], "SwingBreakoutS1")
        self.assertEqual(cfg["exchange"]["api_key"], "")
        self.assertEqual(self.destination.stat().st_mode & 0o777, 0o600)

    def test_configuration_overrides_rejected(self):
        for arg in ("--config=evil.json", "-cevil.json", "--trading-mode=futures", "--strategy=Other", "--conf=evil.json", "--strat=Other"):
            with self.assertRaises(ValueError):
                self.command(["trade", arg])

    def test_environment_override_rejected(self):
        env = {**self.env, "FREQTRADE__DRY_RUN": "false"}
        with self.assertRaises(ValueError):
            self.command(["trade"], env)

    def test_missing_auth_rejected(self):
        with self.assertRaises(ValueError):
            self.command(["trade"], {"LAB_UI_PASSWORD": "short"})

    def test_download_does_not_receive_strategy_flag(self):
        cmd = self.command(["download-data", "--timeframes", "1h", "4h", "1d"])
        self.assertNotIn("--strategy", cmd)

    def test_unknown_command_rejected(self):
        with self.assertRaises(ValueError):
            self.command(["show-config"])
