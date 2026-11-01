"""Webhook callbacks and the dead-letter list (see :mod:`dpdpkit.fastapi.webhooks` for delivery).

``erasure.due`` and ``export.requested`` webhooks are signed and delivered by the dpdpkit-fastapi outbox
(retried with backoff, dead-lettered after the last attempt). The customer's app acts on its own data, then
calls ``POST /v1/webhooks/confirmations`` with the event ``id`` from the webhook body. The server writes the
confirmation into the hash-chained ledger. A confirmed export also closes the access request; a failed one is
recorded and the request stays open, so it shows as overdue in the dashboard.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from dpdpkit.errors import DpdpkitError, NotFound
from dpdpkit.events import ERASURE_DUE, EXPORT_REQUESTED
from dpdpkit.fastapi import DPDPKit
from dpdpkit.fastapi.webhooks import WebhookDelivery, WebhookOutbox
from dpdpkit.server import auth
from dpdpkit.server.routes import require_admin, require_api_key

# event type -> (ledger subject type, action prefix)
_SUBJECTS = {ERASURE_DUE: ("erasure_schedule", "webhook.erasure"), EXPORT_REQUESTED: ("request", "webhook.export")}
_DEFAULT_EXPORT_RESPONSE = "Your data export has been delivered."


class Confirmation(BaseModel):
    event_type: Literal["erasure.due", "export.requested"]
    event_id: str = Field(min_length=1, max_length=128, description="The `id` of the webhook event being confirmed")
    subject_id: str = Field(
        min_length=1,
        max_length=128,
        description="`schedule_id` of an erasure.due event, or `request_id` of an export.requested event",
    )
    status: Literal["completed", "failed"]
    message: str = Field(default="", max_length=2000)


class ConfirmationResult(BaseModel):
    recorded: bool = Field(description="False when this event was already confirmed (the call is idempotent)")
    action: str


def _dpdpkit(request: Request) -> DPDPKit:
    kit = getattr(request.app.state, "dpdpkit", None)
    if not isinstance(kit, DPDPKit):
        raise HTTPException(503, "the dpdpkit engine is not configured (set DPDPKIT_DATABASE_URL)")
    return kit


def _outbox(request: Request) -> WebhookOutbox:
    outbox = _dpdpkit(request).webhooks
    if outbox is None:
        raise HTTPException(503, "webhooks need the SQL database")
    return outbox


router = APIRouter()


@router.post("/v1/webhooks/confirmations", response_model=ConfirmationResult, dependencies=[Depends(require_api_key)])
def confirm_webhook(body: Confirmation, request: Request) -> ConfirmationResult:
    """Confirm that the app acted on a webhook. The confirmation is recorded in the ledger."""
    dpdp = _dpdpkit(request)
    kit = dpdp.kit
    subject_type, prefix = _SUBJECTS[body.event_type]
    action = f"{prefix}.{'confirmed' if body.status == 'completed' else 'failed'}"
    try:
        if body.event_type == EXPORT_REQUESTED:
            kit.rights.get(body.subject_id)
        elif not any(s.id == body.subject_id for s in kit.retention.schedules(active_only=False)):
            raise NotFound(f"erasure schedule {body.subject_id} not found")
        if any(
            entry.data.get("event_id") == body.event_id and entry.action.startswith(prefix)
            for entry in kit.ledger.audit_entries(body.subject_id)
        ):
            return ConfirmationResult(recorded=False, action=action)
        data: dict[str, Any] = {"event_id": body.event_id, "message": body.message}
        kit.ledger.audit(action, subject_type=subject_type, subject_id=body.subject_id, actor="webhook", data=data)
        if body.event_type == EXPORT_REQUESTED and body.status == "completed":
            kit.rights.respond(body.subject_id, body.message or _DEFAULT_EXPORT_RESPONSE, actor="webhook")
    except DpdpkitError as exc:
        raise HTTPException(exc.http_status, exc.message) from exc
    return ConfirmationResult(recorded=True, action=action)


@router.get("/admin/webhooks/deliveries")
def list_deliveries(
    request: Request,
    _: Annotated[auth.Claims, Depends(require_admin)],
    status: Literal["pending", "delivered", "dead"] | None = None,
    limit: Annotated[int, Field(ge=1, le=500)] = 100,
) -> list[WebhookDelivery]:
    return _outbox(request).deliveries(status, limit=limit)


@router.get("/admin/webhooks/dead-letters")
def list_dead_letters(request: Request, _: Annotated[auth.Claims, Depends(require_admin)]) -> list[WebhookDelivery]:
    return _outbox(request).dead_letters()


@router.post("/admin/webhooks/redeliver")
def redeliver(
    request: Request, _: Annotated[auth.Claims, Depends(require_admin)], delivery_id: str | None = None
) -> dict[str, int]:
    """Move one dead delivery (or all of them) back to pending with a fresh attempt budget."""
    try:
        return {"requeued": _outbox(request).redeliver(delivery_id)}
    except DpdpkitError as exc:
        raise HTTPException(exc.http_status, exc.message) from exc
