from decimal import Decimal
import unittest
from unittest.mock import patch

from frugalbar_linux import providers
from frugalbar_linux.credentials import Credential
from frugalbar_linux.http import FetchError


class ProvidersTests(unittest.TestCase):
    def test_empty_or_malformed_data_never_means_zero_usage(self):
        for provider, _ in providers.definitions():
            with self.subTest(provider=provider):
                windows, balances, _ = providers.parse(provider, {})
                self.assertEqual((windows, balances), ((), ()))

    def test_claude_mixed_fraction_and_percentage_source_semantics(self):
        windows, _, _ = providers.parse('claude', {
            'five_hour': {'utilization': 82, 'resets_at': '2026-11-02T10:00:00Z'},
            'seven_day': {'utilization': .4}})
        self.assertEqual([w.used for w in windows], [.82, .4])
        self.assertEqual(windows[0].duration, 18000)

    def test_codex_unknown_duration_does_not_get_five_hour_label(self):
        windows, balances, plan = providers.parse('openai', {'rate_limit': {
            'primary_window': {'used_percent': 25}}, 'credits': {'balance': '62500.000001'}, 'plan_type': 'pro'})
        self.assertEqual(windows[0].label, 'PRIMARY')
        self.assertIsNone(windows[0].duration)
        self.assertEqual(balances[0].value, '62500.000001')
        self.assertEqual(balances[0].unit, 'credits')

    def test_copilot_zero_entitlement_and_unlimited_are_not_headroom(self):
        windows, _, _ = providers.parse('copilot', {'quota_snapshots': {
            'premium_interactions': {'entitlement': 0, 'remaining': 0, 'percent_remaining': 100},
            'chat': {'entitlement': 500, 'remaining': 300, 'unlimited': True}}})
        self.assertEqual(windows, ())

    def test_copilot_independent_monthly_allowances_keep_both(self):
        windows, _, _ = providers.parse('copilot', {'quota_snapshots': {
            'premium_interactions': {'entitlement': 100, 'remaining': 20},
            'chat': {'entitlement': 200, 'remaining': 100}}, 'quota_reset_date': '2026-12-01'})
        self.assertEqual([w.detail for w in windows], ['Premium', 'Chat'])
        self.assertEqual([w.used for w in windows], [.8, .5])

    def test_opencode_blocked_without_percentage_stays_blocked(self):
        windows, _, _ = providers.parse('opencode', {'usage': {'rolling': {'status': 'rate-limited'}}})
        self.assertTrue(windows[0].blocked)
        self.assertIsNone(windows[0].used)

    def test_deepseek_exact_currency_balances_never_become_gauges(self):
        windows, balances, _ = providers.parse('deepseek', {'is_available': True,
            'balance_infos': [{'currency': 'CNY', 'total_balance': '16.12345678'}]})
        self.assertEqual(windows, ())
        self.assertEqual((balances[0].value, balances[0].unit), ('16.12345678', 'CNY'))
        self.assertEqual(providers.parse('deepseek', {'balance_infos': [{'currency': 'USD', 'total_balance': 100}]})[:2], ((), ()))

    def test_openrouter_lifetime_spend_is_not_a_balance(self):
        self.assertEqual(providers.parse('openrouter', {'data': {'usage': 50}})[:2], ((), ()))
        _, balances, _ = providers.parse('openrouter', {'data': {}, '_credits': {
            'total_credits': Decimal('20.1'), 'total_usage': Decimal('3.09')}})
        self.assertEqual(balances[0].value, '17.01')

    def test_bad_percentages_and_booleans_do_not_create_windows(self):
        for value in (None, True, 'nan', float('inf')):
            self.assertEqual(providers.parse('clinepass', {'limits': [{'type': 'five_hour', 'percentUsed': value}]})[0], ())
        for value, used in ((-1, 0), (101, 1)):
            self.assertEqual(providers.parse('clinepass', {'limits': [{'type': 'five_hour', 'percentUsed': value}]})[0][0].used, used)

    def test_devpass_never_uses_someone_elses_pinned_renewal(self):
        windows, _, _ = providers.parse('devpass', {'data': {'devPlan': 'pro',
            'devPlanCreditsUsed': '10', 'devPlanCreditsLimit': '100'}})
        self.assertEqual(windows[0].used, .1)
        self.assertIsNone(windows[0].resets_at)

    def test_remaining_provider_published_shapes(self):
        fixtures = [
            ('grok', {'config': {'creditUsagePercent': 25, 'currentPeriod': {
                'type': 'weekly', 'start': '2026-11-01T00:00:00Z', 'end': '2026-11-08T00:00:00Z'}}}, 'WK', .25),
            ('commandcode', {'data': {'windowLimits': {'fiveHour': {'used': '15', 'cap': '100'}}}}, '5H', .15),
            ('muse', {'is_subs_active': True, 'subs_usage': {'window': {
                'used_percent': '35', 'window_duration_mins': 300, 'resets_at': '1793617200000'}}}, '5H', .35),
            ('kiro', {'nextDateReset': 1793617200, 'usageBreakdownList': [{'resourceType': 'CREDIT',
                'currentUsageWithPrecision': 30, 'currentOveragesWithPrecision': 10,
                'usageLimitWithPrecision': 100}]}, 'MO', .2),
            ('githubRest', {'resources': {'core': {'limit': 5000, 'remaining': 4000}}}, '1H', .2),
            ('clinepass', {'success': True, 'data': {'limits': [{'type': 'weekly', 'percentUsed': '12.5'}]}}, 'WK', .125),
        ]
        for provider, data, label, used in fixtures:
            with self.subTest(provider=provider):
                windows, _, _ = providers.parse(provider, data)
                self.assertEqual((windows[0].label, windows[0].used), (label, used))

    def test_vendor_reset_units_and_grok_pace_are_not_invented(self):
        self.assertEqual(providers.stamp('1793617200000'), 1793617200)
        windows, _, _ = providers.parse('grok', {'config': {'creditUsagePercent': 25,
            'currentPeriod': {'type': 'monthly', 'end': '2026-12-01T00:00:00Z'}}})
        self.assertIsNone(windows[0].duration)

    def test_deepseek_vendor_unavailability_is_not_healthy(self):
        with patch.object(providers, 'resolve', return_value=Credential('fixture')), \
                patch.object(providers, '_read', return_value={'is_available': False,
                    'balance_infos': [{'currency': 'USD', 'total_balance': '10'}]}):
            result = providers.fetch('deepseek')
        self.assertEqual(result.state, 'measured')
        self.assertIn('cannot fund calls', result.message)
        self.assertTrue(result.critical)

    def test_claude_throttle_is_not_credential_rejected(self):
        with patch.object(providers, 'resolve', return_value=Credential('fixture')), \
                patch.object(providers, '_read', side_effect=FetchError('fixture-private', 403)), \
                patch.object(providers.time, 'time', return_value=1000):
            result = providers.fetch('claude')
        self.assertEqual(result.state, 'rate_limited')
        self.assertEqual(result.retry_at, 1300)
        self.assertNotIn('fixture-private', result.message)

    def test_cline_http_404_is_explicit_no_subscription(self):
        with patch.object(providers, 'resolve', return_value=Credential('fixture')), \
                patch.object(providers, '_read', side_effect=FetchError('Provider request failed', 404)):
            result = providers.fetch('clinepass')
        self.assertIn('No ClinePass subscription', result.message)
        self.assertEqual(result.windows, ())

    def test_google_scopes_project_and_falls_through_missing_gemini_host(self):
        calls = []
        def request(url, token, **kwargs):
            calls.append((url, kwargs))
            if url.endswith('loadCodeAssist'):
                return {'cloudaicompanionProject': 'fixture-project'}
            if 'daily-' in url:
                return {'groups': [{'displayName': 'Claude and GPT models', 'buckets': []}]}
            return {'groups': [{'displayName': 'Gemini', 'buckets': [
                {'window': '5h', 'remainingFraction': .7, 'resetTime': '2026-11-02T10:00:00Z'},
                {'window': 'weekly', 'remainingFraction': 1, 'disabled': True}]}]}
        with patch.object(providers, 'request', side_effect=request):
            windows, _, _ = providers._google('gemini', Credential('fixture'))
        self.assertEqual(len(windows), 1)
        self.assertAlmostEqual(windows[0].used, .3)
        quota_calls = [kwargs for url, kwargs in calls if url.endswith('retrieveUserQuotaSummary')]
        self.assertEqual([c['body'] for c in quota_calls], [{'project': 'fixture-project'}] * 2)


if __name__ == '__main__':
    unittest.main()
