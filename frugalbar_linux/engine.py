"""Bounded polling, vendor cooldown and explicit last-known observations."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import threading
import time
from .models import Snapshot


class Engine:
    def __init__(self, fetch, definitions, clock=time.time):
        self.fetch = fetch
        self.definitions = tuple(definitions)
        self.clock = clock
        self.snapshots = {key: Snapshot(key, name, state="not_configured",
                                       message="Not configured") for key, name in self.definitions}
        self.next_poll = {}
        self.next_manual = {}
        self._lock = threading.Lock()
        self.stopped = threading.Event()
        self.generation = 0

    def refresh(self, *, manual=False, discover=False, on_update=lambda: None):
        if not self._lock.acquire(blocking=False):
            return False
        try:
            now = self.clock()
            generation = self.generation
            due = [key for key, _ in self.definitions
                   if not self.stopped.is_set() and now >= (
                       self.next_manual.get(key, 0) if manual else self.next_poll.get(key, 0))]
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(self.fetch, key, discover=discover): key for key in due}
                for future in as_completed(futures):
                    if self.stopped.is_set():
                        for pending in futures:
                            pending.cancel()
                        break
                    key = futures[future]
                    try:
                        snapshot = future.result()
                    except Exception:
                        # Never show exception text: it can contain a credential or body.
                        snapshot = Snapshot(key, self.snapshots[key].name, state="error",
                                            message="Read failed. Check Settings or try again.")
                    if generation != self.generation:
                        continue
                    self.accept(snapshot)
                    on_update()
            return bool(due)
        finally:
            self._lock.release()

    def accept(self, snapshot):
        now = self.clock()
        previous = self.snapshots[snapshot.provider]
        if (snapshot.state not in {"measured", "not_configured"} and previous.measured_at is not None
                and snapshot.credential_id == previous.credential_id):
            snapshot = replace(snapshot, windows=previous.windows, balances=previous.balances,
                               measured_at=previous.measured_at, stale=True,
                               plan=snapshot.plan or previous.plan, source=previous.source)
        self.snapshots[snapshot.provider] = snapshot
        deadline = max(now + 120, snapshot.retry_at or 0)
        # Preserve an earlier vendor instruction across manual failures.
        if snapshot.state != "measured":
            deadline = max(deadline, self.next_poll.get(snapshot.provider, 0))
        self.next_poll[snapshot.provider] = deadline
        self.next_manual[snapshot.provider] = now + 30

    def credentials_changed(self):
        self.generation += 1
        self.next_poll.clear()
        self.next_manual.clear()
        self.snapshots = {key: Snapshot(key, name, state="not_configured",
                                       message="Not configured") for key, name in self.definitions}
