"""Tests for streaming in POST /v1/chat/completions.

Verifies that streaming requests are forwarded with stream=true and
that SSE chunks are relayed correctly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import json
import pytest
from fastapi.testclient import TestClient


class AsyncStreamMock:
    """Mimics httpx streaming response for SSE relay testing."""

    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


def _make_streaming_response(chunks: list[bytes]):
    """Build a fake httpx.Response that supports aiter_bytes."""
    resp = httpx.Response(status_code=200)
    resp.aiter_bytes = AsyncStreamMock(chunks).aiter_bytes
    return resp


@pytest.mark.asyncio
async def test_streaming_forwards_stream_true(client: TestClient):
    """When stream=true, the forwarded request should also have stream=true."""
    captured = {}

    async def fake_send(*args, **kwargs):
        # httpx.AsyncClient.send(request=req, stream=True)
        request = kwargs.get("request", args[1] if len(args) > 1 else None)
        import json
        captured["json"] = json.loads(request.content.decode())
        return _make_streaming_response(
            [b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n', b"data: [DONE]\n\n"]
        )

    with patch("app.router.httpx.AsyncClient.send", new=fake_send):
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-router-key", "Content-Type": "application/json"},
            json={"model": "coding-cheap", "messages": [{"role": "user", "content": "Hi"}], "stream": True},
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert captured["json"]["stream"] is True


@pytest.mark.asyncio
async def test_streaming_relays_sse_chunks(client: TestClient):
    """SSE chunks from the backend are relayed unchanged."""
    sse_chunks = [
        b'data: {"choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}\n\n',
        b'data: {"choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}\n\n',
        b'data: {"choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}\n\n',
        b'data: [DONE]\n\n',
    ]

    async def fake_send(*args, **kwargs):
        return _make_streaming_response(sse_chunks)

    with patch("app.router.httpx.AsyncClient.send", new=fake_send):
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-router-key", "Content-Type": "application/json"},
            json={"model": "coding-cheap", "messages": [{"role": "user", "content": "Hi"}], "stream": True},
        )

    assert resp.status_code == 200
    content = b"".join(resp.iter_bytes())
    assert b'data: {"choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}' in content
    assert b'data: {"choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}' in content
    assert b"data: [DONE]" in content


@pytest.mark.asyncio
async def test_streaming_content_type(client: TestClient):
    async def fake_send(*args, **kwargs):
        return _make_streaming_response([b"data: [DONE]\n\n"])

    with patch("app.router.httpx.AsyncClient.send", new=fake_send):
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-router-key", "Content-Type": "application/json"},
            json={"model": "coding-cheap", "messages": [{"role": "user", "content": "Hi"}], "stream": True},
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers.get("cache-control") == "no-cache"


@pytest.mark.asyncio
async def test_streaming_error_relayed(client: TestClient):
    """Backend streaming error returns OpenAI-style error with correct status."""

    async def fake_send(*args, **kwargs):
        # Return an error response (no aiter_bytes needed — error path uses aread)
        return httpx.Response(status_code=429, content=b'{"error": {"message": "Rate limited"}}')

    with patch("app.router.httpx.AsyncClient.send", new=fake_send):
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-router-key", "Content-Type": "application/json"},
            json={"model": "coding-cheap", "messages": [{"role": "user", "content": "Hi"}], "stream": True},
        )

    # Streaming error responses come as 200 with error in SSE body
    assert resp.status_code == 200
    # Parse the SSE data line
    text = resp.text
    assert text.startswith("data: ")
    body = json.loads(text[len("data: "):].strip())
    assert body["error"]["code"] == "backend_error"
