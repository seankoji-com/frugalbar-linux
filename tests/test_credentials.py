import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from frugalbar_linux.credentials import CredentialReadError, resolve


class CredentialsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def resolve(self, provider, **kwargs):
        return resolve(provider, home=self.root, environment={}, **kwargs)

    def test_discovery_is_opt_in_and_never_invokes_gh_by_default(self):
        self.write('.codex/auth.json', {'tokens': {'access_token': 'fixture'}})
        with patch('frugalbar_linux.credentials._gh_token', side_effect=AssertionError):
            self.assertIsNone(self.resolve('openai'))
            self.assertIsNone(self.resolve('copilot'))
        self.assertEqual(self.resolve('openai', discover=True).token, 'fixture')

    def test_explicit_environment_overrides_cli_and_repr_hides_token(self):
        self.write('.codex/auth.json', {'tokens': {'access_token': 'old'}})
        result = resolve('openai', environment={'FRUGALBAR_CODEX_TOKEN': 'fixture-secret'},
                         home=self.root, discover=True)
        self.assertEqual(result.token, 'fixture-secret')
        self.assertNotIn('fixture-secret', repr(result))

    def test_claude_current_location_and_stale_override_fallback(self):
        self.write('.config/claude/.credentials.json', {'claudeAiOauth': {'accessToken': 'fixture'}})
        result = resolve('claude', discover=True, environment={'CLAUDE_CONFIG_DIR': str(self.root / 'absent')}, home=self.root)
        self.assertEqual(result.token, 'fixture')

    def test_copilot_reads_durable_refresh_not_short_lived_access(self):
        self.write('.local/share/opencode/auth.json', {'github-copilot': {'refresh': 'durable', 'access': 'wrong'}})
        self.assertEqual(self.resolve('copilot', discover=True).token, 'durable')

    def test_expired_claude_token_is_not_sent_to_vendor(self):
        self.write('.claude/.credentials.json', {'claudeAiOauth': {'accessToken': 'expired', 'expiresAt': 1}})
        self.assertIsNone(self.resolve('claude', discover=True))

    def test_cline_stale_override_falls_back_to_existing_login(self):
        self.write('.cline/data/secrets.json', {'clineApiKey': 'fixture'})
        result = resolve('clinepass', discover=True, home=self.root,
                         environment={'CLINE_DATA_DIR': str(self.root / 'missing')})
        self.assertEqual(result.token, 'fixture')

    def test_cline_nested_auth_and_legacy_key(self):
        self.write('.cline/data/settings/providers.json', {'providers': {'cline-pass': {
            'settings': {'auth': {'accessToken': 'expired', 'expiresAt': 1}, 'apiKey': 'fallback'}}}})
        self.assertEqual(self.resolve('clinepass', discover=True).token, 'fallback')

    def test_kiro_database_is_read_only_and_uses_profile_arn(self):
        path = self.root / '.local/share/kiro-cli/data.sqlite3'
        path.parent.mkdir(parents=True)
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE auth_kv (key TEXT, value TEXT)')
            db.execute('CREATE TABLE state (key TEXT, value TEXT)')
            db.execute('INSERT INTO auth_kv VALUES (?, ?)', ('kirocli:social:token', json.dumps({'access_token': 'fixture'})))
            db.execute('INSERT INTO state VALUES (?, ?)', ('api.codewhisperer.profile', json.dumps({'arn': 'arn:fixture'})))
            db.commit()
        before = path.read_bytes()
        result = self.resolve('kiro', discover=True)
        self.assertEqual((result.token, result.profile), ('fixture', 'arn:fixture'))
        self.assertEqual(path.read_bytes(), before)

    def test_unreadable_kiro_database_is_not_a_missing_login(self):
        path = self.root / '.local/share/kiro-cli/data.sqlite3'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'not a database')
        with self.assertRaises(CredentialReadError):
            self.resolve('kiro', discover=True)


if __name__ == '__main__':
    unittest.main()
