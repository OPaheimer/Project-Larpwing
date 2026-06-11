"""Tests for the /health endpoint."""

from fastapi.testclient import TestClient


class TestHealth:
    """GET /health should work without authentication."""

    def test_health_returns_ok(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"status": "ok", "service": "larpwing"}

    def test_health_no_auth_required(self, client: TestClient):
        """Health endpoint does not need an Authorization header."""
        resp = client.get("/health", headers={})
        assert resp.status_code == 200

    def test_health_returns_json(self, client: TestClient):
        resp = client.get("/health")
        assert resp.headers["content-type"].startswith("application/json")
