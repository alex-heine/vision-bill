# vision-bill — Your Private Invoice Tracker

### 🛡️ Privacy First
**vision-bill** is a local-first tool designed to process receipts without ever uploading your data to the cloud. Receipts contain highly sensitive personal and financial information (PII); this project ensures that everything—from image processing to LLM reasoning—stays on your machine.

### 🚀 Core Features
- **Multi-modal Local LLMs:** Uses Ollama to run vision-capable models (like Llama-3-Vision, Moondream, or Gemma) directly on your hardware.
- **Local Extraction:** No separate OCR engine is required; the LLM performs both image understanding and structured data extraction in one step.
- **Privacy-Preserving Architecture:** Built with FastAPI to serve as a local backend for personal use.
- **Non-sequential identifiers:** Users, receipts, images, line items, taxes, tags, and benchmark runs use UUIDs throughout the database and API.

### 🛠️ Quickstart (Docker)
The fastest way to get started is using Docker Compose:
```bash
docker compose up -d
```
*Note: You must have [Ollama](https://ollama.com/) installed and running on your host machine with vision-capable models downloaded.*

### ⚙️ Configuration
The application persists its resolved settings in `/app/config/config.yaml`,
which Docker stores on the host at `./server_data/config`. The file is created
on first startup from environment defaults. Environment variables always take
precedence and are marked as environment-controlled in the admin Settings page.
The page can change the default model, provider connection settings, and
registration policy without exposing database credentials or secrets. Model,
temperature, and registration changes apply immediately; changing the
provider or host requires a server restart.

### ⚙️ Local Configuration & Selection
Since different LLMs perform differently at image extraction, the project includes a model selection system:
- **Model Testing:** Use `tests/data` to evaluate local models against known ground-truth JSON outputs.
- **Selection Logic:** The app can dynamically identify and rank available models based on their performance in "guessing" correct receipt details.
- **Customization:** Easily swap or tune the underlying Ollama models via your host configuration.

### 📦 Tech Stack
- **Backend:** Python, FastAPI, Pydantic
- **Inference:** Ollama (Local LLM execution)
- **Deployment:** Docker, UV (Dependency management)
- **Testing:** Pytest
