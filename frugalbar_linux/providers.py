"""Vendor metadata adapters ported from FrugalBar's MIT provider sources.

No completion/model calls, estimated quotas, credential refreshes or mobile sync.
Each independently metered pool stays separate; unknown data yields no gauge.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import math
import hashlib
import time

from .credentials import CredentialReadError, resolve, text
from .http import FetchError, request
from .models import Balance, Snapshot, Window

_DEFINITIONS = (
    ('claude', 'Claude Code'), ('openai', 'Codex'),
    ('gemini', 'Antigravity Gemini'), ('antigravityArgon', 'Antigravity Argon'),
    ('antigravityClaude', 'Antigravity Claude'), ('opencode', 'OpenCode Go'),
    ('copilot', 'GitHub Copilot'), ('grok', 'Grok'), ('kiro', 'Kiro'),
    ('devpass', 'DevPass'), ('commandcode', 'Command Code'),
    ('clinepass', 'ClinePass'), ('muse', 'Muse'),
    ('openrouter', 'OpenRouter'), ('deepseek', 'DeepSeek'),
    ('githubRest', 'GitHub REST'), ('githubGraphql', 'GitHub GraphQL'),
)


def definitions():
    return _DEFINITIONS


def obj(value):
    return value if isinstance(value, dict) else {}


def items(value):
    return value if isinstance(value, list) else []


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (ValueError, OverflowError):
        return None


def decimal(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    if len(str(value)) > 80:
        return None
    try:
        parsed = Decimal(str(value))
        return parsed if parsed.is_finite() else None
    except InvalidOperation:
        return None


def stamp(value):
    numeric = number(value)
    if numeric is not None:
        result = numeric / 1000 if numeric > 10**12 else numeric
        return result if 0 < result < 10**11 else None
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        result = parsed.timestamp()
        return result if 0 <= result < 10**11 else None
    except (ValueError, OverflowError, OSError):
        return None


def fraction(value, scale=100):
    parsed = number(value)
    return parsed / scale if parsed is not None and 0 <= parsed <= scale else None


def ratio(used, limit):
    u, cap = number(used), number(limit)
    if u is None or cap is None or cap <= 0 or u < 0:
        return None
    return min(u / cap, 1.0)


def month_length(reset):
    if reset is None:
        return None
    end = datetime.fromtimestamp(reset, timezone.utc)
    import calendar
    year, month = (end.year - 1, 12) if end.month == 1 else (end.year, end.month - 1)
    day = min(end.day, calendar.monthrange(year, month)[1])
    return reset - end.replace(year=year, month=month, day=day).timestamp()


def window(label, used, reset=None, duration=None, *, blocked=False, detail='', infer_month=True):
    if used is None and not blocked:
        return None
    at = stamp(reset)
    if label == 'MO' and duration is None and infer_month:
        duration = month_length(at)
    return Window(label, used, resets_at=at, duration=duration,
                  blocked=blocked, detail=detail)


def _read(provider, credential):
    token = credential.token
    if provider == 'claude':
        return request('https://api.anthropic.com/api/oauth/usage', token,
                       headers={'anthropic-beta': 'oauth-2025-04-20'})
    if provider == 'openai':
        headers = {'chatgpt-account-id': credential.account} if credential.account else {}
        return request('https://chatgpt.com/backend-api/wham/usage', token, headers=headers)
    if provider == 'copilot':
        return request('https://api.github.com/copilot_internal/user', token, headers={
            'Authorization': 'token ' + token, 'Editor-Version': 'vscode/1.96.2',
            'Editor-Plugin-Version': 'copilot-chat/0.26.7',
            'User-Agent': 'GitHubCopilotChat/0.26.7', 'X-Github-Api-Version': '2025-04-01'})
    endpoints = {
        'opencode': 'https://opencode.ai/zen/go/v1/usage',
        'deepseek': 'https://api.deepseek.com/user/balance',
        'devpass': 'https://api.llmgateway.io/v1/key',
        'openrouter': 'https://openrouter.ai/api/v1/auth/key',
        'grok': 'https://cli-chat-proxy.grok.com/v1/billing?format=credits',
        'clinepass': 'https://api.cline.bot/api/v1/users/me/plan/usage-limits',
        'commandcode': 'https://api.commandcode.ai/alpha/billing/credits',
        'githubRest': 'https://api.github.com/rate_limit',
        'githubGraphql': 'https://api.github.com/rate_limit',
    }
    if provider == 'muse':
        return request('https://api.meta.ai/muse-code/key', token,
                       body={}, headers={'x-api-version': '1.0.0'})
    if provider == 'kiro':
        if not credential.profile:
            raise FetchError('Kiro needs a profile ARN as well as its access token')
        return request('https://codewhisperer.us-east-1.amazonaws.com/', token,
                       body={'profileArn': credential.profile}, headers={
                           'Content-Type': 'application/x-amz-json-1.0',
                           'X-Amz-Target': 'AmazonCodeWhispererService.GetUsageLimits'})
    headers = {'x-xai-token-auth': 'xai-grok-cli'} if provider == 'grok' else {}
    try:
        return request(endpoints[provider], token, headers=headers)
    except FetchError as error:
        if provider == 'clinepass' and error.status == 401 and not token.lower().startswith('workos:'):
            return request(endpoints[provider], 'workos:' + token)
        raise


def parse(provider, data):
    """Return published windows, balances and optional plan, with no I/O."""
    windows, balances, plan = [], [], ''
    if provider == 'claude':
        for key, label, duration in [('five_hour', '5H', 18000), ('seven_day', 'WK', 604800)]:
            row = obj(data.get(key))
            value = number(row.get('utilization'))
            # Match the original adapter's mixed percent/fraction convention.
            used = fraction(value, 100) if value is not None and value > 1 else fraction(value, 1)
            windows.append(window(label, used, row.get('resets_at'), duration))
    elif provider == 'openai':
        limits = obj(data.get('rate_limit'))
        for key in ('primary_window', 'secondary_window'):
            row = obj(limits.get(key))
            duration = number(row.get('limit_window_seconds'))
            label = '5H' if duration == 18000 else 'WK' if duration == 604800 else key.replace('_window', '').upper()
            windows.append(window(label, fraction(row.get('used_percent')), row.get('reset_at'), duration))
        credits = obj(data.get('credits'))
        if credits.get('unlimited') is not True and (value := decimal(credits.get('balance'))) is not None:
            balances.append(Balance(str(value), 'credits', 'API credits'))
        plan = text(data.get('plan_type'))
    elif provider == 'opencode':
        usage = obj(data.get('usage'))
        for key, label, duration in [('rolling', '5H', 18000), ('weekly', 'WK', 604800), ('monthly', 'MO', None)]:
            row = obj(usage.get(key))
            windows.append(window(label, fraction(row.get('percent')), row.get('resetsAt'), duration,
                                  blocked=row.get('status') == 'rate-limited'))
    elif provider == 'copilot':
        for key, label in [('premium_interactions', 'Premium'), ('chat', 'Chat')]:
            row = obj(obj(data.get('quota_snapshots')).get(key))
            limit, remaining = number(row.get('entitlement')), number(row.get('remaining'))
            if row.get('unlimited') is True or not limit or limit <= 0:
                continue
            percent = fraction(row.get('percent_remaining'))
            used = 1 - percent if percent is not None else ratio(limit - remaining, limit) if remaining is not None else None
            windows.append(window('MO', used, data.get('quota_reset_date'), detail=label))
        plan = text(data.get('copilot_plan'))
    elif provider == 'deepseek':
        if not isinstance(data.get('is_available'), bool):
            return (), (), ''
        for row in items(data.get('balance_infos')):
            row = obj(row)
            value = decimal(row.get('total_balance'))
            currency = text(row.get('currency'))
            if value is not None and currency:
                kind = 'Prepaid balance' if data['is_available'] else 'Balance unavailable for calls'
                balances.append(Balance(str(value), currency, kind))
    elif provider == 'openrouter':
        row = obj(data.get('data'))
        # The caller supplies credits when the account endpoint permits it.
        credits = obj(data.get('_credits'))
        total, spent = decimal(credits.get('total_credits')), decimal(credits.get('total_usage'))
        if total is not None and spent is not None:
            balances.append(Balance(str(total - spent), 'USD', 'Account credit'))
        else:
            remaining = decimal(row.get('limit_remaining'))
            if remaining is not None:
                balances.append(Balance(str(remaining), 'USD', 'Key cap remaining'))
            # Lifetime spend is never relabelled as a balance or quota.
    elif provider == 'grok':
        row = obj(data.get('config'))
        period = obj(row.get('currentPeriod'))
        kind = text(period.get('type')).lower()
        label = 'WK' if 'week' in kind else 'MO' if 'month' in kind else 'PLAN'
        end = stamp(period.get('end') or row.get('billingPeriodEnd'))
        start = stamp(period.get('start') or row.get('billingPeriodStart'))
        duration = end - start if end is not None and start is not None and end > start else None
        windows.append(window(label, fraction(row.get('creditUsagePercent')), end,
                              duration, infer_month=False))
        plan = text(data.get('subscriptionTier')) or text(row.get('subscriptionTier'))
    elif provider == 'clinepass':
        if data.get('success') is False:
            return (), (), ''
        payload = obj(data.get('data')) if 'data' in data else data
        types = {'five_hour': ('5H', 18000), 'weekly': ('WK', 604800), 'monthly': ('MO', None)}
        for row in items(payload.get('limits')):
            row = obj(row)
            if row.get('type') in types:
                label, duration = types[row['type']]
                windows.append(window(label, fraction(row.get('percentUsed')), row.get('resetsAt'), duration))
    elif provider == 'devpass':
        row = obj(data.get('data'))
        raw_plan = text(row.get('devPlan'))
        if raw_plan and raw_plan != 'none':
            plan = raw_plan
            windows.append(window('MO', ratio(row.get('devPlanCreditsUsed'), row.get('devPlanCreditsLimit'))))
    elif provider == 'commandcode':
        payload = obj(data.get('data')) if 'data' in data else data
        limits = obj(payload.get('windowLimits'))
        for key, label, duration in [('fiveHour', '5H', 18000), ('weekly', 'WK', 604800)]:
            row = obj(limits.get(key))
            reset = row.get('resetAt')
            if (numeric := number(reset)) is not None:
                reset = numeric / 1000 if numeric > 10**11 else numeric
            windows.append(window(label, ratio(row.get('used'), row.get('cap')), reset, duration))
        plan = text(obj(payload.get('credits')).get('planId'))
    elif provider == 'muse':
        usage = obj(data.get('subs_usage'))
        if data.get('require_payment') is True or data.get('is_subs_active') is False:
            return (), (), text(data.get('subs_tier_name'))
        for key, label, duration in [('window', '5H', None), ('weekly', 'WK', 604800)]:
            row = obj(usage.get(key))
            minutes = number(row.get('window_duration_mins'))
            if key == 'window':
                duration = minutes * 60 if minutes is not None and minutes > 0 else None
            windows.append(window(label, fraction(row.get('used_percent')), row.get('resets_at'), duration))
        plan = text(data.get('subs_tier_name')) or text(usage.get('tier'))
    elif provider == 'kiro':
        rows = [obj(row) for row in items(data.get('usageBreakdownList')) if obj(row).get('resourceType') == 'CREDIT']
        if len(rows) != 1:
            return (), (), ''
        row = rows[0]
        total, overage = number(row.get('currentUsageWithPrecision')), number(row.get('currentOveragesWithPrecision'))
        overage = 0 if overage is None and 'currentOveragesWithPrecision' not in row else overage
        used = total - overage if total is not None and overage is not None and total >= overage else None
        windows.append(window('MO', ratio(used, row.get('usageLimitWithPrecision')),
                              row.get('nextDateReset') or data.get('nextDateReset')))
        plan = text(obj(data.get('subscriptionInfo')).get('subscriptionTitle'))
    elif provider in ('githubRest', 'githubGraphql'):
        row = obj(obj(data.get('resources')).get('core' if provider == 'githubRest' else 'graphql'))
        limit, remaining = number(row.get('limit')), number(row.get('remaining'))
        used = ratio(limit - remaining, limit) if limit is not None and remaining is not None else None
        windows.append(window('1H', used, row.get('reset'), 3600,
                              detail='Requests' if provider == 'githubRest' else 'Points'))
    return tuple(w for w in windows if w is not None), tuple(balances), plan


def _google(provider, credential):
    last_error = None
    for base in ('https://daily-cloudcode-pa.googleapis.com/v1internal:',
                 'https://cloudcode-pa.googleapis.com/v1internal:'):
        try:
            headers = {'User-Agent': 'antigravity/cli/1.4.3'}
            assist = request(base + 'loadCodeAssist', credential.token, headers=headers,
                             body={'metadata': {'ideType': 'ANTIGRAVITY', 'platform': 'PLATFORM_UNSPECIFIED', 'pluginType': 'GEMINI'}})
            project = text(assist.get('cloudaicompanionProject'))
            if not project:
                continue
            data = request(base + 'retrieveUserQuotaSummary', credential.token,
                           headers=headers, body={'project': project})
            candidates = []
            for group in items(data.get('groups')):
                group = obj(group)
                buckets = items(group.get('buckets'))
                name = text(group.get('displayName')).lower()
                ids = [text(obj(b).get('bucketId')).lower() for b in buckets]
                argon = 'argon' in name or any(key.startswith('gemini-argon-') for key in ids)
                if provider == 'antigravityArgon':
                    matches = argon
                elif provider == 'antigravityClaude':
                    matches = not argon and ('claude' in name or any(key.startswith('claude') for key in ids))
                else:
                    matches = not argon and ('gemini' in name or any(key.startswith('gemini') for key in ids))
                if matches:
                    candidates.append(group)
            if len(candidates) != 1:
                continue
            windows = []
            for row in items(candidates[0].get('buckets')):
                row = obj(row)
                if row.get('disabled') not in (True, False, None):
                    continue
                if row.get('disabled') is True:
                    continue
                left = fraction(row.get('remainingFraction'), 1)
                kind = text(row.get('window')).lower()
                label = {'5h': '5H', 'weekly': 'WK', 'monthly': 'MO'}.get(kind, kind.upper() or 'AG')
                duration = {'5h': 18000, 'weekly': 604800}.get(kind)
                windows.append(window(label, None if left is None else 1 - left,
                                      row.get('resetTime'), duration, detail=text(row.get('displayName')),
                                      infer_month=False))
            windows = tuple(w for w in windows if w is not None)
            if windows:
                tier = obj(assist.get('paidTier')) or obj(assist.get('currentTier'))
                return windows, (), text(tier.get('name'))
        except FetchError as error:
            if error.status in (401, 403):
                raise
            last_error = error
    if last_error:
        raise last_error
    return (), (), ''


def fetch(provider, *, discover=False):
    name = dict(_DEFINITIONS).get(provider, provider)
    try:
        credential = resolve(provider, discover=discover)
    except CredentialReadError:
        return Snapshot(provider, name, state='error',
                        message='Could not read the local CLI login. Try again.')
    if credential is None:
        return Snapshot(provider, name, state='not_configured',
                        message='Add a credential in Settings or enable local CLI discovery.')
    identity = hashlib.sha256((credential.token + '\x00' + credential.account + '\x00' + credential.profile).encode()).hexdigest()
    try:
        if provider in ('gemini', 'antigravityClaude', 'antigravityArgon'):
            windows, balances, plan = _google(provider, credential)
        else:
            data = _read(provider, credential)
            if provider == 'openrouter':
                try:
                    credit_data = request('https://openrouter.ai/api/v1/credits', credential.token)
                    data = dict(data, _credits=obj(credit_data.get('data')))
                except FetchError:
                    pass  # A key cap can still be a valid independent reading.
            windows, balances, plan = parse(provider, data)
        measured = bool(windows or balances)
        message = '' if measured else 'The provider published no usable quota or balance.'
        if provider == 'deepseek' and data.get('is_available') is False:
            message = 'DeepSeek reports that this balance cannot fund calls.'
        return Snapshot(provider, name, windows=windows, balances=balances,
                        plan=plan, state='measured' if measured else 'unavailable',
                        message=message, measured_at=time.time() if measured else None,
                        source=credential.source, credential_id=identity)
    except FetchError as error:
        throttled = error.status == 429 or (provider == 'claude' and error.status == 403)
        retry = error.retry_at
        if throttled and provider == 'claude':
            retry = min(retry, time.time() + 3600) if retry else time.time() + 300
        return Snapshot(provider, name, state='rate_limited' if throttled else 'error',
                        message='Rate limited. Waiting before the next automatic read.' if throttled else
                        'No ClinePass subscription on this account.' if provider == 'clinepass' and error.status == 404 else error.message,
                        retry_at=retry, source=credential.source, credential_id=identity)
    except (ValueError, TypeError, KeyError, OverflowError, ArithmeticError):
        return Snapshot(provider, name, state='error', message='Unreadable provider response',
                        source=credential.source, credential_id=identity)
