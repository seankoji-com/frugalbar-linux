"""Credentials stay in the desktop Secret Service, never the preferences file."""
import shutil
import subprocess


def available() -> bool:
    return shutil.which("secret-tool") is not None


def read_secret(provider: str) -> str | None:
    if not available():
        return None
    try:
        result = subprocess.run(
            ["secret-tool", "lookup", "application", "frugalbar-linux", "provider", provider],
            capture_output=True, text=True, timeout=3,
        )
        return result.stdout.strip() or None if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def save_secret(provider: str, value: str) -> bool:
    if not available():
        return False
    command = ["secret-tool", "store", "--label=FrugalBar Linux: " + provider] if value else ["secret-tool", "clear"]
    try:
        result = subprocess.run(
            command + ["application", "frugalbar-linux", "provider", provider],
            input=value, capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
