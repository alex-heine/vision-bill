#!/bin/sh
# Image entrypoint: migrate the schema, then start the server.
#
# We `exec` the final command so the server replaces this shell and becomes
# PID 1. That is what lets `docker stop` (SIGTERM) reach uvicorn directly for
# a graceful shutdown — the exact behavior BuildKit's JSONArgsRecommended
# check asks for, which a plain shell-form `CMD … && …` cannot provide.
#
# Running the migration here (rather than only in docker-compose) keeps the
# image self-sufficient: `docker run` on a fresh DB works, and new migrations
# apply on upgrade. docker-compose's `depends_on: db: service_healthy` gate
# keeps this safe when orchestrated.
set -e

uv run alembic upgrade head

# Import/update GPC data if needed
SQL_PATH=/app/src/vision_bill/data/gpc_import.sql
if [ -f "$SQL_PATH" ]; then
    if ! python -m vision_bill.gpc_check --db-url "$PG_DSN" --sql-path "$SQL_PATH"; then
        echo "GPC data up to date"
    else
        echo "Importing GPC data..."
        python -m vision_bill.gpc_import --db-url "$PG_DSN" --sql-path "$SQL_PATH"
    fi
fi

exec "$@"
