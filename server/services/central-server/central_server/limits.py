"""Process-local token buckets: one misbehaving hub or client must not crowd out the others."""

from __future__ import annotations

import math
import threading
import time


class Limiter:
    """A request needs one token from every (capacity, period_seconds) bucket of its key."""

    MAX_KEYS = 1024  # client addresses are attacker-chosen: memory stays bounded regardless

    def __init__(self, *rates, clock=time.monotonic):
        self.rates, self.clock = rates, clock
        self.lock, self.buckets = threading.Lock(), {}

    def take(self, key) -> int:
        """Return 0 when the request may proceed, else whole seconds until a token is available."""
        now = self.clock()
        with self.lock:
            levels = self.buckets.get(key)
            if levels is None:
                if len(self.buckets) >= self.MAX_KEYS:
                    self.prune(now)
                levels = self.buckets[key] = [[capacity, now] for capacity, _ in self.rates]
            wait = 0.0
            for (capacity, period), level in zip(self.rates, levels):
                level[0] = min(capacity, level[0]+(now-level[1])*capacity/period)
                level[1] = now
                if level[0] < 1:
                    wait = max(wait, (1-level[0])*period/capacity)
            if not wait:
                for level in levels:
                    level[0] -= 1
            return math.ceil(wait)

    def prune(self, now):
        """Drop keys whose buckets have refilled by now; if all are still busy, drop the oldest."""
        for key, levels in list(self.buckets.items()):
            if all(level[0]+(now-level[1])*capacity/period >= capacity
                   for (capacity, period), level in zip(self.rates, levels)):
                del self.buckets[key]
        while len(self.buckets) >= self.MAX_KEYS:
            del self.buckets[next(iter(self.buckets))]
