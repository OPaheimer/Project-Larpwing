"""Tests for alias routing in POST /v1/chat/completions.

Uses httpx mocking via monkeypatching so tests do not call real providers.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient


def _fake_response(status_code: int, json_data: dict) -> httpx.Response:
    return httpx.Response(status_code=status_code, json=json_data)


@pytest.mark.asyncio
async def test_alias_replaces_model_name(client: TestClient):
    """The alias should be replaced by the real backend model name in the forwarded request."""
    captured = {}

    async def fake_post(*args, **kwargs):
        # args[0] is the AsyncClient instance (self), url is in kwargs
        captured["url"] = kwargs.get("url", args[1] if len(args) > 1 else "")
        captured["json"] = kwargs.get("json")
        captured["headers"] = kwargs.get("headers")
        return _fake_response(
            200,
            {
                "id": "cmpl-test",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello"}}],
            },
        )

    with patch("app.router.httpx.AsyncClient.post", new=fake_post):
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-router-key", "Content-Type": "application/json"},
            json={"model": "coding-cheap", "messages": [{"role": "user", "content": "Hi"}], "stream": False},
        )

    assert resp.status_code == 200
    assert captured["json"]["model"] == "deepseek-v4-flash"
    assert "api.deepseek.com" in captured["url"]


@pytest.mark.asyncio
async def test_unknown_model_returns_error(client: TestClient):
    resp = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-router-key", "Content-Type": "application/json"},
        json={"model": "non-existent-model", "messages": [{"role": "user", "content": "Hi"}]},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "model_not_found"
    assert "non-existent-model" in body["error"]["message"]
    assert body["error"]["param"] == "model"


@pytest.mark.asyncio
async def test_missing_model_field(client: TestClient):
    resp = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-router-key", "Content-Type": "application/json"},
        json={"messages": [{"role": "user", "content": "Hi"}]},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "missing_field"
    assert "model" in body["error"]["message"]


@pytest.mark.asyncio
async def test_backend_api_key_missing(client: TestClient, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    resp = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-router-key", "Content-Type": "application/json"},
        json={"model": "coding-cheap", "messages": [{"role": "user", "content": "Hi"}]},
    )
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"]["code"] == "backend_key_missing"
    assert "DEEPSEEK_API_KEY" in body["error"]["message"]


@pytest.mark.asyncio
async def test_invalid_json_body(client: TestClient):
    resp = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-router-key", "Content-Type": "application/json"},
        content=b"not json at all",
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "invalid_json"


@pytest.mark.asyncio
async def test_non_streaming_forward_response(client: TestClient):
    backend_response = {
        "id": "cmpl-abc123",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "deepseek-v4-flash",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello! How can I help you today?"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }

    async def fake_post(*args, **kwargs):
        return _fake_response(200, backend_response)

    with patch("app.router.httpx.AsyncClient.post", new=fake_post):
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-router-key", "Content-Type": "application/json"},
            json={"model": "coding-cheap", "messages": [{"role": "user", "content": "Hi"}], "stream": False},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "cmpl-abc123"
    assert body["choices"][0]["message"]["content"] == "Hello! How can I help you today?"


@pytest.mark.asyncio
async def test_reasoning_pro_uses_correct_model(client: TestClient):
    captured = {}

    async def fake_post(*args, **kwargs):
        captured["json"] = kwargs.get("json")
        return _fake_response(
            200,
            {"id": "cmpl-reasoning", "object": "chat.completion", "choices": [{"index": 0, "message": {"role": "assistant", "content": "Reasoned."}}]},
        )

    with patch("app.router.httpx.AsyncClient.post", new=fake_post):
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-router-key", "Content-Type": "application/json"},
            json={"model": "reasoning-pro", "messages": [{"role": "user", "content": "Think step by step"}], "stream": False},
        )

    assert resp.status_code == 200
    assert captured["json"]["model"] == "deepseek-v4-pro"


@pytest.mark.asyncio
async def test_backend_timeout(client: TestClient):
    """Backend timeout returns 504 with OpenAI-style error."""

    async def fake_post(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    with patch("app.router.httpx.AsyncClient.post", new=fake_post):
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-router-key", "Content-Type": "application/json"},
            json={"model": "coding-cheap", "messages": [{"role": "user", "content": "Hi"}]},
        )

    assert resp.status_code == 504
    body = resp.json()
    assert body["error"]["code"] == "backend_timeout"


@pytest.mark.asyncio
async def test_backend_http_error(client: TestClient):
    async def fake_post(*args, **kwargs):
        return _fake_response(429, {"error": {"message": "Rate limited"}})

    with patch("app.router.httpx.AsyncClient.post", new=fake_post):
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-router-key", "Content-Type": "application/json"},
            json={"model": "coding-cheap", "messages": [{"role": "user", "content": "Hi"}]},
        )

    assert resp.status_code == 429
    body = resp.json()
    assert body["error"]["code"] == "backend_error"
