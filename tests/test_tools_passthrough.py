"""Tests for tools and tool_choice passthrough.

Verifies that the tools, tool_choice, and other OpenAI-compatible
fields are preserved when forwarding requests to the backend.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient


def _fake_ok_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "cmpl-tools",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_abc",
                                "type": "function",
                                "function": {
                                    "name": "get_weather",
                                    "arguments": '{"location": "Singapore"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        },
    )


@pytest.mark.asyncio
async def test_tools_passthrough(client: TestClient):
    """The 'tools' field is forwarded unchanged to the backend."""
    captured = {}

    async def fake_post(*args, **kwargs):
        captured["json"] = kwargs.get("json")
        return _fake_ok_response()

    tools_payload = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the weather for a location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name",
                        }
                    },
                    "required": ["location"],
                },
            },
        }
    ]

    with patch("app.router.httpx.AsyncClient.post", new=fake_post):
        resp = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer test-router-key",
                "Content-Type": "application/json",
            },
            json={
                "model": "coding-cheap",
                "messages": [{"role": "user", "content": "Weather in Singapore?"}],
                "tools": tools_payload,
                "tool_choice": "auto",
                "stream": False,
            },
        )

    assert resp.status_code == 200
    assert captured["json"]["tools"] == tools_payload
    assert captured["json"]["tool_choice"] == "auto"
    # Model alias should still be resolved
    assert captured["json"]["model"] == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_tool_choice_none(client: TestClient):
    """tool_choice: 'none' is forwarded unchanged."""
    captured = {}

    async def fake_post(*args, **kwargs):
        captured["json"] = kwargs.get("json")
        return _fake_ok_response()

    with patch("app.router.httpx.AsyncClient.post", new=fake_post):
        resp = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer test-router-key",
                "Content-Type": "application/json",
            },
            json={
                "model": "coding-cheap",
                "messages": [{"role": "user", "content": "Hi"}],
                "tool_choice": "none",
                "stream": False,
            },
        )

    assert resp.status_code == 200
    assert captured["json"]["tool_choice"] == "none"


@pytest.mark.asyncio
async def test_extra_fields_preserved(client: TestClient):
    """Unknown/extra OpenAI-compatible fields are forwarded unchanged."""
    captured = {}

    async def fake_post(*args, **kwargs):
        captured["json"] = kwargs.get("json")
        return httpx.Response(
            200,
            json={
                "id": "cmpl-extra",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}}],
            },
        )

    with patch("app.router.httpx.AsyncClient.post", new=fake_post):
        resp = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer test-router-key",
                "Content-Type": "application/json",
            },
            json={
                "model": "coding-cheap",
                "messages": [{"role": "user", "content": "Hi"}],
                "temperature": 0.7,
                "max_tokens": 500,
                "top_p": 0.9,
                "presence_penalty": 0.1,
                "frequency_penalty": 0.1,
                "stop": ["\n"],
                "response_format": {"type": "text"},
                "stream": False,
            },
        )

    assert resp.status_code == 200
    assert captured["json"]["temperature"] == 0.7
    assert captured["json"]["max_tokens"] == 500
    assert captured["json"]["top_p"] == 0.9
    assert captured["json"]["presence_penalty"] == 0.1
    assert captured["json"]["frequency_penalty"] == 0.1
    assert captured["json"]["stop"] == ["\n"]
    assert captured["json"]["response_format"] == {"type": "text"}
