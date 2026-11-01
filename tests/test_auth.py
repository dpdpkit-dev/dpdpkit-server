import pytest
from fastapi.testclient import TestClient

from dpdpkit.server import auth
from dpdpkit.server.app import create_app
from dpdpkit.server.settings import Settings

KEY, KEY_HASH = auth.generate_api_key()
PASSWORD_HASH = auth.hash_password("correct horse")


def client(**overrides: object) -> TestClient:
    values: dict[str, object] = {
        "signing_key": "s3cret",
        "api_key_hashes": (KEY_HASH,),
        "admin_password_hash": PASSWORD_HASH,
    }
    return TestClient(create_app(Settings(**{**values, **overrides})))  # type: ignore[arg-type]


def bearer(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


def test_api_key_is_stored_hashed() -> None:
    assert KEY not in KEY_HASH
    assert auth.verify_api_key(KEY, [KEY_HASH])
    assert not auth.verify_api_key(KEY + "x", [KEY_HASH])
    assert not auth.verify_api_key("not-a-key", [KEY_HASH])
    assert not auth.verify_api_key(KEY, [])


def test_password_hash() -> None:
    assert auth.verify_password("correct horse", PASSWORD_HASH)
    assert not auth.verify_password("wrong", PASSWORD_HASH)
    assert not auth.verify_password("x", "garbage")


def test_token_round_trip_and_tamper() -> None:
    token = auth.issue_token("k", auth.USER_TOKEN, "u1", ttl=60, scope="consent")
    claims = auth.verify_token("k", auth.USER_TOKEN, token)
    assert (claims.subject, claims.scope) == ("u1", "consent")
    with pytest.raises(auth.AuthError):
        auth.verify_token("other", auth.USER_TOKEN, token)
    with pytest.raises(auth.AuthError):
        auth.verify_token("k", auth.ADMIN_TOKEN, token)
    with pytest.raises(auth.AuthError):
        auth.verify_token("k", auth.USER_TOKEN, "a" + token)
    with pytest.raises(auth.AuthError):
        auth.verify_token("k", auth.USER_TOKEN, "nonsense")


def test_token_expires() -> None:
    token = auth.issue_token("k", auth.USER_TOKEN, "u1", ttl=60, now=1000)
    assert auth.verify_token("k", auth.USER_TOKEN, token, now=1059).subject == "u1"
    with pytest.raises(auth.AuthError, match="expired"):
        auth.verify_token("k", auth.USER_TOKEN, token, now=1060)


def test_mint_user_token_needs_api_key() -> None:
    http = client()
    assert http.post("/v1/tokens", json={"subject": "u1"}).status_code == 401
    assert http.post("/v1/tokens", json={"subject": "u1"}, headers=bearer("dpk_bad")).status_code == 401
    response = http.post("/v1/tokens", json={"subject": "u1", "scope": "consent"}, headers=bearer(KEY))
    assert response.status_code == 200
    claims = auth.verify_token("s3cret", auth.USER_TOKEN, response.json()["token"])
    assert (claims.subject, claims.scope) == ("u1", "consent")


def test_tokens_need_signing_key() -> None:
    response = client(signing_key=None).post("/v1/tokens", json={"subject": "u1"}, headers=bearer(KEY))
    assert response.status_code == 503


def test_admin_login_and_session() -> None:
    http = client()
    assert http.post("/admin/login", json={"password": "nope"}).status_code == 401
    login = http.post("/admin/login", json={"password": "correct horse"})
    assert login.status_code == 200
    token = login.json()["token"]
    assert http.get("/admin/session", headers=bearer(token)).json()["subject"] == "admin"
    assert http.get("/admin/session").status_code == 401
    # A user token must not open an admin session.
    user_token = auth.issue_token("s3cret", auth.USER_TOKEN, "u1", ttl=60)
    assert http.get("/admin/session", headers=bearer(user_token)).status_code == 401


def test_admin_login_disabled_without_password_hash() -> None:
    assert client(admin_password_hash=None).post("/admin/login", json={"password": "x"}).status_code == 404


def test_oidc_not_configured() -> None:
    assert client().get("/admin/oidc/login", follow_redirects=False).status_code == 404


def test_oidc_callback_rejects_foreign_state() -> None:
    state = auth.issue_token("s3cret", "oidc-state", "n", ttl=60)
    response = client().get("/admin/oidc/callback", params={"code": "c", "state": state})
    assert response.status_code == 400
