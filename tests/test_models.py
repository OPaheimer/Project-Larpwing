"""Tests for the /v1/models endpoint."""

from fastapi.testclient import TestClient


class TestModelsAuth:
    """Auth behaviour for GET /v1/models."""

    def test_requires_auth(self, client: TestClient):
        """Request without auth header returns 401."""
        resp = client.get("/v1/models", headers={})
        assert resp.status_code == 401

    def test_invalid_auth(self, client: TestClient):
        """Request with wrong token returns 401."""
        resp = client.get(
            "/v1/models",
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert resp.status_code == 401

    def test_missing_bearer_prefix(self, client: TestClient):
        """Bare token without Bearer prefix should also work."""
        resp = client.get(
            "/v1/models",
            headers={"Authorization": "test-router-key"},
        )
        assert resp.status_code == 200


class TestModelsResponse:
    """Response shape for GET /v1/models."""

    def test_returns_virtual_aliases(self, client: TestClient):
        """Returns the virtual model aliases, not real backend model names."""
        resp = client.get(
            "/v1/models",
            headers={"Authorization": "Bearer test-router-key"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["object"] == "list"

        model_ids = [m["id"] for m in body["data"]]
        assert "coding-cheap" in model_ids
        assert "reasoning-pro" in model_ids
        # Should NOT return real backend model names
        assert "deepseek-v4-flash" not in model_ids
        assert "deepseek-v4-pro" not in model_ids

    def test_model_entry_shape(self, client: TestClient):
        """Each model entry has the correct OpenAI-compatible fields."""
        resp = client.get(
            "/v1/models",
            headers={"Authorization": "Bearer test-router-key"},
        )
        body = resp.json()
        for entry in body["data"]:
            assert entry["object"] == "model"
            assert entry["owned_by"] == "larpwing"
            assert "id" in entry
            assert "created" in entry
