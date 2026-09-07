# AEGIS backend — FastAPI + uvicorn, single process (state is in-memory).
# Build context is the repo root:  docker build -f backend/Dockerfile .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first for layer caching. requirements.txt is the project's
# existing dependency file — nothing added.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Application code
COPY backend/ backend/

EXPOSE 8000

# Exactly one worker: the live NetworkState lives in this process's memory.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
