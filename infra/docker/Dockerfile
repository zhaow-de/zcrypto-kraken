# syntax=docker/dockerfile:1
FROM python:3.14-slim
LABEL org.opencontainers.image.source="https://github.com/zhaow-de/zcrypto-kraken"

# Pinned, static uv binary copied from the official image — no apt/curl install step needed.
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /usr/local/bin/

# Non-root runtime user. `compose.yaml` overrides the container's `user:` to the host's
# `kraken-capture` uid/gid at deploy time (so bind-mounted segment files land with the right
# host ownership); this user is just the image's own sane default for a standalone `docker run`.
RUN groupadd --system capture && useradd --system --gid capture --create-home --shell /usr/sbin/nologin capture

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}"

# README.md is copied too: hatchling (the build backend) reads `[project].readme` at build time.
COPY pyproject.toml uv.lock README.md ./
COPY cli/ cli/
# POLARS_RUNTIME=default -> keeps the AVX-optimized `polars-runtime-32` (the VPS, AMD EPYC).
# POLARS_RUNTIME=compat  -> swaps to `polars-runtime-compat` and drops the AVX runtime, so the
#   image runs on CPUs without AVX/AVX2 (the Synology NAS, Intel Atom Goldmont). Same polars
#   version either way; see docs/open-topics/T0029-nas-cpu-no-avx-polars.md.
ARG POLARS_RUNTIME=default
RUN uv sync --frozen --no-dev \
    && if [ "$POLARS_RUNTIME" = "compat" ]; then \
         V="$(uv pip show --python /app/.venv/bin/python polars | awk '/^Version:/{print $2}')"; \
         uv pip install --python /app/.venv/bin/python "polars-runtime-compat==$V"; \
         uv pip uninstall --python /app/.venv/bin/python polars-runtime-32; \
       fi \
    && /app/.venv/bin/python -c "import polars; polars.DataFrame({'a':[1]}).select('a')" \
    && chown -R capture:capture /app

USER capture

# CAPTURE_DATA_DIR / CAPTURE_DEPTH / CAPTURE_PAIRS (comma-separated) map to `zcrypto capture`'s
# --data-dir / --depth / --pairs flags; HEALTHCHECK_URL passes straight through as an env var
# since the daemon itself reads that one directly. Unset CAPTURE_PAIRS omits --pairs so the
# CLI falls back to its own universe-derived default.
ENTRYPOINT ["/bin/sh", "-c", "set -eu; set -- --data-dir \"${CAPTURE_DATA_DIR:-/var/lib/zcrypto-capture}\" --depth \"${CAPTURE_DEPTH:-100}\"; if [ -n \"${CAPTURE_PAIRS:-}\" ]; then IFS=','; for p in $CAPTURE_PAIRS; do set -- \"$@\" --pairs \"$p\"; done; unset IFS; fi; exec zcrypto capture \"$@\""]
