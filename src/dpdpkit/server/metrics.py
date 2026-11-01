"""Prometheus metrics in the text exposition format, without a client library dependency."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterable

Labels = tuple[tuple[str, str], ...]


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def format_sample(name: str, value: float, labels: Labels = ()) -> str:
    if labels:
        name += "{" + ",".join(f'{key}="{_escape(val)}"' for key, val in labels) + "}"
    return f"{name} {value:g}"


class Metrics:
    """Counters and gauges the server and the worker update, safe to use from several threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[Labels, int] = {}
        self._job_runs: dict[Labels, int] = {}
        self._job_last_success: dict[str, float] = {}

    def request(self, method: str, status: int) -> None:
        key: Labels = (("method", method), ("status", str(status)))
        with self._lock:
            self._requests[key] = self._requests.get(key, 0) + 1

    def job(self, name: str, ok: bool, at: float | None = None) -> None:
        key: Labels = (("job", name), ("result", "ok" if ok else "error"))
        with self._lock:
            self._job_runs[key] = self._job_runs.get(key, 0) + 1
            if ok:
                self._job_last_success[name] = time.time() if at is None else at

    def render(self, version: str, ready: bool, deliveries: dict[str, int] | None = None) -> str:
        """The exposition text. ``deliveries`` are webhook counts by status, when the database is reachable."""
        with self._lock:
            requests, job_runs, last_success = dict(self._requests), dict(self._job_runs), dict(self._job_last_success)
        lines: list[str] = []

        def family(name: str, kind: str, help_text: str, samples: Iterable[str]) -> None:
            lines.extend([f"# HELP {name} {help_text}", f"# TYPE {name} {kind}", *samples])

        family(
            "dpdpkit_server_info",
            "gauge",
            "Server version.",
            [format_sample("dpdpkit_server_info", 1, (("version", version),))],
        )
        family(
            "dpdpkit_server_ready",
            "gauge",
            "1 when the database answers.",
            [format_sample("dpdpkit_server_ready", int(ready))],
        )
        family(
            "dpdpkit_http_requests_total",
            "counter",
            "HTTP requests served.",
            [format_sample("dpdpkit_http_requests_total", n, key) for key, n in sorted(requests.items())],
        )
        family(
            "dpdpkit_job_runs_total",
            "counter",
            "Worker job runs.",
            [format_sample("dpdpkit_job_runs_total", n, key) for key, n in sorted(job_runs.items())],
        )
        family(
            "dpdpkit_job_last_success_timestamp_seconds",
            "gauge",
            "Unix time of the last successful run of a worker job.",
            [
                format_sample("dpdpkit_job_last_success_timestamp_seconds", at, (("job", name),))
                for name, at in sorted(last_success.items())
            ],
        )
        family(
            "dpdpkit_webhook_deliveries",
            "gauge",
            "Webhook deliveries by status.",
            [
                format_sample("dpdpkit_webhook_deliveries", n, (("status", status),))
                for status, n in sorted((deliveries or {}).items())
            ],
        )
        return "\n".join(lines) + "\n"
