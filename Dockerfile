# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────────────
# suitewright — end-user runtime image
# Multi-stage: uv builder -> slim runtime
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build with uv ───────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:0.9-python3.11-bookworm-slim@sha256:4f5d923c9dcea037f57bda425dd209f3ec643da2f0b74227f68d09dab0b3bb36 AS builder

WORKDIR /build

# Create venv at the final runtime path so shebangs are correct after copy
ENV UV_PROJECT_ENVIRONMENT=/app/.venv

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock ./
COPY README.md LICENSE NOTICE ./

# Install dependencies only (no project yet)
RUN uv sync --frozen --no-install-project

# Copy source and install the project (non-editable for portability)
COPY src/ src/
RUN uv sync --frozen --no-editable

# ── Stage 2: Slim runtime ────────────────────────────────────────────────────
FROM python:3.11-slim@sha256:9a7765b36773a37061455b332f18e265e7f58f6fea9c419a550d2a8b0e9db834

# Create non-root user
RUN groupadd -g 1000 suitewright && \
    useradd -u 1000 -g 1000 -m -d /home/suitewright -s /bin/sh suitewright

# XDG directories for config and cache
ENV XDG_CONFIG_HOME=/home/suitewright/.config
ENV XDG_CACHE_HOME=/home/suitewright/.cache
ENV NO_COLOR=1

# Pre-create auth, runtime, and cache directories
RUN mkdir -p \
    /home/suitewright/.config/suitewright/auth \
    /home/suitewright/.cache/suitewright \
    /home/suitewright/runtime && \
    chown -R 1000:1000 /home/suitewright

# Copy the virtual environment from builder (built at /app/.venv so shebangs match)
COPY --from=builder --chown=1000:1000 /app/.venv /app/.venv

# Put the venv's bin on PATH so `suitewright` is directly callable
ENV PATH="/app/.venv/bin:${PATH}"

USER suitewright
WORKDIR /home/suitewright

ENTRYPOINT ["suitewright"]
