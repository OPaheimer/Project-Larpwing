#!/usr/bin/env python3
"""Larpwing setup wizard.

Generates a router API key and helps you add custom provider configs.

Usage:
    python configure.py          # interactive mode
    python configure.py --check  # non-interactive: report what's configured
"""

from __future__ import annotations

import os
import re
import secrets
import string
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ENV_PATH = HERE / ".env"
YAML_PATH = HERE / "config" / "models.yaml"


# ── helpers ─────────────────────────────────────────────────────────


def _generate_key() -> str:
    """Generate an OpenAI-format API key: sk-<48 random chars>."""
    chars = string.ascii_letters + string.digits
    return "sk-" + "".join(secrets.choice(chars) for _ in range(48))


def _load_env() -> dict[str, str]:
    """Parse .env into a dict."""
    if not ENV_PATH.exists():
        return {}
    env: dict[str, str] = {}
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip()
    return env


def _write_env(updates: dict[str, str], comments: dict[str, str]) -> None:
    """Update .env in-place, preserving existing lines and comments.

    Only touches keys in ``updates`` — all other content is preserved.
    Adds new keys at the end with their comment header.
    """
    if not ENV_PATH.exists():
        lines: list[str] = []
        for key in updates:
            c = comments.get(key)
            if c:
                lines.append(f"# {c}")
            lines.append(f"{key}={updates[key]}")
        lines.append("")
        ENV_PATH.write_text("\n".join(lines))
        return

    existing = ENV_PATH.read_text().splitlines()
    new_lines: list[str] = []
    updated_keys: set[str] = set()

    for line in existing:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    for key in updates:
        if key not in updated_keys:
            c = comments.get(key)
            if c:
                new_lines.append(f"# {c}")
            new_lines.append(f"{key}={updates[key]}")

    new_lines.append("")
    ENV_PATH.write_text("\n".join(new_lines))


def _write_models(added_models: list[dict[str, str]]) -> None:
    """Append model alias entries to config/models.yaml preserving existing content."""
    if not YAML_PATH.exists():
        print("  ⚠  config/models.yaml not found. Skipping.")
        return

    lines = YAML_PATH.read_text().splitlines(keepends=True)
    # Build the YAML block to insert
    block_lines: list[str] = []
    for m in added_models:
        block_lines.append(f"  {m['alias']}:\n")
        block_lines.append(f"    provider: {m['provider']}\n")
        block_lines.append(f"    base_url: {m['base_url']}\n")
        block_lines.append(f"    api_key_env: {m['key_env']}\n")
        block_lines.append(f"    api_url_env: {m['url_env']}\n")
        block_lines.append(f"    model: {m['model']}\n")
        block_lines.append(f"    context_length: 128000\n")
        block_lines.append(f"    supports_tools: true\n")
        block_lines.append(f"    supports_streaming: true\n")

    # Find where to insert
    inserted = False
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n").rstrip("\r")
        # Replace empty models dict
        if stripped.strip() == "models: {}":
            lines[i] = "models:\n"
            lines = lines[:i+1] + block_lines + lines[i+1:]
            inserted = True
            break

    if not inserted:
        # Append after last model entry or at end of file
        lines.extend(block_lines)

    YAML_PATH.write_text("".join(lines))


# ── prompts ─────────────────────────────────────────────────────────


def _ask(prompt: str, default: str = "") -> str:
    if default:
        val = input(f"{prompt} [{default}]: ").strip()
        return val if val else default
    return input(f"{prompt}: ").strip()


