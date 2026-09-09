# vision-bill development workflow.
.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help install-uv setup migrate run docker-build docker-up docker-down docker-logs test lint context-budget \
	script-context-budget script-create-benchmark db-configure-roles \
	e2e-up e2e-down test-e2e \
	fe-install fe-dev fe-build fe-sync fe-deploy fe-docker fe-check fe-test fe-test-e2e fe-verify fe

help: ## Show this help
	@echo "vision-bill — available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

setup: ## Install project + dev extra (ruff, mypy, pytest) via uv
	uv sync --extra dev

migrate: ## Apply database migrations
	uv run alembic upgrade head

run: ## Run the API locally with auto-reload
	uv run uvicorn src.vision_bill.main:app --host 0.0.0.0 --port 8080 --reload --reload-dir ./src/vision_bill

# Docker Hub target for a future `make docker-push` (push is skipped for now).
# `docker-build` always tags vision-bill:latest locally; it also tags the full
# Hub name only when a username is provided, e.g.:
#   make docker-build DOCKER_USER=me
#   make docker-build DOCKER_USER=me DOCKER_TAG=v1.0
DOCKER_REGISTRY ?= docker.io
DOCKER_USER ?=
DOCKER_REPO ?= vision-bill
DOCKER_TAG ?= latest
ifeq ($(strip $(DOCKER_USER)),)
IMAGE :=
else
IMAGE := $(DOCKER_REGISTRY)/$(DOCKER_USER)/$(DOCKER_REPO):$(DOCKER_TAG)
endif

docker-build: ## Build the image (personal data excluded via .dockerignore)
	docker build -t vision-bill:$(DOCKER_TAG) $(if $(IMAGE),-t $(IMAGE)) .

docker-up: ## Build image + start app and postgres
	docker compose up --build

docker-down: ## Stop app and postgres
	docker compose down

docker-logs: ## Follow vision_bill container logs
	docker compose logs -f vision_bill

test: ## Run unit tests (e2e excluded; see test-e2e)
	uv run --extra dev pytest tests/ -m "not e2e"

e2e-up: ## Build and start the e2e stack (manual; the test targets manage it)
	$(E2E_COMPOSE) up -d --build

e2e-down: ## Stop the e2e stack and delete its volumes (manual)
	$(E2E_COMPOSE) down -v

# The e2e test targets own the stack lifecycle: start it for the run and
# always tear it down on exit (the EXIT trap covers failures and Ctrl-C).
E2E_COMPOSE := docker compose -f docker-compose.e2e.yml
test-e2e: ## Run backend e2e tests (starts the e2e stack, always tears it down)
	@bash -c 'trap "$(E2E_COMPOSE) down -v" EXIT; \
		$(E2E_COMPOSE) up -d --build && uv run python e2e/wait_ready.py && \
		uv run --extra dev pytest tests/e2e/'

fe-test-e2e: ## Playwright e2e (starts the e2e stack, always tears it down)
	@bash -c 'trap "$(E2E_COMPOSE) down -v" EXIT; \
		$(E2E_COMPOSE) up -d --build && uv run python e2e/wait_ready.py && \
		$(NODE) (cd $(FE) && npm run test:e2e)'

lint: ## Lint (ruff) and type-check (mypy)
	uv run ruff check src
	uv run mypy src

# --- Operational scripts -------------------------------------------------
# Values loaded here become real environment variables and therefore override
# the application's .env files. Override with: make ... SCRIPTS_ENV=path/to/file
SCRIPTS_ENV ?= .env.scripts
WITH_SCRIPTS_ENV = set -a; if [[ -f "$(SCRIPTS_ENV)" ]]; then source "$(SCRIPTS_ENV)"; fi; set +a;

script-context-budget: ## Measure Ollama context usage (ARGS="...")
	@$(WITH_SCRIPTS_ENV) uv run python scripts/context_budget.py $(ARGS)

script-create-benchmark: ## Queue a benchmark API run (ARGS="...")
	@$(WITH_SCRIPTS_ENV) uv run python scripts/create_benchmark_run.py $(ARGS)

db-configure-roles: ## Create/update PostgreSQL runtime and read-only group roles
	@$(WITH_SCRIPTS_ENV) test -n "$$MIGRATION_DATABASE_URL" || { echo "Set MIGRATION_DATABASE_URL in $(SCRIPTS_ENV)"; exit 2; }; \
		psql "$$MIGRATION_DATABASE_URL" -v database_name="$${PG__DB:-vision_bill}" -f scripts/configure_db_roles.sql

context-budget: script-context-budget ## Alias for script-context-budget

# --- Frontend (SvelteKit SPA) -------------------------------------------
# Node/npm come from nvm when present (local dev, pinned Node version
# independent of the caller's global default); otherwise the system Node is
# used (e.g. GitHub Actions runners, where actions/setup-node provides it).

NVM_DIR ?= $(HOME)/.nvm
ifeq ($(wildcard $(NVM_DIR)/nvm.sh),)
NODE :=
else
NODE := . "$(NVM_DIR)/nvm.sh" >/dev/null 2>&1 &&
endif
FE := frontend

fe-install: ## Install locked frontend npm dependencies
	$(NODE) (cd $(FE) && npm ci)

fe-dev: ## Run the Vite dev server on :5173 (proxies /api -> :8080)
	$(NODE) (cd $(FE) && npm run dev)

fe-build: ## Build the SPA into frontend/out (run fe-install once after dependency changes)
	$(NODE) (cd $(FE) && npm run build)

fe-sync: fe-build ## Copy the built SPA into src/vision_bill/static for FastAPI/Docker
	rm -rf src/vision_bill/static
	mkdir -p src/vision_bill/static
	cp -r $(FE)/out/. src/vision_bill/static/
	touch src/vision_bill/static/.gitkeep

fe-deploy: fe-sync ## Build and sync the SPA into the host directory mounted by Docker

fe-docker: fe-deploy ## Build, sync, and restart the Docker API service
	docker compose restart vision_bill

fe-check: ## Frontend static checks (svelte-check + eslint + prettier)
	$(NODE) (cd $(FE) && npm run check && npm run lint && npm run format:check)

fe-test: ## Run frontend unit tests (vitest)
	$(NODE) (cd $(FE) && npm run test)

fe-verify: fe-check fe-test fe-build ## Run frontend checks, unit tests, and a production build

fe: ## Run an npm script in frontend/ (make fe CMD=<script> [ARGS="..."])
	@test -n "$(CMD)" || { echo "usage: make fe CMD=<npm-script> [ARGS=\"arg1 arg2\"]"; exit 1; }
	$(NODE) (cd $(FE) && npm run $(CMD) $(ARGS))
