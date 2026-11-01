"""The ``worker`` command: runs the periodic jobs (retention, ledger verification, root-hash export, webhook
delivery) in one process, next to a small HTTP server for ``/healthz``, ``/readyz`` and ``/metrics``.

Run one worker per database. The jobs are safe to repeat and webhook rows are leased, so a second worker only
wastes work. The web containers (``python -m dpdpkit.server``) do not run these jobs.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

from dpdpkit.fastapi import DPDPKit
from dpdpkit.fastapi.tasks import DELIVER_WEBHOOKS, EXPORT_ROOT, RETENTION, VERIFY_LEDGER, build_jobs
from dpdpkit.server.metrics import Metrics

log = logging.getLogger(__name__)

_UTC = dt.timezone.utc


@dataclass
class Job:
    name: str
    run: Callable[[], object]
    next_at: dt.datetime
    every: dt.timedelta | None = None  # interval jobs
    daily_at: dt.time | None = None  # UTC time of day for daily jobs

    def advance(self, now: dt.datetime) -> None:
        if self.every is not None:
            self.next_at = now + self.every
        elif self.daily_at is not None:
            self.next_at = _next_daily(now, self.daily_at)


def _next_daily(now: dt.datetime, at: dt.time) -> dt.datetime:
    candidate = dt.datetime.combine(now.date(), at, tzinfo=_UTC)
    return candidate if candidate > now else candidate + dt.timedelta(days=1)


class Worker:
    """Runs the jobs of :func:`dpdpkit.fastapi.tasks.build_jobs` at the cadence of ``DPDPKit.start_scheduler()``.

    Interval jobs run once at start-up; daily jobs wait for their hour (UTC). A failing job is logged and counted
    and does not stop the others."""

    def __init__(self, dpdp: DPDPKit, metrics: Metrics, *, now: Callable[[], dt.datetime] | None = None) -> None:
        self.metrics = metrics
        self._now = now or (lambda: dt.datetime.now(_UTC))
        start = self._now()
        jobs = build_jobs(dpdp)
        every = {RETENTION: dt.timedelta(minutes=15), DELIVER_WEBHOOKS: dt.timedelta(seconds=30)}
        daily = {VERIFY_LEDGER: dt.time(2), EXPORT_ROOT: dt.time(3)}
        self.jobs: list[Job] = []
        for name, run in jobs.items():
            if name in every:
                self.jobs.append(Job(name, run, start, every=every[name]))
            else:
                self.jobs.append(Job(name, run, _next_daily(start, daily[name]), daily_at=daily[name]))

    def run_due(self) -> int:
        """Run every job that is due now; returns how many ran."""
        now = self._now()
        ran = 0
        for job in self.jobs:
            if job.next_at > now:
                continue
            ran += 1
            try:
                job.run()
            except Exception:
                log.exception("job %s failed", job.name)
                self.metrics.job(job.name, False)
            else:
                self.metrics.job(job.name, True)
            job.advance(now)
        return ran

    def loop(self, stop: threading.Event, tick_seconds: float = 1.0) -> None:
        while not stop.is_set():
            self.run_due()
            stop.wait(tick_seconds)


def run_worker(dpdp: DPDPKit, metrics: Metrics) -> tuple[Worker, threading.Event, threading.Thread]:
    """Start the job loop in a daemon thread. Set the returned event to stop it."""
    worker = Worker(dpdp, metrics)
    stop = threading.Event()
    thread = threading.Thread(target=worker.loop, args=(stop,), daemon=True, name="dpdpkit-worker")
    thread.start()
    return worker, stop, thread
