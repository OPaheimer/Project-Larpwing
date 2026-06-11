"""OpenAI-compatible error responses for Larpwing.

All error responses follow the OpenAI error JSON schema:

    {
      "error": {
        "message": "...",
        "type": "...",
        "param": "...",
        "code": "..."
      }
    }

Functions that are used in FastAPI Depends must call _http_error() to
raise HTTPExceptions. Functions used in endpoint handlers return JSONResponse.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException
from starlette.responses import JSONResponse


def _error_body(
    message: str,
    type: str = "invalid_request_error",
    param: Optional[str] = None,
    code: str = "error",
) -> Dict[str, Any]:
    return {
        "error": {
            "message": message,
            "type": type,
            "param": param,
            "code": code,
        }
    }


def _http_error(status: int, body: dict) -> HTTPException:
    """Raiseable HTTPException — use in FastAPI Depends only."""
    return HTTPException(status_code=status, detail=body)


def _json_error(status: int, body: dict) -> JSONResponse:
    """Returnable JSONResponse — use in endpoint handlers."""
    return JSONResponse(status_code=status, content=body)


# ── For Depends (raises HTTPException) ────────────────────────────


def missing_auth() -> HTTPException:
    return _http_error(401, _error_body(
        message="Missing Authorization header",
        code="missing_auth",
    ))


def invalid_auth() -> HTTPException:
    return _http_error(401, _error_body(
        message="Invalid API key",
        code="invalid_auth",
    ))


# ── For endpoint handlers (returns JSONResponse) ──────────────────


def missing_field(field_name: str) -> JSONResponse:
    return _json_error(400, _error_body(
        message=f"Missing required field: '{field_name}'",
        param=field_name,
        code="missing_field",
    ))


def unknown_model(alias: str) -> JSONResponse:
    return _json_error(404, _error_body(
        message=f"Unknown model alias: {alias}",
        param="model",
        code="model_not_found",
    ))


def missing_backend_key(env_var: str) -> JSONResponse:
    return _json_error(500, _error_body(
        message=f"Backend API key not configured: {env_var}",
        type="server_error",
        code="backend_key_missing",
    ))


def backend_error(status_code: int, detail: str) -> JSONResponse:
    return _json_error(status_code, _error_body(
        message=f"Backend error: {detail}",
        type="upstream_error",
        code="backend_error",
    ))


def backend_timeout() -> JSONResponse:
    return _json_error(504, _error_body(
        message="Backend request timed out",
        type="server_error",
        code="backend_timeout",
    ))


def invalid_json() -> JSONResponse:
    return _json_error(400, _error_body(
        message="Invalid JSON in request body",
        code="invalid_json",
    ))
