"""Read credentials, never refresh or modify the owning CLI's login.

Environment values are explicit configuration. Local CLI files and gh are read
only when discovery is enabled. No credential value is included in diagnostics.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
from dataclasses import dataclass, field
from contextlib import closing

ENV_KEYS = {
    'claude': ('CLAUDE_CODE_OAUTH_TOKEN', 'FRUGALBAR_CLAUDE_TOKEN'),
    'openai': ('FRUGALBAR_CODEX_TOKEN',),
    'copilot': ('GH_TOKEN', 'GITHUB_TOKEN'),
    'githubRest': ('GH_TOKEN', 'GITHUB_TOKEN'),
    'githubGraphql': ('GH_TOKEN', 'GITHUB_TOKEN'),
    'opencode': ('OPENCODE_GO_API_KEY',),
    'openrouter': ('OPENROUTER_API_KEY',),
    'deepseek': ('DEEPSEEK_API_KEY',),
    'grok': ('FRUGALBAR_GROK_TOKEN',),
    'clinepass': ('CLINE_API_KEY', 'CLINEPASS_API_KEY'),
    'devpass': ('LLMGATEWAY_API_KEY', 'DEVPASS_API_KEY'),
    'commandcode': ('COMMAND_CODE_API_KEY', 'COMMANDCODE_API_KEY'),
    'kiro': ('FRUGALBAR_KIRO_TOKEN',),
    'muse': ('FRUGALBAR_MUSE_TOKEN',),
    'gemini': ('FRUGALBAR_GOOGLE_ACCESS_TOKEN',),
    'antigravityClaude': ('FRUGALBAR_GOOGLE_ACCESS_TOKEN',),
    'antigravityArgon': ('FRUGALBAR_GOOGLE_ACCESS_TOKEN',),
}


class CredentialReadError(Exception):
    """A transient local read failure, distinct from an absent login."""


@dataclass(frozen=True)
class Credential:
    token: str = field(repr=False)
    source: str = ''
    account: str = ''
    profile: str = ''


def text(value):
    return value.strip() if isinstance(value, str) else ''


def read_json(path):
    try:
        with Path(path).open('rb') as handle:
            raw = handle.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            return {}
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _gh_token():
    try:
        result = subprocess.run(['gh', 'auth', 'token'], capture_output=True,
                                text=True, timeout=3, check=False)
        return text(result.stdout) if result.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


def resolve(provider, *, discover=False, environment=None, home=None):
    env = os.environ if environment is None else environment
    root = Path.home() if home is None else Path(home)
    for key in ENV_KEYS.get(provider, ()):
        if value := text(env.get(key)):
            return Credential(value, 'Environment',
                              account=text(env.get('FRUGALBAR_CODEX_ACCOUNT_ID')),
                              profile=text(env.get('FRUGALBAR_KIRO_PROFILE_ARN')))
    # Explicitly injected fixture roots never consult the real desktop keyring.
    if environment is None and home is None:
        from .secretstore import read_secret
        token = read_secret(provider)
        if not token and provider in ('antigravityClaude', 'antigravityArgon'):
            token = read_secret('gemini')
        if token:
            return Credential(token, 'Desktop keyring',
                              account=text(env.get('FRUGALBAR_CODEX_ACCOUNT_ID')),
                              profile=text(env.get('FRUGALBAR_KIRO_PROFILE_ARN')))
    if not discover:
        return None
    data_root = Path(env.get('XDG_DATA_HOME') or root / '.local/share')
    config_root = Path(env.get('XDG_CONFIG_HOME') or root / '.config')
    opencode = read_json(data_root / 'opencode/auth.json')
    if provider in ('opencode', 'openrouter', 'deepseek'):
        entry = opencode.get('opencode-go' if provider == 'opencode' else provider, {})
        token = text(entry.get('key')) if isinstance(entry, dict) else ''
        return Credential(token, 'OpenCode login') if token else None
    if provider == 'claude':
        candidates = [Path(env['CLAUDE_CONFIG_DIR'])] if env.get('CLAUDE_CONFIG_DIR') else []
        candidates.extend((config_root / 'claude', root / '.claude'))
        path = next((p for p in candidates if (p / '.credentials.json').is_file()), candidates[-1])
        oauth = read_json(path / '.credentials.json').get('claudeAiOauth', {})
        token = text(oauth.get('accessToken')) if isinstance(oauth, dict) else ''
        return Credential(token, 'Claude Code login') if token else None
    if provider == 'openai':
        candidates = [Path(env['CODEX_HOME'])] if env.get('CODEX_HOME') else []
        candidates.extend((root / '.codex',))
        path = next((p for p in candidates if (p / 'auth.json').is_file()), candidates[-1])
        tokens = read_json(path / 'auth.json').get('tokens', {})
        if isinstance(tokens, dict) and (token := text(tokens.get('access_token'))):
            return Credential(token, 'Codex login', account=text(tokens.get('account_id')))
    if provider in ('copilot', 'githubRest', 'githubGraphql'):
        if provider == 'copilot':
            for key in ('github-copilot', 'github-copilot-enterprise'):
                entry = opencode.get(key, {})
                if isinstance(entry, dict) and (token := text(entry.get('refresh'))):
                    return Credential(token, 'OpenCode GitHub login')
            for entry in read_json(config_root / 'github-copilot/hosts.json').values():
                if isinstance(entry, dict) and (token := text(entry.get('oauth_token'))):
                    return Credential(token, 'Copilot login')
        token = _gh_token()
        return Credential(token, 'GitHub CLI login') if token else None
    if provider == 'commandcode':
        token = text(read_json(root / '.commandcode/auth.json').get('apiKey'))
        return Credential(token, 'Command Code login') if token else None
    if provider == 'grok':
        entries = [entry for entry in read_json(root / '.grok/auth.json').values()
                   if isinstance(entry, dict) and text(entry.get('key'))]
        if entries:
            # ISO-8601 timestamps sort chronologically for the CLI's UTC format.
            entry = max(entries, key=lambda item: text(item.get('expires_at')))
            return Credential(text(entry.get('key')), 'Grok login')
    if provider == 'clinepass':
        path = Path(env.get('CLINE_DATA_DIR') or Path(env.get('CLINE_DIR') or root / '.cline') / 'data')
        providers = read_json(path / 'settings/providers.json').get('providers', {})
        for key in ('cline', 'cline-pass'):
            entry = providers.get(key, {}) if isinstance(providers, dict) else {}
            settings = entry.get('settings', {}) if isinstance(entry, dict) else {}
            if not isinstance(settings, dict):
                continue
            auth = settings.get('auth', {})
            auth = auth if isinstance(auth, dict) else {}
            expiry = auth.get('expiresAt')
            live = not isinstance(expiry, (int, float)) or expiry / 1000 > time.time()
            if live and (token := text(auth.get('accessToken'))):
                return Credential(token, 'Cline login')
            for value in (settings.get('apiKey'), auth.get('apiKey')):
                if token := text(value):
                    return Credential(token, 'Cline login')
        if token := text(read_json(path / 'secrets.json').get('clineApiKey')):
            return Credential(token, 'Cline login')
    if provider == 'kiro':
        path = Path(env.get('KIRO_DATA_DIR') or data_root / 'kiro-cli') / 'data.sqlite3'
        if not path.is_file():
            return None
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=.25)) as db:
                token = ''
                token_profile = ''
                for key in ('kirocli:odic:token', 'kirocli:social:token'):
                    row = db.execute('SELECT value FROM auth_kv WHERE key = ?', (key,)).fetchone()
                    obj = json.loads(row[0]) if row else {}
                    obj = obj if isinstance(obj, dict) else {}
                    if token := text(obj.get('access_token')):
                        token_profile = text(obj.get('profile_arn'))
                        break
                row = db.execute('SELECT value FROM state WHERE key = ?',
                                 ('api.codewhisperer.profile',)).fetchone()
                profile_obj = json.loads(row[0]) if row else {}
                profile = text(profile_obj.get('arn')) if isinstance(profile_obj, dict) else ''
                profile = profile or token_profile
                if token and profile:
                    return Credential(token, 'Kiro CLI login', profile=profile)
        except (sqlite3.Error, ValueError, OSError):
            raise CredentialReadError('Could not read the Kiro login. Try again.') from None
    return None
