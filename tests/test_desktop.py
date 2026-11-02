import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from frugalbar_linux import config, secretstore
from frugalbar_linux.__main__ import main


class DesktopTests(unittest.TestCase):
    def test_homebrew_desktop_launch_keeps_wrapper_and_its_session_path(self):
        with tempfile.TemporaryDirectory() as root:
            prefix = Path(root)
            (prefix / "bin").mkdir()
            wrapper = prefix / "bin/frugalbar-linux"
            wrapper.write_text("#!/bin/sh\n")
            with patch("sys.argv", [str(prefix / "libexec/launch.py")]):
                self.assertIn(f'Exec="{wrapper.resolve()}"\n', config.desktop_entry())
                self.assertNotIn(" -m frugalbar_linux", config.desktop_entry())

    def test_preferences_contain_only_nonsecret_choices_and_startup_is_explicit(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"XDG_CONFIG_HOME": root}), \
                patch("sys.argv", ["/opt/frugal bar/bin/frugalbar-linux"]):
            config.save({"discover": True, "show_unconfigured": False, "token": "fixture-secret"})
            path = Path(root) / "frugalbar-linux/settings.json"
            self.assertNotIn("fixture-secret", path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(config.load(), {"discover": True, "show_unconfigured": False})
            self.assertFalse(config.autostart_enabled())
            config.set_autostart(True)
            entry = (Path(root) / "autostart/frugalbar-linux.desktop").read_text()
            self.assertIn('Exec="/opt/frugal bar/bin/frugalbar-linux" --hidden\n', entry)
            config.set_autostart(False)
            self.assertFalse(config.autostart_enabled())

    def test_desktop_installer_and_percent_escaping(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"XDG_DATA_HOME": root}), \
                patch("sys.argv", ["/opt/100%/frugalbar-linux", "--install-desktop"]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 0)
            entry = (Path(root) / "applications/frugalbar-linux.desktop").read_text()
            self.assertIn('Exec="/opt/100%%/frugalbar-linux"\n', entry)

    def test_demo_json_does_not_touch_credentials_and_strips_fingerprint(self):
        with patch("sys.argv", ["frugalbar-linux", "--demo", "--json"]), \
                patch("frugalbar_linux.credentials.resolve", side_effect=AssertionError("No credentials in demo")), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 0)
            data = json.loads(output.getvalue())
            self.assertTrue(data["illustrative"])
            self.assertNotIn("credential_id", output.getvalue())

    def test_keyring_save_and_clear_never_pass_secret_in_command_arguments(self):
        with patch.object(secretstore, "available", return_value=True), \
                patch.object(secretstore.subprocess, "run", return_value=Mock(returncode=0)) as run:
            self.assertTrue(secretstore.save_secret("claude", "fixture-secret"))
            args, kwargs = run.call_args
            self.assertNotIn("fixture-secret", " ".join(args[0]))
            self.assertEqual(kwargs["input"], "fixture-secret")
            self.assertTrue(secretstore.save_secret("claude", ""))
            self.assertEqual(run.call_args.args[0][:2], ["secret-tool", "clear"])

    def test_missing_keyring_is_not_an_empty_saved_credential(self):
        with patch.object(secretstore, "available", return_value=False), \
                patch.object(secretstore.subprocess, "run", side_effect=AssertionError):
            self.assertIsNone(secretstore.read_secret("claude"))
            self.assertFalse(secretstore.save_secret("claude", "fixture"))
