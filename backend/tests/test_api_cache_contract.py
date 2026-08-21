from fastapi.testclient import TestClient

from app.main import app


def test_api_responses_are_not_browser_cacheable():
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"
