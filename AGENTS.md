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

## Development Context
- **Testing**: Functional tests are located in `scripts/` and unit tests in `tests/`. Ground truth data for model evaluation is in `tests/data/`.
- **Privacy**: Always ensure that data processing remains local unless explicitly configured otherwise.
- **LLM Interaction**: When adding new providers, inherit from the base provider to maintain compatibility with the self-correction logic.
