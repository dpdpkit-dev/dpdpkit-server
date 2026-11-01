"""Builds the dpdpkit engine from the server settings."""

from __future__ import annotations

from fastapi import Request

from dpdpkit.errors import ConfigError
from dpdpkit.fastapi import DPDPKit
from dpdpkit.server.settings import Settings


def _no_principal(request: Request) -> None:
    # The server authenticates callers itself (see dpdpkit.server.auth), not through the engine's resolver.
    return None


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
    )
