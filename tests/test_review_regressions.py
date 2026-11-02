"""Consequential edge cases found by independent review R1."""
from dataclasses import replace
import unittest
from frugalbar_linux.models import Snapshot, Window, tray_reading, urgency
from frugalbar_linux import providers


class ReviewRegressions(unittest.TestCase):
    def test_negative_percentage_cannot_disagree_with_zero_meter_label(self):
        windows, _, _ = providers.parse("clinepass", {"limits": [{"type": "five_hour", "percentUsed": -1}]})
        self.assertEqual(windows[0].used, 0)
        self.assertIsNone(windows[0].reported_percent)

    def test_no_live_subscription_never_makes_a_green_or_developer_red_tray(self):
        stale = Snapshot("claude", "Claude", (Window("5H", .1),), stale=True)
        developer = Snapshot("githubRest", "GitHub", (Window("1H", .99),))
        for rows in ([stale], [developer], [stale, developer]):
            self.assertEqual(tray_reading(rows, 1000)[2], "unknown")
        self.assertEqual(tray_reading([replace(stale, stale=False, windows=(Window("5H", 1),))], 1000)[2], "critical")

    def test_new_window_activity_does_not_mean_running_low(self):
        self.assertEqual(urgency(Window("WK", .02, 600000, 604800), 1000), "normal")
        self.assertEqual(urgency(Window("5H", .82), 1000), "warning")

    def test_over_quota_is_exhausted_and_preserves_muse_reported_percent(self):
        fixtures = [
            ("muse", {"subs_usage": {"window": {"used_percent": 120}}}),
            ("opencode", {"usage": {"rolling": {"percent": 150}}}),
            ("clinepass", {"limits": [{"type": "five_hour", "percentUsed": 101}]}),
            ("grok", {"config": {"creditUsagePercent": 110}}),
        ]
        for provider, data in fixtures:
            with self.subTest(provider=provider):
                windows, _, _ = providers.parse(provider, data)
                self.assertEqual(windows[0].used, 1)
                self.assertEqual(urgency(windows[0], 1000), "critical")
                if provider == "muse":
                    self.assertEqual(windows[0].reported_percent, 120)

    def test_codex_credit_guards_and_openrouter_floor(self):
        for credits in ({"has_credits": False, "balance": "5"}, {"balance": "-5"}, {"balance": "1e3"}):
            self.assertFalse(providers.parse("openai", {"credits": credits})[1])
        self.assertEqual(providers.parse("openrouter", {"_credits": {"total_credits": 5, "total_usage": 9}})[1][0].value, "0")

    def test_copilot_prefers_published_percentage_before_entitlement_ratio(self):
        windows, _, _ = providers.parse("copilot", {"quota_snapshots": {
            "premium_interactions": {"entitlement": 0, "remaining": 50, "percent_remaining": 80}}})
        self.assertAlmostEqual(windows[0].used, .2)

    def test_kiro_requires_plausible_epoch_seconds_reset(self):
        row = {"resourceType": "CREDIT", "currentUsageWithPrecision": 30, "usageLimitWithPrecision": 100}
        for reset in (None, 100, 1793617200000):
            self.assertFalse(providers.parse("kiro", {"nextDateReset": reset, "usageBreakdownList": [row]})[0])

    def test_grok_uses_daily_and_known_duration_labels(self):
        self.assertEqual(providers.parse("grok", {"config": {"creditUsagePercent": 20,
                         "currentPeriod": {"type": "USAGE_PERIOD_TYPE_DAILY"}}})[0][0].label, "1D")
        self.assertEqual(providers.parse("grok", {"config": {"creditUsagePercent": 20,
            "currentPeriod": {"start": "2026-11-01T00:00:00Z", "end": "2026-11-08T00:00:00Z"}}})[0][0].label, "WK")
