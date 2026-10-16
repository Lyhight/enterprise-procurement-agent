from __future__ import annotations

from collections import Counter
from threading import Lock


class ApplicationMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._request_count = 0
        self._error_count = 0
        self._duration_ms = 0.0
        self._status_counts: Counter[str] = Counter()

    def observe(self, status_code: int, duration_ms: float) -> None:
        with self._lock:
            self._request_count += 1
            self._duration_ms += duration_ms
            self._status_counts[str(status_code)] += 1
            if status_code >= 500:
                self._error_count += 1

    def snapshot(self) -> dict:
        with self._lock:
            average = self._duration_ms / self._request_count if self._request_count else 0.0
            return {
                "request_count": self._request_count,
                "server_error_count": self._error_count,
                "average_duration_ms": round(average, 3),
                "status_counts": dict(self._status_counts),
            }


metrics = ApplicationMetrics()
