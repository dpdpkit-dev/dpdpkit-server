from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dpdpkit.server import auth
from dpdpkit.server.app import create_app
from dpdpkit.server.engine import CONFORMANCE_PRINCIPAL_HEADER, CONFORMANCE_ROLE_HEADER
from dpdpkit.server.settings import Settings

HERE = Path(__file__).parent / "conformance"
BASE_ENV = {
    "DPDPKIT_CONFIG": str(HERE / "dpdpkit.yaml"),
    "DPDPKIT_DATABASE_URL": "sqlite://",
    "DPDPKIT_MIGRATE_ON_STARTUP": "1",
    "DPDPKIT_SIGNING_KEY": "test-signing-key",
}


def _app(conformance: bool) -> TestClient:
    env = {**BASE_ENV, **({"DPDPKIT_CONFORMANCE": "1"} if conformance else {})}
    return TestClient(create_app(Settings.load(env)))


def test_conformance_suite_passes_against_server_app() -> None:
    pytest.importorskip("dpdpkit_conformance")
    env = {**os.environ, **BASE_ENV, "DPDPKIT_CONFORMANCE": "1", "DPDPKIT_ASGI_APP": "app:app"}
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, "-m", "dpdpkit_conformance", "-q", "-p", "no:warnings"],
        cwd=HERE,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-2000:]


def test_test_headers_are_ignored_outside_conformance_mode() -> None:
    with _app(conformance=False) as client:
        headers = {CONFORMANCE_PRINCIPAL_HEADER: "u1", CONFORMANCE_ROLE_HEADER: "admin"}
        assert client.get("/dpdp/consents/me", headers=headers).status_code == 401
        assert client.get("/dpdp/admin/consent/stats", headers=headers).status_code == 401


def test_user_token_identifies_the_data_principal() -> None:
    token = auth.issue_token("test-signing-key", auth.USER_TOKEN, "u_42", ttl=60)
    admin_token = auth.issue_token("test-signing-key", auth.ADMIN_TOKEN, "admin", ttl=60)
    with _app(conformance=False) as client:
        assert client.get("/dpdp/consents/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        # an admin session is not an end user, and a user token is not an admin
        assert client.get("/dpdp/consents/me", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 401
        assert client.get("/dpdp/admin/consent/stats", headers={"Authorization": f"Bearer {token}"}).status_code == 403
        assert (
            client.get("/dpdp/admin/consent/stats", headers={"Authorization": f"Bearer {admin_token}"}).status_code
            == 200
        )
