from fastapi.testclient import TestClient

from dpdpkit.server.app import create_app


def test_healthz() -> None:
    response = TestClient(create_app()).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
