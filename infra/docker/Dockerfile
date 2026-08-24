# syntax=docker/dockerfile:1
FROM python:3.14-slim
LABEL org.opencontainers.image.source="https://github.com/zhaow-de/zcrypto-kraken"

# Pinned, static uv binary copied from the official image — no apt/curl install step needed.
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /usr/local/bin/

# rsync + ssh client: the archive-pull service (Role A, spec 00048) shells out to `rsync -e ssh`
# to pull segments from the VPS. The capture/engine services don't use them but share this image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends rsync openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user, fixed at uid/gid 1000. The VPS capture/engine compose files override
# `user:` to the host's `kraken-capture`/`kraken-engine` *system* uids (100-999), so this default
# is inert there. The NAS archive-pull runs as `1000:1000` (spec 00048) and shells out to `ssh`,
# which calls getpwuid(getuid()) at startup and exits 255 ("No user exists for uid 1000") if the
# running uid has no /etc/passwd entry — so uid 1000 must exist in the image. (1000 is unused in
# the base image; the VPS system uids never collide with it.)
RUN groupadd --gid 1000 capture && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin capture

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}"

# README.md is copied too: hatchling (the build backend) reads `[project].readme` at build time.
COPY pyproject.toml uv.lock README.md ./
COPY cli/ cli/
# Not documentation: `cli.data.sync` reads this at runtime to verify frozen sets whose own manifest
# vouches nothing, and the image runs `push_hot`. Absent, that verification degrades to a no-op.
COPY docs/reference/vouched-dataset-hashes.jsonl docs/reference/
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

# GIT_REVISION (the commit sha, CI-supplied) changes on every build; declared after `uv sync`
# so a new revision never busts that layer's cache. cli/engine/cycle.py::_code_version() reads
# ZCRYPTO_BUILD_REVISION to append `+<sha12>` to the package version -- see
# docs/specs/00089-venue-truth-design.md D8. Empty by default, so a local `docker build` is unaffected.
ARG GIT_REVISION=""
ENV ZCRYPTO_BUILD_REVISION=$GIT_REVISION

USER capture

# CAPTURE_DATA_DIR / CAPTURE_DEPTH / CAPTURE_PAIRS (comma-separated) map to `zcrypto capture`'s
# --data-dir / --depth / --pairs flags; HEALTHCHECK_URL passes straight through as an env var
# since the daemon itself reads that one directly. Unset CAPTURE_PAIRS omits --pairs so the
# CLI falls back to its own universe-derived default. ZCRYPTO_SHIP_LOGS unset/empty omits
# --ship-logs (the CLI's own global flag, read before `capture`); set it non-empty to ship logs
# to Grafana Cloud Loki too (needs ZCRYPTO_LOKI_*/ZCRYPTO_LOG_* env vars -- cli/__main__.py).
ENTRYPOINT ["/bin/sh", "-c", "set -eu; set -- --data-dir \"${CAPTURE_DATA_DIR:-/var/lib/zcrypto-capture}\" --depth \"${CAPTURE_DEPTH:-100}\"; if [ -n \"${CAPTURE_PAIRS:-}\" ]; then IFS=','; for p in $CAPTURE_PAIRS; do set -- \"$@\" --pairs \"$p\"; done; unset IFS; fi; exec zcrypto ${ZCRYPTO_SHIP_LOGS:+--ship-logs} capture \"$@\""]
