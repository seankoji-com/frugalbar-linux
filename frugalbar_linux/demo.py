"""Isolated illustrative data. Never mixed with real provider reads."""
from .models import Snapshot, Window, Balance


def snapshots(now):
    return [
        Snapshot("claude", "Claude Code", (Window("5H", .82, now + 6420, 18000),
                 Window("WK", .41, now + 367200, 604800)), plan="Max 5x", measured_at=now),
        Snapshot("openai", "Codex", (Window("5H", .23, now + 11400, 18000),
                 Window("WK", .37, now + 439200, 604800)), plan="Plus", measured_at=now),
        Snapshot("gemini", "Gemini", (Window("5H", 1, now + 4800, 18000),
                 Window("WK", .34, now + 522000, 604800)), measured_at=now),
        Snapshot("antigravityArgon", "Argon", (Window("5H", .08, now + 15120, 18000),
                 Window("WK", .19, now + 522000, 604800)), measured_at=now),
        Snapshot("antigravityClaude", "Claude", (Window("5H", .46, now + 9000, 18000),
                 Window("WK", .22, now + 522000, 604800)), measured_at=now),
        Snapshot("opencode", "OpenCode Go", (Window("5H", .34, now + 7500, 18000),
                 Window("WK", .58, now + 273600, 604800), Window("MO", .48, now + 1555200)),
                 state="error", message="Timed out", measured_at=now - 1560, stale=True),
        Snapshot("copilot", "GitHub Copilot", (Window("MO", .46, now + 352800),),
                 plan="Pro", measured_at=now),
        Snapshot("grok", "Grok", state="error", message="Credential rejected. Check Settings."),
        Snapshot("openrouter", "OpenRouter", balances=(Balance("18.42", "USD"),), measured_at=now),
        Snapshot("deepseek", "DeepSeek", balances=(Balance("6.10", "USD", "Prepaid balance"),), measured_at=now),
    ]
