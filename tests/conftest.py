"""Shared test fixtures for Larpwing tests.

Sets up a FastAPI TestClient with a test config and env vars.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from app.config import AppConfig, ModelConfig, ServerConfig
from app.main import app


@pytest.fixture(autouse=True)
def set_env() -> Generator[None, None, None]:
    """Set required env vars before each test, then restore."""
    old = {
        "ROUTER_API_KEY": os.environ.get("ROUTER_API_KEY"),
        "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY"),
    }
    os.environ["ROUTER_API_KEY"] = "test-router-key"
    os.environ["DEEPSEEK_API_KEY"] = "sk-test-deepseek-key"
    yield
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture
def test_config() -> AppConfig:
    """Build a test AppConfig with known models."""
    return AppConfig(
        server=ServerConfig(
            api_key_env="ROUTER_API_KEY",
            default_timeout_seconds=600,
        ),
        models={
            "coding-cheap": ModelConfig(
                provider="deepseek",
                base_url="https://api.deepseek.com/v1",
                api_key_env="DEEPSEEK_API_KEY",
                model="deepseek-v4-flash",
                context_length=1000000,
                supports_tools=True,
                supports_streaming=True,
            ),
            "reasoning-pro": ModelConfig(
                provider="deepseek",
                base_url="https://api.deepseek.com/v1",
                api_key_env="DEEPSEEK_API_KEY",
                model="deepseek-v4-pro",
                context_length=1000000,
                supports_tools=True,
                supports_streaming=True,
            ),
        },
    )


@pytest.fixture
def client(test_config: AppConfig) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with test config injected into app.state."""
    with TestClient(app) as c:
        # Set config AFTER TestClient creation so lifespan doesn't overwrite it
        app.state.config = test_config
        yield c