def _confirm(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    val = input(f"{prompt} [{hint}]: ").strip().lower()
    if not val:
        return default
    return val.startswith("y")


# ── interactive wizard ──────────────────────────────────────────────


def run_interactive() -> None:
    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║        Larpwing Setup Wizard             ║")
    print("  ╚══════════════════════════════════════════╝")
    print()

    env = _load_env()
    comments: dict[str, str] = {}
    added_models: list[dict[str, str]] = []

    # ── Step 1: Router API key ──────────────────────────────────────

    print("── Step 1: Router API Key ──────────────────────")
    print("  This key authenticates clients to Larpwing.")
    print()

    existing_key = env.get("ROUTER_API_KEY", "")
    if existing_key and existing_key.startswith("sk-"):
        print(f"  ✓ Router key already set (sk-...{existing_key[-8:]})")
        if not _confirm("  Regenerate?", default=False):
            comments["ROUTER_API_KEY"] = "Larpwing router API key"
        else:
            existing_key = ""
            print()

    if not existing_key or not existing_key.startswith("sk-"):
        print("  No router API key found." if not existing_key else
              f"  Current value doesn't look like an OpenAI-format key ({existing_key[:12]}...)")
        new_key = _generate_key()
        print(f"  Generated: sk-...{new_key[-12:]}")
        env["ROUTER_API_KEY"] = new_key
        comments["ROUTER_API_KEY"] = "Larpwing router API key"
        print()

    # ── Step 2: Custom providers ────────────────────────────────────

    print("── Step 2: Add Your Providers ───────────────────")
    print("  Add one model alias at a time. Each alias is a")
    print("  short name you'll put in the 'model' field that")
    print("  Larpwing translates to a real backend model.")
    print()

    while True:
        if not _confirm("  Add a provider?", default=len(added_models) == 0):
            break

        print()

        alias = _ask("     Alias name (e.g. fast-chat, coding-pro)")
        if not alias:
            print("     Alias name is required. Try again.")
            continue

        provider_name = _ask("     Provider label (e.g. openai, deepseek, local)", default=alias)
        base_url = _ask("     Base URL (e.g. https://api.openai.com/v1)")
        if not base_url:
            print("     Base URL is required. Try again.")
            continue

        api_key = _ask("     API key")
        if not api_key:
            print("     API key is required. Try again.")
            continue

        model_name = _ask("     Model name (e.g. gpt-4o-mini, deepseek-v4-flash, gemma)")
        if not model_name:
            print("     Model name is required. Try again.")
            continue

        # Build env var names from alias
        suffix = re.sub(r"[^A-Z0-9]", "_", alias.upper().strip())
        key_env = f"{suffix}_API_KEY"
        url_env = f"{suffix}_API_URL"

        env[key_env] = api_key
        comments[key_env] = f"API key for {provider_name} ({alias})"
        comments[url_env] = f"Optional: override base URL for {provider_name}"

        added_models.append({
            "alias": alias,
            "provider": provider_name,
            "base_url": base_url,
            "key_env": key_env,
            "url_env": url_env,
            "model": model_name,
        })

        print(f"     ✓ Added to .env as {key_env}")
        print()

    if not added_models and not env.get("ROUTER_API_KEY", "").startswith("sk-"):
        print("  No providers configured. You can always re-run: python configure.py")
        print()

    # ── Write env ────────────────────────────────────────────────────

    _write_env(env, comments)
    print(f"  ✓ Keys saved to {ENV_PATH}")
    print()

    # ── Write models.yaml ─────────────────────────────────────────────

    if added_models:
        _write_models(added_models)
        print(f"  ✓ Model aliases added to {YAML_PATH}")
        print()

    # ── Summary ─────────────────────────────────────────────────────

    print("── Summary ──────────────────────────────────────")
    print(f"  Router key:   sk-...{env.get('ROUTER_API_KEY', '')[-8:]}")
    for m in added_models:
        print(f"  ✓ {m['alias']}  →  {m['model']}  @  {m['base_url']}")
    print()

    if added_models:
        print("  Next steps:")
        print("    1. docker compose up -d")
        print("    2. curl http://localhost:7321/health")
        print("    3. hermes ask \"hello\"")
        print()
    else:
        print("  Next step:")
        print("    Re-run: python configure.py")
        print()


# ── check mode ─────────────────────────────────────────────────────


def run_check() -> None:
    """Non-interactive check: report what's configured."""
    env = _load_env()

    router_key = env.get("ROUTER_API_KEY", "")
    if router_key.startswith("sk-"):
        print(f"✓ ROUTER_API_KEY = sk-...{router_key[-8:]}")
    else:
        print("✗ ROUTER_API_KEY missing or invalid")
        print("  Run: python configure.py")
        sys.exit(1)

    # Report any CUSTOM_*_API_KEY env vars (set by this wizard)
    provider_keys = [(k, v) for k, v in env.items() if k.endswith("_API_KEY") and k != "ROUTER_API_KEY"]
    for key, val in provider_keys:
        print(f"✓ {key} = {val[:12]}...")

    if not provider_keys:
        print()
        print("  No providers configured yet.")
        print("  Run: python configure.py")
        print()


# ── entry point ────────────────────────────────────────────────────


if __name__ == "__main__":
    if "--check" in sys.argv:
        run_check()
    else:
        run_interactive()
