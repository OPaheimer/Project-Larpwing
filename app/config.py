"""Configuration loader for Larpwing.

Loads model alias definitions and server settings from config/models.yaml.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import yaml


@dataclass
class ModelConfig:
    """Configuration for a single backend model alias."""

    provider: str
    base_url: str
    api_key_env: str
    model: str
    context_length: int = 4096
    supports_tools: bool = False
    supports_streaming: bool = True
    api_url_env: str = ""

    @property
    def resolved_base_url(self) -> str:
        """Return the base URL, with optional override from api_url_env env var."""
        if self.api_url_env:
            env_url = os.environ.get(self.api_url_env)
            if env_url:
                return env_url.rstrip("/")
        return self.base_url.rstrip("/")

    @property
    def resolved_api_key(self) -> Optional[str]:
        """Return the API key from the configured environment variable."""
        return os.environ.get(self.api_key_env)


@dataclass
class ServerConfig:
    """Server-level configuration."""

    api_key_env: str = "ROUTER_API_KEY"
    default_timeout_seconds: int = 600


@dataclass
class AppConfig:
    """Complete application configuration."""

    server: ServerConfig = field(default_factory=ServerConfig)
    models: Dict[str, ModelConfig] = field(default_factory=dict)

    def get_model(self, alias: str) -> Optional[ModelConfig]:
        """Look up a model config by its virtual alias name."""
        return self.models.get(alias)

    def router_api_key(self) -> str:
        """Read the router API key from the configured environment variable."""
        return os.environ.get(self.server.api_key_env, "")


def load_config(config_path: Path) -> AppConfig:
    """Load and parse config/models.yaml into an AppConfig object.

    Args:
        config_path: Path to models.yaml.

    Returns:
        AppConfig with parsed server and model settings.

    Raises:
        FileNotFoundError: If models.yaml cannot be found.
        yaml.YAMLError: If the YAML is malformed.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text())

    # Server section
    server_raw = raw.get("server", {})
    server = ServerConfig(
        api_key_env=server_raw.get("api_key_env", "ROUTER_API_KEY"),
        default_timeout_seconds=server_raw.get("default_timeout_seconds", 600),
    )

    # Models section
    models_raw = raw.get("models", {})
    models: Dict[str, ModelConfig] = {}
    for alias, cfg in models_raw.items():
        models[alias] = ModelConfig(
            provider=cfg.get("provider", ""),
            base_url=cfg.get("base_url", ""),
            api_key_env=cfg.get("api_key_env", ""),
            api_url_env=cfg.get("api_url_env", ""),
            model=cfg.get("model", ""),
            context_length=cfg.get("context_length", 4096),
            supports_tools=cfg.get("supports_tools", False),
            supports_streaming=cfg.get("supports_streaming", True),
        )

    return AppConfig(server=server, models=models)
