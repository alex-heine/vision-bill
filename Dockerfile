FROM python:3.12-slim

# Install uv (grabbed from the official distroless image, no extra deps needed)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies into a project-local venv, based only on the lockfile
# (no source yet, so this layer is cached until deps actually change)
RUN uv sync --frozen --no-install-project

# Now copy the source (plus the alembic migration tooling the app relies on)
COPY ./src ./src
COPY alembic.ini ./
COPY ./alembic ./alembic

RUN apt update && apt install -y --no-install-recommends libmagic1 && rm -rf /var/lib/apt/lists/*

# Install the project itself (editable, matches the lockfile)
RUN uv sync --frozen

# Make sure the venv's binaries are used
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080

CMD ["uvicorn", "src.vision_bill.main:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]
