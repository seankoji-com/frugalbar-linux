"""Bounded JSON metadata reads. Credentials are never forwarded across redirects."""
from __future__ import annotations

import json
import math
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from email.utils import parsedate_to_datetime

MAX_BYTES = 2 * 1024 * 1024
TIMEOUT = 10
ALLOWED_HOSTS = frozenset({
    'api.anthropic.com', 'chatgpt.com', 'api.github.com', 'opencode.ai',
    'openrouter.ai', 'api.deepseek.com', 'cli-chat-proxy.grok.com',
    'api.cline.bot', 'api.llmgateway.io', 'api.commandcode.ai',
    'codewhisperer.us-east-1.amazonaws.com', 'api.meta.ai',
    'daily-cloudcode-pa.googleapis.com', 'cloudcode-pa.googleapis.com',
})


@dataclass
class FetchError(Exception):
    message: str
    status: int = 0
    retry_at: float | None = None

    def __str__(self):
        return self.message


def retry_after(value, now=None):
    now = time.time() if now is None else now
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.isascii() and text.isdigit() and len(text) < 12:
        seconds = min(int(text), 86400)
        return now + seconds if seconds > 0 else None
    try:
        stamp = parsedate_to_datetime(text).timestamp()
        return min(stamp, now + 86400) if math.isfinite(stamp) and stamp > now else None
    except (ValueError, TypeError, OverflowError):
        return None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url, token, *, headers=None, body=None):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise FetchError('Invalid provider endpoint')
    fields = {'Accept': 'application/json', 'User-Agent': 'frugalbar-linux/0.1.0',
              'Authorization': 'Bearer ' + token}
    fields.update(headers or {})
    data = None if body is None else json.dumps(body).encode('utf-8')
    if body is not None:
        fields.setdefault('Content-Type', 'application/json')
    req = urllib.request.Request(url, data=data, headers=fields)
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=TIMEOUT) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise FetchError('Provider response too large')
            try:
                result = json.loads(raw, parse_float=Decimal,
                                    parse_constant=lambda _: None)
            except (ValueError, UnicodeDecodeError):
                raise FetchError('Unreadable provider response') from None
            if not isinstance(result, dict):
                raise FetchError('Unreadable provider response')
            return result
    except urllib.error.HTTPError as error:
        status = error.code
        retry = retry_after(error.headers.get('Retry-After'))
        error.close()
        message = ('Credential rejected. Check the connection in Settings.'
                   if status in (401, 403) else
                   'Rate limited. Waiting before the next automatic read.'
                   if status == 429 else 'Provider request failed')
        raise FetchError(message, status, retry) from None
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
        raise FetchError('Provider connection failed or timed out') from None
