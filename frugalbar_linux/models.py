"""Published observations. Missing readings never imply unused quota."""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import math


@dataclass(frozen=True)
class Window:
    label: str
    used: float | None
    resets_at: float | None = None
    duration: float | None = None
    blocked: bool = False
    detail: str = ""
    reported_percent: float | None = None

    def __post_init__(self):
        if self.used is not None and (
            isinstance(self.used, bool) or not isinstance(self.used, (int, float))
            or not math.isfinite(self.used) or not 0 <= self.used <= 1
        ):
            raise ValueError("Invalid published fraction")
        for value in (self.resets_at, self.duration):
            if value is not None and (not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value <= 0):
                raise ValueError("Invalid published time")

    def pace(self, now: float) -> float | None:
        if (self.used is None or self.used >= 1 or not self.duration
                or not self.resets_at or self.resets_at <= now):
            return None
        return min(1, max(0, 1 - (self.resets_at - now) / self.duration))


@dataclass(frozen=True)
class Balance:
    value: str
    unit: str
    kind: str = "Account credit"

    def __post_init__(self):
        try:
            if not Decimal(self.value).is_finite():
                raise ValueError("Invalid published balance")
        except InvalidOperation:
            raise ValueError("Invalid published balance") from None


@dataclass(frozen=True)
class Snapshot:
    provider: str
    name: str
    windows: tuple[Window, ...] = ()
    balances: tuple[Balance, ...] = ()
    plan: str = ""
    state: str = "measured"
    message: str = ""
    measured_at: float | None = None
    stale: bool = False
    retry_at: float | None = None
    source: str = ""
    credential_id: str = field(default="", repr=False)
    critical: bool = False


def urgency(window: Window, now: float) -> str:
    if window.blocked or window.used is not None and window.used >= .95:
        return "critical"
    if window.used is not None and window.used >= .8:
        return "warning"
    return "normal"


def tray_reading(snapshots: list[Snapshot], now: float) -> tuple[str, str, str]:
    """Match the menu title: tightest live, unspent subscription window."""
    live = [snapshot for snapshot in snapshots
               if snapshot.state == "measured" and not snapshot.stale
               and snapshot.provider not in {"githubRest", "githubGraphql"}]
    published = [window for snapshot in live for window in snapshot.windows
                 if window.used is not None or window.blocked]
    windows = [(snapshot, window) for snapshot in live
               for window in snapshot.windows
               if window.used is not None and window.used < 1 and not window.blocked]
    level = "normal" if published else "unknown"
    for snapshot in live:
        for window in snapshot.windows:
            candidate = urgency(window, now)
            if candidate == "critical":
                level = "critical"
            elif candidate == "warning" and level != "critical":
                level = "warning"
    if not windows:
        return "FrugalBar", "No current unspent subscription window", level
    snapshot, window = max(windows, key=lambda pair: pair[1].used)
    remaining = (1 - window.used) * 100
    return f"{window.label} {remaining:.0f}%", f"{snapshot.name} · {window.label} · {remaining:.0f}% left", level


def countdown(resets_at: float | None, now: float) -> str:
    if resets_at is None:
        return "Reset not published"
    seconds = resets_at - now
    if seconds <= 0:
        return "Reset passed; awaiting reading"
    minutes = math.ceil(seconds / 60)
    if minutes >= 1440:
        return f"{minutes // 1440}d {(minutes % 1440) // 60}h"
    if minutes >= 60:
        return f"{minutes // 60}h {minutes % 60}m"
    return f"{minutes}m"
