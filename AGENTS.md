# Vision-Bill Agent Guide

This document provides technical context for agents working on the vision-bill project.

## Project Overview
**vision-bill** is an invoice tracking API designed to prioritize privacy by using local multi-modal LLMs (via Ollama) for data extraction from receipts and invoices. It eliminates the need to send sensitive PII to external cloud services.

## Technology Stack
- **Language**: Python 3.12+
- **Web Framework**: FastAPI, Uvicorn
- **LLM Engine**: Ollama (Local inference)
- **Database**: PostgreSQL (`asyncpg`)
- **Core Libraries**:
    - `pydantic`: Data validation and settings management.
    - `httpx`: Asynchronous HTTP client.
    - `python-magic`: File type identification.

## Architecture & Key Modules
### 1. API Layer (`src/vision_bill/api`)
Handles all external requests, including receipt uploads and system configuration endpoints.

### 2. Service Layer (`src/vision_bill/service`)
Contains the core business logic:
- `receipt_service`: Orchestrates the workflow from image upload to data extraction.
- `image_service`: Manages image processing and validation.

### 3. Provider Layer (`src/vision_bill/provider`)
An abstraction layer for LLM interaction:
- **Model Discovery**: Automatically identifies available local models and filters for those with `vision` capabilities.
- **Self-Correction**: Implements a retry loop that feeds back parsing errors to the LLM, prompting it to correct malformed JSON outputs.

### 4. Model & Configuration Layer
- `src/vision_bill/model`: Defines Pydantic models (e.g., `Receipt`) used for schema enforcement.
- `src/vision_bill/config.py`: Centralized configuration using nested environment variables (e.g., `LLM__MODEL_NAME`).

## Development Workflow
- **Package Manager**: Uses `uv`. Use `uv` for installing dependencies and running commands.
- **Run App**: `uvicorn src.vision_bill.main:app --host 0.0.0.0 --port 8080 --reload --reload-dir ./src/vision_bill`
- **Database migrations**: Hand-written raw SQL in `alembic/versions/` (no autogenerate). Before starting the app run `uv run alembic upgrade head` (safe on existing DBs — migration 0001 uses `IF NOT EXISTS`). New migration: `uv run alembic revision -m "message"`, then edit `alembic/versions/<rev>_<message>.py` with explicit SQL. Docker Compose runs the upgrade automatically before uvicorn.
- **Lint & Typecheck**: Run `ruff check .` and `mypy .` (ensure project root context).
- **Testing**:
  - Unit tests: `pytest tests/`
  - Functional tests: See `scripts/run_functional_tests.py`. Requires specific data in `tests/data/`.

## Operational Notes & Constraints
- **Local Inference Only**: All LLM interactions are local via Ollama. Ensure vision models (e.g., Llama3-Vision, Moondream) are pre-downloaded on the host.
- **File Detection**: Uses `python-magic` for identifying file types; ensure this library is available in the environment.
- **Privacy**: PII never leaves the local machine. Do not propose any external API calls for data processing unless explicitly requested and approved.

## Contextual Hints
- Entry point: `src/vision_bill/main.py`
- Configuration: Managed via `src/vision_bill/config.py` using nested environment variables (e.g., `LLM__MODEL_NAME`).

## Edit files
- The edit tool matches oldString byte-for-byte. Read the file again immediately before each edit, and again after every successful edit line content shifts.
- Copy oldString verbatim from the file you just read. Do not retype, reindent or normalise it. Preserve tabs, trailing spaces and blank lines.
- Keep oldString to the smallest span that is still unique — usually one or two lines, not a whole block.
- After two failed edits on the same file, stop and report. Do not switch to rewriting the file.
