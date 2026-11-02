from dataclasses import replace
import unittest
from frugalbar_linux.engine import Engine
from frugalbar_linux.models import Snapshot, Window, Balance, tray_reading, countdown


class PollTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.calls = 0
        self.value = Snapshot("claude", "Claude", (Window("5H", .8, 2000, 18000),), measured_at=1000)
        def fetch(*args, **kwargs):
            self.calls += 1
            return self.value
        self.engine = Engine(fetch, [("claude", "Claude")], clock=lambda: self.now)

    def test_failure_keeps_last_reading_but_marks_stale(self):
        self.engine.refresh()
        self.value = Snapshot("claude", "Claude", state="error", message="Timed out")
        self.now += 120
        self.engine.refresh()
        retained = self.engine.snapshots["claude"]
        self.assertEqual(retained.windows[0].used, .8)
        self.assertEqual(retained.measured_at, 1000)
        self.assertTrue(retained.stale)
        self.assertEqual(tray_reading([retained], self.now)[0], "FrugalBar")

    def test_vendor_cooldown_and_manual_floor_are_independent(self):
        self.value = Snapshot("claude", "Claude", state="rate_limited", retry_at=2000)
        self.engine.refresh()
        self.now = 1200
        self.engine.refresh()
        self.assertEqual(self.calls, 1)
        self.engine.refresh(manual=True)
        self.assertEqual(self.calls, 2)
        self.engine.refresh(manual=True)
        self.assertEqual(self.calls, 2)
        self.now = 1230
        self.value = replace(self.value, retry_at=None)
        self.engine.refresh(manual=True)
        self.assertEqual(self.engine.next_poll["claude"], 2000)

    def test_removed_credential_clears_carried_reading(self):
        self.engine.refresh()
        self.value = Snapshot("claude", "Claude", state="not_configured")
        self.engine.credentials_changed()
        self.engine.refresh()
        self.assertFalse(self.engine.snapshots["claude"].windows)

    def test_success_replaces_stale(self):
        self.engine.accept(self.value)
        self.engine.accept(Snapshot("claude", "Claude", state="error"))
        self.engine.accept(replace(self.value, measured_at=1100))
        self.assertFalse(self.engine.snapshots["claude"].stale)

    def test_account_change_does_not_carry_another_accounts_reading(self):
        self.engine.accept(replace(self.value, credential_id="old-account"))
        self.engine.accept(Snapshot("claude", "Claude", state="error", credential_id="new-account"))
        self.assertFalse(self.engine.snapshots["claude"].windows)
        self.assertFalse(self.engine.snapshots["claude"].stale)

    def test_in_flight_read_cannot_restore_a_removed_credential(self):
        def removed_during_fetch(*args, **kwargs):
            self.engine.credentials_changed()
            return self.value
        self.engine.fetch = removed_during_fetch
        self.engine.refresh()
        self.assertFalse(self.engine.snapshots["claude"].windows)


class DisplaySemantics(unittest.TestCase):
    def test_unknown_is_neither_zero_nor_exhausted(self):
        window = Window("5H", None)
        self.assertIsNone(window.used)
        self.assertIsNone(window.pace(1000))
        for value in (float("nan"), float("inf"), -1, 1.1, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Window("5H", value)

    def test_tray_excludes_spent_stale_balances_and_developer_rates(self):
        values = [Snapshot("claude", "Claude", (Window("5H", .82),)),
                  Snapshot("openai", "Codex", (Window("WK", .99),), stale=True),
                  Snapshot("gemini", "Gemini", (Window("5H", 1),)),
                  Snapshot("githubRest", "GitHub", (Window("1H", .98),)),
                  Snapshot("deepseek", "DeepSeek", balances=(Balance("10.01", "USD"),))]
        title, tooltip, level = tray_reading(values, 1000)
        self.assertEqual(title, "5H 18%")
        self.assertIn("Claude", tooltip)
        self.assertEqual(level, "critical")

    def test_pace_requires_both_published_length_and_future_reset(self):
        self.assertIsNone(Window("5H", .5, 2000).pace(1000))
        self.assertIsNone(Window("5H", .5, 900, 18000).pace(1000))
        self.assertIsNone(Window("5H", 1, 2000, 18000).pace(1000))
        self.assertAlmostEqual(Window("5H", .5, 10000, 18000).pace(1000), .5)

    def test_passed_reset_does_not_imply_restored_quota(self):
        self.assertEqual(countdown(900, 1000), "Reset passed; awaiting reading")
        self.assertEqual(countdown(None, 1000), "Reset not published")

    def test_balance_keeps_exact_decimal(self):
        balance = Balance("123.456789012345678901", "USD")
        self.assertEqual(balance.value, "123.456789012345678901")
