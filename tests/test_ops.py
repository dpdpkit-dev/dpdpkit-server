from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from test_webhooks import CONFIG, Receiver

from dpdpkit.events import WebhookEndpoint
from dpdpkit.fastapi import DPDPKit
from dpdpkit.server.app import create_app
from dpdpkit.server.metrics import Metrics
from dpdpkit.server.settings import Settings
from dpdpkit.server.worker import Worker


@pytest.fixture
def dpdp() -> DPDPKit:
    kit = DPDPKit(
        db_url="sqlite://",
        config=CONFIG,
        principal_resolver=lambda r: None,
        signing_key="k",
        create_tables=True,
        webhooks=[WebhookEndpoint(id="app", url="https://app.example.in/hooks", secret="whsec")],
    )
    assert kit.webhooks is not None
    kit.webhooks.sender = Receiver()
    return kit


def test_readyz_without_database_is_unavailable() -> None:
    response = TestClient(create_app(Settings())).get("/readyz")
    assert response.status_code == 503
    assert "DPDPKIT_DATABASE_URL" in response.json()["reason"]


def test_readyz_with_database(dpdp: DPDPKit) -> None:
    response = TestClient(create_app(Settings(), dpdp)).get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_metrics_exposition(dpdp: DPDPKit) -> None:
    client = TestClient(create_app(Settings(), dpdp))
    client.get("/healthz")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "dpdpkit_server_ready 1" in body
    assert 'dpdpkit_http_requests_total{method="GET",status="200"} 1' in body
    assert 'dpdpkit_webhook_deliveries{status="pending"} 0' in body


def test_metrics_without_database() -> None:
    body = TestClient(create_app(Settings())).get("/metrics").text
    assert "dpdpkit_server_ready 0" in body
    assert "dpdpkit_webhook_deliveries{" not in body


def test_worker_runs_interval_jobs_at_start_and_daily_jobs_later(dpdp: DPDPKit) -> None:
    clock = [dt.datetime(2026, 11, 1, 1, 0, tzinfo=dt.timezone.utc)]
    metrics = Metrics()
    worker = Worker(dpdp, metrics, now=lambda: clock[0])
    assert worker.run_due() == 2  # retention and webhook delivery
    assert worker.run_due() == 0
    clock[0] = dt.datetime(2026, 11, 1, 2, 0, 30, tzinfo=dt.timezone.utc)
    assert worker.run_due() == 3  # retention (15 min), webhooks (30 s) and ledger verification (02:00)
    body = metrics.render("x", True)
    assert 'dpdpkit_job_runs_total{job="dpdpkit.verify_ledger",result="ok"} 1' in body
    assert 'dpdpkit_job_last_success_timestamp_seconds{job="dpdpkit.retention"}' in body


def test_worker_job_failure_is_counted_and_does_not_stop_others(dpdp: DPDPKit) -> None:
    metrics = Metrics()
    worker = Worker(dpdp, metrics)

    def boom() -> None:
        raise RuntimeError("down")

    worker.jobs[0].run = boom
    assert worker.run_due() == 2
    body = metrics.render("x", True)
    assert 'dpdpkit_job_runs_total{job="dpdpkit.retention",result="error"} 1' in body
    assert 'dpdpkit_job_runs_total{job="dpdpkit.deliver_webhooks",result="ok"} 1' in body
