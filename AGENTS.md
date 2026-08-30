# Vision-Bill Agent Guide

This document provides technical context for agents working on the vision-bill project.

## Project Overview
**vision-bill** is an invoice tracking API designed to prioritize privacy by using local multi-modal LLMs (via Ollama) for data extraction from receipts and invoices. It eliminates the need to send sensitive PII to external cloud services.

## Technology Stack
- **Language**: Python 3.12+
- **Web Framework**: FastAPI, Uvicorn
- **LLM Engine**: Ollama (local inference, `ollama` Python SDK)
- **Database**: PostgreSQL (`asyncpg` pool, raw SQL — no ORM in use)
- **Migrations**: Alembic (hand-written raw SQL)
- **Core Libraries**:
    - `pydantic` / `pydantic-settings`: Data validation and settings management.
    - `httpx`: Asynchronous HTTP client.
    - `python-magic`: File type identification (requires system `libmagic`).
- **Package Manager**: `uv` (lockfile: `uv.lock`)

## Repository Layout
- `src/vision_bill/` — Application package (API, services, providers, models, config).
- `alembic/` — Migration tooling; versions in `alembic/versions/`.
- `tests/` — Pytest suite (`asyncio_mode = "auto"`); ground-truth fixtures in `tests/data/` (image + expected JSON pairs).
- `scripts/` — Helper scripts (`run_functional_tests.py`, `llm_benchmark_runner.py`).
- `image-sticher/` — Standalone client-side image-stitching HTML tool (served via nginx, see `docker-compose.image-stichter.yml`).
- `server/nginx_site.conf` — Nginx site config for reverse-proxy deployments.
- `Makefile` — Canonical dev workflow targets (see Development Workflow).
- `Dockerfile` / `docker-compose.yml` — Containerized app + PostgreSQL.

## Architecture & Key Modules
All application code lives under `src/vision_bill/`. Entry point: `main.py`.

### 1. API Layer (`api/`)
FastAPI routers, all mounted under versioned prefixes in `main.py`:
- `api/images.py` — mounted at `/api/v1/images`:
    - `POST /?model_id=...` — multipart upload; returns `201` with a `Location` header when analyzed, `202` with a `Location` header when queued, `415` for unsupported image types.
    - `GET /` — lists images, optionally filtered with `?status=pending,failed`.
    - `GET /{id}`, `DELETE /{id}` — inspect or delete pending/failed image resources.
    - `POST /analyze` — manually trigger one pending-image analysis cycle.
- `api/receipts.py` — mounted at `/api/v1/receipts`:
    - `GET /`, `GET /{id}`, `PUT /{id}` — list, inspect, and update persisted receipts.
    - `POST /{id}/verify` — marks a receipt verified and moves its image from tmp to permanent storage.
    - All endpoints return `503` when the DB pool is unavailable.
- `api/system/llm.py` — mounted at `/api/v1/llm`: `GET /models` lists vision-capable models.
- `api/system/main.py` — mounted at `/api/v1/system` (mostly stubbed).
- `api/helper/helper.py` — FastAPI dependencies (`get_receipt_service`, `get_image_service`, `get_analysis_scheduler`) backed by `app.state`.

### 2. Service Layer (`service/`)
Core business logic:
- `receipt_service.py`: Orchestrates upload → LLM extraction → persistence. Delegates all DB access to `ReceiptDB`. Also supports `extract_receipt_all_models` (concurrent extraction across every available model via `asyncio.gather`).
- `image_service.py`: Image validation/inspection via a singleton `MagicService` (python-magic); manages temporary (`store_tmp_image`) and permanent (`store_perm_image`) image storage.

### 3. Provider Layer (`provider/`)
Abstraction over external dependencies:
- `provider/llm/base.py` — `LLMProvider` ABC: `get_available_models`, `analyse_receipt_from_model`, `send_message`, plus shared `build_prompt` (embeds `Receipt.model_json_schema()`) and `parse_llm_response`.
- `provider/llm/ollama.py` — `OllamaProvider`:
    - **Model Discovery**: Lists local Ollama models and filters to those with the `vision` capability.
    - **Self-Correction**: Retry loop (`RETRY_LIMIT = 3`) that appends the failed output + validation error back to the conversation so the model can emit corrected JSON.
- `provider/factory.py` — `get_llm_provider(settings.llm)`. Only `OLLAMA` is implemented; the `LLMProviderEnum` also declares `ANTHROPIC`/`OPENAI` but they raise `ValueError` (and are out of scope — see Privacy constraint).
- `provider/db/receipt_db.py` — `ReceiptDB`: asyncpg pool, raw SQL DML for receipts, line items, taxes (`persist_receipt`, `get_receipt_with_details`, `update_receipt`, `verify_receipt`, ...). DDL lives only in Alembic migrations.
- `provider/db/image_db.py` — currently an empty placeholder (image persistence is handled by `ImageService` file storage, not the DB).

