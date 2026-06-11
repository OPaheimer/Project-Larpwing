"""FastAPI router for Larpwing endpoints.

Endpoints:
  GET  /health              — health check, no auth required
  GET  /v1/models            — list virtual model aliases, auth required
  POST /v1/chat/completions  — forward to backend, auth required
"""

from __future__ import annotations

import json
import time
import uuid
from typing import AsyncGenerator, Optional

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.status import HTTP_200_OK

from app.config import AppConfig, ModelConfig
from app.errors import (
    backend_error,
    backend_timeout,
    invalid_auth,
    invalid_json,
    missing_auth,
    missing_backend_key,
    missing_field,
    unknown_model,
)
from app.logging import log

router = APIRouter()

# ── State ──────────────────────────────────────────────────────────
# Config is injected into request.app.state.config by main.py lifespan.


def _get_config(request: Request) -> AppConfig:
    return request.app.state.config


# ── Auth dependency (MUST raise HTTPException for Depends) ─────────


async def require_auth(request: Request) -> None:
    """Dependency: validate Bearer token against the configured router API key."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        raise missing_auth()

    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
    else:
        token = auth_header

    config = _get_config(request)
    expected = config.router_api_key()
    if not expected or token != expected:
        raise invalid_auth()


# ── Helpers ────────────────────────────────────────────────────────


def _build_model_list(config: AppConfig) -> list[dict]:
    """Build the OpenAI-compatible models list from virtual aliases."""
    return [
        {"id": alias, "object": "model", "created": 0, "owned_by": "larpwing"}
        for alias in config.models
    ]


def _validate_body(
    request: Request, body: dict
) -> tuple[Optional[str], Optional[ModelConfig], Optional[JSONResponse]]:
    """Validate chat completion body. Returns (alias, cfg, error)."""
    model_alias = body.get("model")
    if not model_alias:
        return None, None, missing_field("model")
    cfg = _get_config(request).get_model(model_alias)
    if cfg is None:
        return None, None, unknown_model(model_alias)
    return model_alias, cfg, None


def _build_headers(cfg: ModelConfig) -> tuple[Optional[dict], Optional[JSONResponse]]:
    """Build backend request headers. Returns (headers, error)."""
    api_key = cfg.resolved_api_key
    if not api_key:
        return None, missing_backend_key(cfg.api_key_env)
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }, None


# ── Endpoint: GET /health ─────────────────────────────────────────-─


@router.get("/health")
async def health():
    return {"status": "ok", "service": "larpwing"}


# ── Endpoint: GET /v1/models ───────────────────────────────────────


@router.get("/v1/models", dependencies=[Depends(require_auth)])
async def list_models(request: Request):
    config = _get_config(request)
    return {"object": "list", "data": _build_model_list(config)}


# ── Endpoint: POST /v1/chat/completions ───────────────────────────-─


@router.post("/v1/chat/completions", dependencies=[Depends(require_auth)])
async def chat_completions(request: Request):
    """Forward a chat completion request to the backend provider.

    Supports both streaming and non-streaming modes.
    All OpenAI-compatible fields are passed through unchanged.
    """
    request_id = request.headers.get("X-Request-Id", uuid.uuid4().hex[:12])

    # Parse body
    try:
        body = await request.json()
    except ValueError:
        return invalid_json()

    model_alias, cfg, err = _validate_body(request, body)
    if err:
        return err

    is_stream = body.get("stream", False)
    backend_body = {**body, "model": cfg.model}

    headers, err = _build_headers(cfg)
    if err:
        return err

    url = f"{cfg.resolved_base_url}/chat/completions"
    timeout = _get_config(request).server.default_timeout_seconds

    log.info(
        "forwarding request | alias=%s provider=%s backend_model=%s stream=%s",
        model_alias, cfg.provider, cfg.model, is_stream,
    )

    start = time.monotonic()

    if is_stream:
        return await _handle_streaming(
            url, backend_body, headers, request_id, start, timeout
        )
    else:
        return await _handle_non_streaming(
            url, backend_body, headers, request_id, start, timeout
        )


# ── Non-streaming handler ─────────────────────────────────────────-─


async def _handle_non_streaming(
    url: str,
    body: dict,
    headers: dict,
    request_id: str,
    start: float,
    timeout: int,
) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            resp = await client.post(url, json=body, headers=headers)
    except httpx.TimeoutException:
        log.warning("backend timeout | request_id=%s", request_id)
        return backend_timeout()
    except httpx.RequestError as exc:
        log.error(
            "backend request failed | request_id=%s error=%s", request_id, exc,
        )
        return backend_error(502, str(exc))

    elapsed = time.monotonic() - start
    log.info(
        "backend response | status=%s elapsed=%.3fs", resp.status_code, elapsed,
    )

    if resp.is_error:
        try:
            detail = resp.json()
        except ValueError:
            detail = resp.text[:500]
        return backend_error(resp.status_code, str(detail))

    return JSONResponse(content=resp.json(), status_code=HTTP_200_OK)


# ── Streaming handler ─────────────────────────────────────────────-─


async def _handle_streaming(
    url: str,
    body: dict,
    headers: dict,
    request_id: str,
    start: float,
    timeout: int,
) -> StreamingResponse:
    """Handle a streaming chat completion by relaying SSE chunks.

    The httpx client is created INSIDE the relay generator so
    it stays alive for the entire duration of the streamed response.
    """

    async def _relay() -> AsyncGenerator[bytes, None]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
                req = client.build_request("POST", url, json=body, headers=headers)
                resp = await client.send(req, stream=True)

                if resp.is_error:
                    try:
                        body_text = (await resp.aread()).decode()
                    except Exception:
                        body_text = "unknown error"
                    elapsed = time.monotonic() - start
                    log.info(
                        "backend streaming error | status=%s elapsed=%.3fs",
                        resp.status_code, elapsed,
                    )
                    error_payload = {
                        "error": {
                            "message": f"Backend error: {body_text}",
                            "type": "upstream_error",
                            "code": "backend_error",
                        }
                    }
                    yield f"data: {json.dumps(error_payload)}\n\n".encode()
                    return

                elapsed = time.monotonic() - start
                log.info(
                    "backend stream connected | status=%s elapsed=%.3fs",
                    resp.status_code, elapsed,
                )

                async for chunk in resp.aiter_bytes():
                    yield chunk
        except Exception as exc:
            log.error(
                "stream relay error | request_id=%s error=%s", request_id, exc,
            )

    return StreamingResponse(
        _relay(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
