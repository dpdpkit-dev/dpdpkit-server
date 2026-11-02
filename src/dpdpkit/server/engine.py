"""Builds the dpdpkit engine from the server settings."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Request

from dpdpkit.errors import ConfigError
from dpdpkit.fastapi import DPDPKit
from dpdpkit.guardians import CallbackVerifier, VerifierRequest
from dpdpkit.server import auth
from dpdpkit.server.settings import Settings

CONFORMANCE_PRINCIPAL_HEADER = "X-DPDP-Test-Principal"
CONFORMANCE_ROLE_HEADER = "X-DPDP-Test-Role"


def _no_principal(request: Request) -> None:
    # Replaced by bind_auth() once the engine is attached to an app.
    return None


def _token(request: Request, settings: Settings, token_type: str) -> auth.Claims | None:
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not value.strip() or not settings.signing_key:
        return None
    try:
        return auth.verify_token(settings.signing_key, token_type, value.strip())
    except auth.AuthError:
        return None


def bind_auth(dpdpkit: DPDPKit, settings: Settings) -> None:
    """Make the engine's ``/dpdp`` endpoints use the server's credentials.

    The data principal is the subject of a signed end-user token and the admin role (``admin``) comes from an
    admin session token. With ``DPDPKIT_CONFORMANCE=1`` the test headers of dpdpkit-spec are used instead, so
    the conformance suite can act as any user or role; never enable that outside tests.
    """
    if settings.conformance:
        dpdpkit.principal_resolver = lambda request: request.headers.get(CONFORMANCE_PRINCIPAL_HEADER)
        dpdpkit.admin_guard = lambda request: request.headers.get(CONFORMANCE_ROLE_HEADER)
        return

    def principal(request: Request) -> str | None:
        claims = _token(request, settings, auth.USER_TOKEN)
        return claims.subject if claims else None

    def role(request: Request) -> str | None:
        return "admin" if _token(request, settings, auth.ADMIN_TOKEN) else None

    dpdpkit.principal_resolver = principal
    dpdpkit.admin_guard = role


CONFORMANCE_GUARDIAN_METHODS = ("existing_kyc", "digilocker_token", "partner_token", "court_order")


def _conformance_verifiers() -> list[CallbackVerifier]:
    """Test-only guardian verifiers: only the evidence token "demo-ok" passes."""

    def check(request: VerifierRequest, evidence: Mapping[str, Any]) -> bool:
        return evidence.get("token") == "demo-ok"

    return [CallbackVerifier(method, check) for method in CONFORMANCE_GUARDIAN_METHODS]


def build_dpdpkit(settings: Settings) -> DPDPKit | None:
    """The engine for ``settings.database_url``, or ``None`` when no database is configured."""
    if not settings.database_url:
        return None
    if settings.config_path is None:
        raise ConfigError("DPDPKIT_DATABASE_URL needs a dpdpkit.yaml (set DPDPKIT_CONFIG or mount it)")
    return DPDPKit(
        principal_resolver=_no_principal,
        db_url=settings.database_url,
        config=settings.config_path,
        signing_key=settings.signing_key,
        migrate_on_startup=settings.migrate_on_startup,
        guardian_verifiers=_conformance_verifiers() if settings.conformance else [],
    )
