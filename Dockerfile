# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml .
RUN pip install --no-cache-dir --user .

COPY app/ app/

FROM python:3.12-slim

# Create non-root user
RUN groupadd -r larpwing && useradd -r -g larpwing -d /app -s /sbin/nologin larpwing

WORKDIR /app

# Copy installed deps from builder
COPY --from=builder /root/.local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /root/.local/bin/ /usr/local/bin/

# Copy setup wizard
COPY configure.py .
COPY pyproject.toml .

# Copy application code
COPY app/ app/

# Copy default config (overridden by volume mount in docker-compose)
COPY config/ config/

COPY .env.example .env.example

RUN chown -R larpwing:larpwing /app

USER larpwing

EXPOSE 7321

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7321/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7321"]
