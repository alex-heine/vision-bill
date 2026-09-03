# vision-bill development workflow.
.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help install-uv setup migrate run docker-build docker-up docker-down docker-logs test lint context-budget \
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

docker-build: ## Build the Docker image
	docker build -t vision-bill .

docker-up: ## Build image + start app and postgres
	docker compose up --build

docker-down: ## Stop app and postgres
	docker compose down

docker-logs: ## Follow vision_bill container logs
	docker compose logs -f vision_bill

test: ## Run unit tests
	uv run --extra dev pytest tests/

lint: ## Lint (ruff) and type-check (mypy)
	uv run ruff check src
	uv run mypy src

context-budget: ## Measure the exact prompt/image token budget on an Ollama model
	uv run python scripts/context_budget.py $(ARGS)

# --- Frontend (SvelteKit SPA) -------------------------------------------
# Node/npm are provided by nvm. Each recipe selects a supported Node version,
# independent of the caller's global default.

NVM_DIR ?= $(HOME)/.nvm
NODE := . "$(NVM_DIR)/nvm.sh" >/dev/null 2>&1 &&
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

fe-test-e2e: ## Run frontend E2E tests (playwright)
	$(NODE) (cd $(FE) && npm run test:e2e)

fe-verify: fe-check fe-test fe-build ## Run frontend checks, unit tests, and a production build

fe: ## Run an npm script in frontend/ (make fe CMD=<script> [ARGS="..."])
	@test -n "$(CMD)" || { echo "usage: make fe CMD=<npm-script> [ARGS=\"arg1 arg2\"]"; exit 1; }
	$(NODE) (cd $(FE) && npm run $(CMD) $(ARGS))
