#!/usr/bin/env sh
# =============================================================================
# Container entrypoint
# =============================================================================
# Applies any pending Alembic migrations, then hands off to the CMD (uvicorn).
# Using `exec "$@"` replaces the shell with the application process so SIGTERM
# from `docker stop` reaches uvicorn directly and shutdown is graceful.
# =============================================================================

set -e

echo "[entrypoint] Applying database migrations..."
alembic upgrade head
echo "[entrypoint] Migrations applied. Starting application: $*"

exec "$@"
