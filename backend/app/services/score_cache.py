"""Small process-local cache of decoded scores; never retains or writes a PDF.

Only values serialized here enter the cache. Deserialization gives each caller
its own score, so edits cannot contaminate another import. Limits apply to the
actual serialized bytes, not the much smaller compressed input PDF.
"""

from collections import OrderedDict
import pickle
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.score_pdf import ParsedScore


class ScoreCache:
    def __init__(self, max_bytes: int = 8 * 1024 * 1024, max_entries: int = 4, ttl: float = 300):
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self.ttl = ttl
        self._entries: OrderedDict[tuple, tuple[float, bytes]] = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    def _expire(self) -> None:
        now = time.monotonic()
        for key, (expires, _) in list(self._entries.items()):
            if expires <= now:
                self._remove(key)

    def _remove(self, key: tuple) -> None:
        self._bytes -= len(self._entries.pop(key)[1])

    def get(self, key: tuple) -> "ParsedScore | None":
        with self._lock:
            self._expire()
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            payload = entry[1]
        # This payload was produced by put(), never supplied by a client or disk.
        return pickle.loads(payload)

    def put(self, key: tuple, score: "ParsedScore") -> None:
        payload = pickle.dumps(score, protocol=pickle.HIGHEST_PROTOCOL)
        if len(payload) > self.max_bytes or self.max_entries < 1:
            return
        with self._lock:
            self._expire()
            if key in self._entries:
                self._remove(key)
            while self._entries and (len(self._entries) >= self.max_entries or self._bytes + len(payload) > self.max_bytes):
                self._remove(next(iter(self._entries)))
            self._entries[key] = (time.monotonic() + self.ttl, payload)
            self._bytes += len(payload)
