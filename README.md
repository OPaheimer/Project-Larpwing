# Larpwing

A lightweight OpenAI-compatible model alias router. Point any OpenAI client at Larpwing, use short alias names for your models, and Larpwing translates them to real backend model IDs and forwards the request.

```
          ┌──────────────┐     model: "fast-chat"         ┌──────────────────┐
 Client ──▶  Larpwing    ──────────────────────────────────▶  DeepSeek API    │
          │  127.0.0.1   │     real model: "gpt-4o-mini"         OpenAI      │
          │  :7321       ◀──────────────────────────────────  Groq           │
          └──────────────┘     response (JSON or SSE)     │  Your provider  │
                                                          └──────────────────┘
```

Supports streaming, tool calling, and all OpenAI-compatible fields. One config change to switch providers — no client-side changes needed.

## Features

- **Multi-provider routing** — DeepSeek, OpenAI, Groq, Google, Mistral, xAI, Pioneer, local, or any OpenAI-compatible API
- **Custom provider wizard** — `python configure.py` interactively adds providers
- **Streaming** — SSE chunks relayed byte-for-byte
- **Tool calling** — tools and tool_choice pass through unchanged
- **Docker** — single container, healthcheck, config mounted read-only
- **Safe logging** — never logs API keys or message content
- **OpenAI-compatible errors** — all errors return OpenAI-style JSON

## Quick start

```bash
# 1. Clone and enter
git clone <repo-url> larpwing
cd larpwing

# 2. Run the setup wizard
python configure.py

# 3. Start
docker compose up -d

# 4. Test
curl http://localhost:7321/health
curl http://localhost:7321/v1/models \
  -H "Authorization: Bearer $(grep ROUTER_API_KEY .env | cut -d= -f2)"
```

The setup wizard will:
1. Generate a random `sk-` router API key
2. Ask for alias name, provider label, base URL, API key, and model name
3. Save keys to `.env` and alias config to `config/models.yaml`

## Example: adding a provider

```
$ python configure.py

── Step 2: Add Your Providers ───────────────────
  Add a provider? [Y/n]: y

  Alias name (e.g. fast-chat, coding-pro): fast-chat
  Provider label (e.g. openai, deepseek, local): deepseek
  Base URL (e.g. https://api.openai.com/v1): https://api.deepseek.com/v1
  API key: sk-yo....n
  Model name (e.g. gpt-4o-mini, deepseek-v4-flash): deepseek-v4-flash
```

## Configuration

### config/models.yaml

```yaml
models:
  fast-chat:
    provider: deepseek                     # label for logging
    base_url: https://api.deepseek.com/v1  # backend endpoint
    api_key_env: FAST_CHAT_API_KEY          # .env variable with the key
    api_url_env: FAST_CHAT_API_URL          # optional: override base_url via .env
    model: deepseek-v4-flash                # real model ID sent upstream
    context_length: 128000
    supports_tools: true
    supports_streaming: true
```

### .env

```
ROUTER_API_KEY=sk-yo....=***-# optional override
```

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | No | Health check |
| `GET` | `/v1/models` | Bearer token | List your model aliases |
| `POST` | `/v1/chat/completions` | Bearer token | Forward to your provider |

Accepts all OpenAI-compatible fields: `messages`, `model`, `stream`, `tools`, `tool_choice`, `temperature`, `max_tokens`, `top_p`, `stop`, `response_format`, etc.

## Run locally (bare metal)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python configure.py
uvicorn app.main:app --host 127.0.0.1 --port 7321 --reload
```

## Run with Docker

```bash
docker build -t larpwing .
docker compose up -d
docker inspect larpwing --format='{{.State.Health.Status}}'
```

## Run tests

```bash
pytest -v
```

24 tests covering health, auth, alias routing, streaming relay, tools passthrough, and all error paths. No real API calls.

## Architecture

- **Auth:** `Authorization: Bearer` checked via FastAPI `Depends`. Auth errors use `HTTPException`. All other errors return `JSONResponse` to avoid FastAPI's `{"detail": ...}` wrapper.
- **Streaming:** httpx client lives inside the SSE relay generator so it stays alive for the entire stream. Chunks relaid byte-for-byte.
- **Logging:** Request ID, alias, provider, streaming flag, status code, elapsed time. Never logs: API keys, message content, Authorization headers.
- **URL override:** If `api_url_env` is set and the env var exists, it overrides `base_url` at runtime — no YAML changes needed.

## License

MIT
