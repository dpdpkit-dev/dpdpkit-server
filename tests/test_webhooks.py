from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient

from dpdpkit.events import WebhookEndpoint, verify_signature
from dpdpkit.fastapi import DPDPKit
from dpdpkit.models import RequestStatus
from dpdpkit.server import auth
from dpdpkit.server.app import create_app
from dpdpkit.server.settings import Settings

KEY, KEY_HASH = auth.generate_api_key()
CONFIG: dict[str, Any] = {
    "policy": "dpdp-rules-2025.v1",
    "contact": {"name": "Shop", "email": "privacy@shop.example.in", "rights_url": "https://shop.example.in/rights"},
    "data_items": [{"id": "email", "name": "Email address"}],
    "purposes": [
        {
            "id": "marketing",
            "title": "Send you offers",
            "description": "Occasional emails about products.",
            "data_items": ["email"],
            "retention": {"trigger": "withdrawal", "period_days": 0},
        }
    ],
    "notice": {
        "title": "How we use your data",
        "body": "Choose what you agree to.",
        "links": {
            "withdraw": "https://shop.example.in/prefs",
            "rights": "https://shop.example.in/rights",
            "board_complaint": "https://shop.example.in/board",
        },
    },
}


class Receiver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, dict[str, str]]] = []

    def __call__(self, url: str, body: bytes, headers: dict[str, str]) -> int:
        self.calls.append((url, body, headers))
        return 200


@pytest.fixture
def receiver() -> Receiver:
    return Receiver()


@pytest.fixture
def dpdp(receiver: Receiver) -> DPDPKit:
    kit = DPDPKit(
        db_url="sqlite://",
        config=CONFIG,
        principal_resolver=lambda r: None,
        signing_key="k",
        create_tables=True,
        webhooks=[WebhookEndpoint(id="app", url="https://app.example.in/hooks", secret="whsec")],
    )
    assert kit.webhooks is not None
    kit.webhooks.sender = receiver
    return kit


@pytest.fixture
def client(dpdp: DPDPKit) -> TestClient:
    settings = Settings(signing_key="s3cret", api_key_hashes=(KEY_HASH,), admin_password_hash=auth.hash_password("pw"))
    return TestClient(create_app(settings, dpdp))


AUTH = {"Authorization": f"Bearer {KEY}"}


def confirm(client: TestClient, **body: Any) -> Any:
    return client.post("/v1/webhooks/confirmations", json=body, headers=AUTH)


def admin(client: TestClient) -> dict[str, str]:
    token = client.post("/admin/login", json={"password": "pw"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_export_webhook_is_signed_and_confirmation_closes_request(
    client: TestClient, dpdp: DPDPKit, receiver: Receiver
) -> None:
    request = dpdp.kit.rights.open("u1", "access")
    assert dpdp.webhooks is not None
    dpdp.webhooks.deliver_due()
    url, body, headers = next(c for c in receiver.calls if c[2]["X-DPDPKit-Event"] == "export.requested")
    assert url == "https://app.example.in/hooks"
    assert verify_signature("whsec", body, headers["X-DPDPKit-Signature"])

    payload = {"event_type": "export.requested", "event_id": "ev_1", "subject_id": request.id, "status": "completed"}
    first = confirm(client, **payload)
    assert first.status_code == 200 and first.json() == {"recorded": True, "action": "webhook.export.confirmed"}
    assert dpdp.kit.rights.get(request.id).status is RequestStatus.COMPLETED
    entries = [e for e in dpdp.kit.ledger.audit_entries(request.id) if e.action == "webhook.export.confirmed"]
    assert len(entries) == 1 and entries[0].data["event_id"] == "ev_1"
    assert dpdp.kit.ledger.verify().ok

    again = confirm(client, **payload)
    assert again.status_code == 200 and again.json()["recorded"] is False
    assert len([e for e in dpdp.kit.ledger.audit_entries(request.id) if e.action.startswith("webhook.")]) == 1


def test_failed_export_is_recorded_and_request_stays_open(client: TestClient, dpdp: DPDPKit) -> None:
    request = dpdp.kit.rights.open("u1", "access")
    response = confirm(
        client,
        event_type="export.requested",
        event_id="ev_2",
        subject_id=request.id,
        status="failed",
        message="db down",
    )
    assert response.json()["action"] == "webhook.export.failed"
    assert dpdp.kit.rights.get(request.id).status is not RequestStatus.COMPLETED


def test_erasure_confirmation_is_recorded_in_ledger(client: TestClient, dpdp: DPDPKit) -> None:
    at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)
    schedule = dpdp.kit.retention.schedule("u1", "marketing", at, reason="test", actor="t")
    response = confirm(client, event_type="erasure.due", event_id="ev_3", subject_id=schedule.id, status="completed")
    assert response.json() == {"recorded": True, "action": "webhook.erasure.confirmed"}
    actions = [e.action for e in dpdp.kit.ledger.audit_entries(schedule.id)]
    assert "webhook.erasure.confirmed" in actions


def test_unknown_subject_is_404(client: TestClient) -> None:
    for event_type in ("export.requested", "erasure.due"):
        response = confirm(client, event_type=event_type, event_id="e", subject_id="nope", status="completed")
        assert response.status_code == 404


def test_confirmation_requires_api_key_and_engine(client: TestClient) -> None:
    body = {"event_type": "erasure.due", "event_id": "e", "subject_id": "s", "status": "completed"}
    assert client.post("/v1/webhooks/confirmations", json=body).status_code == 401
    bare = TestClient(create_app(Settings(api_key_hashes=(KEY_HASH,))))
    assert bare.post("/v1/webhooks/confirmations", json=body, headers=AUTH).status_code == 503
    assert confirm(client, **{**body, "event_type": "other"}).status_code == 422


def test_dead_letters_listed_and_redelivered(client: TestClient, dpdp: DPDPKit, receiver: Receiver) -> None:
    assert dpdp.webhooks is not None
    dpdp.webhooks.sender = lambda url, body, headers: 500
    dpdp.webhooks.max_attempts = 1
    dpdp.kit.rights.open("u1", "access")
    dpdp.webhooks.deliver_due()

    assert client.get("/admin/webhooks/dead-letters").status_code == 401
    headers = admin(client)
    dead = client.get("/admin/webhooks/dead-letters", headers=headers).json()
    assert dead and all(d["status"] == "dead" for d in dead)
    assert len(client.get("/admin/webhooks/deliveries?status=dead", headers=headers).json()) == len(dead)

    requeued = client.post("/admin/webhooks/redeliver", headers=headers)
    assert requeued.json() == {"requeued": len(dead)}
    assert client.get("/admin/webhooks/dead-letters", headers=headers).json() == []
    missing = client.post("/admin/webhooks/redeliver?delivery_id=wh_missing", headers=headers)
    assert missing.status_code == 404
