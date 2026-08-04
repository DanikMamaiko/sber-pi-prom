from fastapi.testclient import TestClient

from app.auth.models import AuthIdentity
from app.auth.session import InvalidSession, SessionManager
from app.core.config import Settings
from app.main import app


def test_successful_login_me_and_logout_cookie_flow():
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": "editor", "password": "editor123"},
        )
        assert login.status_code == 200
        body = login.json()
        assert body["username"] == "editor"
        assert body["roles"] == ["planning_editor"]
        assert "backlog:write" in body["permissions"]
        assert "pi_data:read" not in body["permissions"]
        cookie = login.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=lax" in cookie
        assert "max-age=3600" in cookie

        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json() == body

        logout = client.post("/api/auth/logout")
        assert logout.status_code == 204
        assert "max-age=0" in logout.headers["set-cookie"].lower()
        assert client.get("/api/auth/me").status_code == 401


def test_bad_credentials_return_401_without_session_cookie():
    response = TestClient(app).post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )

    assert response.status_code == 401
    assert "sberpi_session" not in response.cookies


def test_protected_api_returns_401_without_session_and_403_without_permission():
    with TestClient(app) as client:
        assert client.get("/api/pi-cycles").status_code == 401
        login = client.post(
            "/api/auth/login",
            json={"username": "pm", "password": "pm123"},
        )
        assert login.status_code == 200
        assert client.get("/api/backlog-board").status_code == 403
        assert client.get("/api/pi-cycles").status_code == 403


def test_health_remains_public():
    assert TestClient(app).get("/api/health").status_code == 200


def test_session_has_absolute_non_sliding_expiry():
    settings = Settings(
        session_secret="test-secret",
        session_ttl_minutes=60,
        _env_file=None,
    )
    manager = SessionManager(settings)
    token, created = manager.create(
        AuthIdentity(username="user", roles=("viewer",), provider="local"),
        now=1_000,
    )

    assert created.expires_at == 4_600
    assert manager.read(token, now=4_599).expires_at == 4_600
    assert manager.read(token, now=4_000).expires_at == 4_600
    try:
        manager.read(token, now=4_600)
    except InvalidSession:
        pass
    else:
        raise AssertionError("Session must expire exactly at the absolute deadline")


def test_tampered_session_is_rejected():
    settings = Settings(session_secret="test-secret", _env_file=None)
    manager = SessionManager(settings)
    token, _ = manager.create(
        AuthIdentity(username="user", roles=("viewer",), provider="local"),
        now=1_000,
    )

    try:
        manager.read(token + "tampered", now=1_001)
    except InvalidSession:
        pass
    else:
        raise AssertionError("Tampered session must be rejected")
