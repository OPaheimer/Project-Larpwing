"""Larpwing — FastAPI application entry point.

Usage:
    uvicorn app.main:app --host 127.0.0.1 --port 7321 --reload
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from app.config import load_config
from app.logging import log
from app.router import router

# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: load config on startup, validate API key presence."""
    config_path = _project_root / "config" / "models.yaml"
    try:
        config = load_config(config_path)
        app.state.config = config
        log.info("config loaded", extra={"path": str(config_path), "models": list(config.models.keys())})
    except FileNotFoundError as exc:
        log.error("config file not found", extra={"error": str(exc)})
        raise

    # Warn if router API key env var is not set
    router_key_env = config.server.api_key_env
    if not os.environ.get(router_key_env):
        log.warning("router API key env var not set", extra={"env_var": router_key_env})

    yield


app = FastAPI(
    title="Larpwing",
    version="0.1.0",
    description="OpenAI-compatible model alias router for Hermes Agent",
    lifespan=lifespan,
)

app.include_router(router)
