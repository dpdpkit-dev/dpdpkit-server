"""HTTP endpoints and dependencies for authentication (see :mod:`dpdpkit.server.auth`)."""

from __future__ import annotations

import secrets
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from dpdpkit.server import auth
from dpdpkit.server.settings import Settings

OIDC_STATE_COOKIE = "dpdpkit_oidc_state"
OIDC_STATE_TYPE = "oidc-state"
_DENIED = {"WWW-Authenticate": "Bearer"}


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _signing_key(settings: Settings) -> str:
    if not settings.signing_key:
        raise HTTPException(503, "DPDPKIT_SIGNING_KEY is not configured")
    return settings.signing_key


def _bearer(request: Request) -> str:
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        raise HTTPException(401, "missing bearer credential", headers=_DENIED)
    return value.strip()


def require_api_key(request: Request) -> None:
    """Dependency: the request carries a configured API key."""
    if not auth.verify_api_key(_bearer(request), _settings(request).api_key_hashes):
        raise HTTPException(401, "invalid API key", headers=_DENIED)


def _claims(request: Request, token_type: str) -> auth.Claims:
    try:
        return auth.verify_token(_signing_key(_settings(request)), token_type, _bearer(request))
    except auth.AuthError as exc:
        raise HTTPException(401, str(exc), headers=_DENIED) from exc


def require_user_token(request: Request) -> auth.Claims:
    """Dependency: the request carries a valid end-user token; returns its claims."""
    return _claims(request, auth.USER_TOKEN)


def require_admin(request: Request) -> auth.Claims:
    """Dependency: the request carries a valid admin session token; returns its claims."""
    return _claims(request, auth.ADMIN_TOKEN)


class TokenRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=256, description="Your identifier of the end user (data principal)")
    scope: str = Field(default="", max_length=256)
    ttl_seconds: int = Field(default=auth.DEFAULT_USER_TTL, ge=30, le=24 * 3600)


class TokenResponse(BaseModel):
    token: str
    expires_at: int


class LoginRequest(BaseModel):
    password: str


router = APIRouter()


@router.post("/v1/tokens", response_model=TokenResponse, dependencies=[Depends(require_api_key)])
def create_user_token(body: TokenRequest, request: Request) -> TokenResponse:
    """Mint a signed end-user token for a widget. Called by the app's backend with its API key."""
    key = _signing_key(_settings(request))
    token = auth.issue_token(key, auth.USER_TOKEN, body.subject, ttl=body.ttl_seconds, scope=body.scope)
    return TokenResponse(token=token, expires_at=auth.verify_token(key, auth.USER_TOKEN, token).expires_at)


def _admin_session(settings: Settings, subject: str) -> TokenResponse:
    key = _signing_key(settings)
    token = auth.issue_token(key, auth.ADMIN_TOKEN, subject, ttl=auth.DEFAULT_ADMIN_TTL)
    return TokenResponse(token=token, expires_at=auth.verify_token(key, auth.ADMIN_TOKEN, token).expires_at)


@router.post("/admin/login", response_model=TokenResponse)
def admin_login(body: LoginRequest, request: Request) -> TokenResponse:
    settings = _settings(request)
    if not settings.admin_password_hash:
        raise HTTPException(404, "password login is not configured")
    if not auth.verify_password(body.password, settings.admin_password_hash):
        raise HTTPException(401, "wrong password")
    return _admin_session(settings, "admin")


@router.get("/admin/session")
def admin_session(claims: Annotated[auth.Claims, Depends(require_admin)]) -> dict[str, Any]:
    return {"subject": claims.subject, "expires_at": claims.expires_at}


def _oidc_endpoints(settings: Settings) -> dict[str, Any]:
    if not (
        settings.oidc_issuer and settings.oidc_client_id and settings.oidc_client_secret and settings.oidc_redirect_uri
    ):
        raise HTTPException(404, "OIDC login is not configured")
    url = settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
    try:
        response = httpx.get(url, timeout=10)
        response.raise_for_status()
        document: dict[str, Any] = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "cannot read the OIDC provider's configuration") from exc
    return document


@router.get("/admin/oidc/login", include_in_schema=False)
def oidc_login(request: Request) -> RedirectResponse:
    settings = _settings(request)
    endpoints = _oidc_endpoints(settings)
    state = auth.issue_token(_signing_key(settings), OIDC_STATE_TYPE, secrets.token_urlsafe(16), ttl=600)
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.oidc_client_id,
            "redirect_uri": settings.oidc_redirect_uri,
            "scope": "openid email",
            "state": state,
        }
    )
    response = RedirectResponse(f"{endpoints['authorization_endpoint']}?{query}")
    # The cookie ties the callback to the browser that started the login (CSRF protection).
    response.set_cookie(
        OIDC_STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax", secure=request.url.scheme == "https"
    )
    return response


@router.get("/admin/oidc/callback", response_model=TokenResponse, include_in_schema=False)
def oidc_callback(request: Request, code: str, state: str) -> TokenResponse:
    settings = _settings(request)
    cookie = request.cookies.get(OIDC_STATE_COOKIE, "")
    if not secrets.compare_digest(cookie.encode(), state.encode()):
        raise HTTPException(400, "login state does not match this browser")
    try:
        auth.verify_token(_signing_key(settings), OIDC_STATE_TYPE, state)
    except auth.AuthError as exc:
        raise HTTPException(400, f"login state rejected: {exc}") from exc
    endpoints = _oidc_endpoints(settings)
    try:
        # The tokens come straight from the provider over TLS, so the user's identity is read from its
        # userinfo endpoint instead of validating an ID token signature locally.
        tokens = httpx.post(
            endpoints["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.oidc_redirect_uri,
                "client_id": settings.oidc_client_id,
                "client_secret": settings.oidc_client_secret,
            },
            timeout=10,
        )
        tokens.raise_for_status()
        info = httpx.get(
            endpoints["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {tokens.json()['access_token']}"},
            timeout=10,
        )
        info.raise_for_status()
        profile: dict[str, Any] = info.json()
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(502, "OIDC provider rejected the login") from exc
    email = str(profile.get("email", "")).lower()
    if not email or profile.get("email_verified") is not True or email not in settings.admin_emails:
        raise HTTPException(403, "this account is not an administrator")
    return _admin_session(settings, email)