### 4. Model Layer (`model/`)
- `model/receipt.py` — Pydantic `Receipt` schema (incl. `confidence` 0–100, line items, taxes, totals) used for LLM output enforcement.
- `model/image.py` — Pydantic models for image info.
- `model/db/receipt.py`, `model/db/image.py` — DB row models (`ReceiptRow`, `ReceiptWithDetails`, `LineItemRow`, `TaxLineRow`, ...).

### 5. Configuration (`config.py`)
Pydantic settings loaded from `.env` and `.env.local` with nested delimiter `__` (e.g. `LLM__MODEL_NAME`, `PG__HOST`). Sections:
- `api` — port, log level.
- `images` — `save_dir`, `tmp_dir` (mounted volumes in Docker: `./uploads`, `./uploads_tmp`).
- `llm` — `provider` (default `ollama`), `host`, `model_name`, `temperature`, `api_key`.
- `pg` — user/password/db/host/port; exposes `database_url` (SQLAlchemy-style) and `pg_dsn` (plain DSN for asyncpg).

### 6. App Lifecycle (`main.py`)
FastAPI `lifespan` creates the LLM provider and `ReceiptService`, initialises the DB pool (failure is logged, app continues without DB), and exposes services on `app.state`. A static frontend is mounted last at `/` from `src/vision_bill/static` so it never shadows `/api` routes.

## Database & Migrations
- PostgreSQL; schema owned by Alembic. Migrations are hand-written raw SQL in `alembic/versions/` (no autogenerate). Current: `0001_initial_schema.py`, `dcd2dd9d789c` (adds `confidence` + `verified` to receipts).
- Receipts carry a workflow: `status` (`unverified` → `verified`) plus `confidence` and `verified` columns; the image lives in tmp storage until `verify` moves it to permanent storage.
- Before starting the app: `uv run alembic upgrade head` (safe on existing DBs — migration 0001 uses `IF NOT EXISTS`).
- New migration: `uv run alembic revision -m "message"`, then edit `alembic/versions/<rev>_<message>.py` with explicit SQL.
- Docker Compose runs `alembic upgrade head` automatically before uvicorn.

## Development Workflow
A `Makefile` defines the canonical workflow (`make help` lists targets):
- `make install-uv` — install uv if missing.
- `make setup` — `uv sync --extra dev` (installs ruff, mypy, pytest).
- `make migrate` — `uv run alembic upgrade head`.
- `make run` — run the API locally with auto-reload on port 8080.
- `make test` — `uv run pytest tests/`.
- `make lint` — `uv run ruff check src` + `uv run mypy src` (mypy runs in `strict` mode; `alembic/` is excluded from both).
- `make docker-build` / `docker-up` / `docker-down` / `docker-logs` — container workflow.

Additional notes:
- **Pre-commit**: `.pre-commit-config.yaml` runs `make lint` and `make test` on every commit (hooks are local; `uv` must be on PATH).
- **Functional tests**: `scripts/run_functional_tests.py`; requires the image/JSON fixture pairs in `tests/data/`.
- **Test data**: `tests/data/` holds real receipt images alongside ground-truth JSON used to evaluate model extraction quality.

## Docker & Deployment
- `Dockerfile`: python:3.12-slim + uv; installs `libmagic1` for python-magic; frozen sync from lockfile.
- `docker-compose.yml`: app + `postgres:18` (host port `54321:5432`, healthcheck-gated). App container mounts `./src/vision_bill`, `./logs`, `./uploads`, `./uploads_tmp`; uses `host.docker.internal:host-gateway` so it can reach Ollama on the host.
- `docker-compose.image-stichter.yml` + `image-sticher/` + `server/nginx_site.conf`: optional nginx-served image-stitching frontend.

## Operational Notes & Constraints
- **Local Inference Only**: All LLM interactions are local via Ollama. Ensure vision models (e.g. Llama-3-Vision, Moondream, Gemma) are pre-downloaded on the host.
- **File Detection**: Uses `python-magic`; the system library `libmagic` must be available (`libmagic1` on Debian/Ubuntu).
- **Privacy**: PII never leaves the local machine. Do not propose any external API calls for data processing unless explicitly requested and approved.

## Contextual Hints
- Entry point: `src/vision_bill/main.py`
- Configuration: `src/vision_bill/config.py` (nested env vars, e.g. `LLM__MODEL_NAME`, `PG__HOST`)
- DB access pattern: services never touch asyncpg directly — go through `provider/db/`
- LLM access pattern: services never call Ollama directly — go through `provider/llm/` + `provider/factory.py`

## Edit files
- The edit tool matches oldString byte-for-byte. Read the file again immediately before each edit, and again after every successful edit line content shifts.
- Copy oldString verbatim from the file you just read. Do not retype, reindent or normalise it. Preserve tabs, trailing spaces and blank lines.
- Keep oldString to the smallest span that is still unique — usually one or two lines, not a whole block.
- After two failed edits on the same file, stop and report. Do not switch to rewriting the file.
