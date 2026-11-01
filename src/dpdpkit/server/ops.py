"""Operational endpoints: ``/readyz`` (the database answers) and ``/metrics`` (Prometheus).

Like ``/healthz`` they need no credentials, so probes and scrapers can reach them; keep them off the public
internet. They expose counts only, never personal data.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from dpdpkit.fastapi import DPDPKit
from dpdpkit.fastapi.repository import SqlAlchemyRepository
from dpdpkit.server import __version__

log = logging.getLogger(__name__)

router = APIRouter()


def database_error(request: Request) -> str | None:
    """Why the database is unusable, or ``None`` when ``SELECT 1`` succeeds."""
    kit = getattr(request.app.state, "dpdpkit", None)
    if not isinstance(kit, DPDPKit):
        return "no database configured (set DPDPKIT_DATABASE_URL)"
    try:
        if isinstance(kit.repository, SqlAlchemyRepository):
            with kit.repository.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
    except Exception as exc:
        log.warning("readiness check failed: %s", exc)
        return "database unreachable"
    return None


@router.get("/readyz", include_in_schema=False)
def readyz(request: Request) -> Response:
    error = database_error(request)
    if error:
        return JSONResponse({"status": "unavailable", "reason": error}, status_code=503)
    return JSONResponse({"status": "ready"})


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request) -> Response:
    ready = database_error(request) is None
    deliveries = None
    kit = getattr(request.app.state, "dpdpkit", None)
    if ready and isinstance(kit, DPDPKit) and kit.webhooks is not None:
        deliveries = kit.webhooks.counts()
    body = request.app.state.metrics.render(__version__, ready, deliveries)
    return Response(body, media_type="text/plain; version=0.0.4; charset=utf-8")
