# vision-bill development workflow.
.DEFAULT_GOAL := help

.PHONY: help install-uv setup migrate run docker-build docker-up docker-down docker-logs test lint

help: ## Show this help
	@echo "vision-bill — available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

install-uv: ## Install uv via the official installer (skips if already on PATH)
	@command -v uv > /dev/null 2>&1 && echo "uv already installed" && exit 0 || \
		curl -LsSf https://astral.sh/uv/install.sh | sh

setup: ## Install project + dev extra (ruff, mypy, pytest) via uv
	uv sync --extra dev

migrate: ## Apply database migrations
	uv run alembic upgrade head

run: ## Run the API locally with auto-reload
	uv run uvicorn src.vision_bill.main:app --host 0.0.0.0 --port 8080 --reload --reload-dir ./src/vision_bill

docker-build: ## Build the Docker image
	docker build -t vision-bill .

docker-up: ## Build image + start app and postgres
	docker compose up -d --build

docker-down: ## Stop app and postgres
	docker compose down

docker-logs: ## Follow vision_bill container logs
	docker compose logs -f vision_bill

test: ## Run unit tests
	uv run pytest tests/

lint: ## Lint (ruff) and type-check (mypy)
	uv run ruff check src
	uv run mypy src
