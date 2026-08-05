FROM python:3.11-slim

# Install uv (grabbed from the official distroless image, no extra deps needed)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies into a project-local venv, based only on the lockfile
# (no source yet, so this layer is cached until deps actually change)
RUN uv sync --frozen --no-install-project

# Now copy the source
COPY ./src ./src

RUN apt update && apt install -y --no-install-recommends libmagic1 && rm -rf /var/lib/apt/lists/*

# Install the project itself (editable, matches the lockfile)
RUN uv sync --frozen

# Make sure the venv's binaries are used
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "src.vision_bill.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
