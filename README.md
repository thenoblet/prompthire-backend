# PromptHire Backend

FastAPI service for the PromptHire frontend. Generates three interview questions for a job title via `litellm` + `instructor`, with Postgres-backed audit logging and per-IP rate limiting.

See `docs/superpowers/specs/2026-05-09-fastapi-backend-design.md` for the full design.

## Requirements

- Python 3.11
- Postgres 14+
- An LLM provider key (Anthropic, OpenAI, etc.) supported by litellm

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -e . --no-deps                       # registers `app` (src layout)
docker compose up -d postgres                    # local Postgres for dev
cp .env.example .env                             # then edit: LITELLM_MODEL, provider key, DATABASE_URL
alembic upgrade head
uvicorn app.main:app --reload
```

The service listens on `:8000`. The frontend's Vite proxy forwards `/api/*` to it in development.

## Endpoints

- `GET /healthz` — liveness probe
- `POST /api/v1/generate` — generate three interview questions

## Layout

```
src/app/
  routers/         # FastAPI endpoints (incl. routers/v1/ for the public API)
  services/        # business logic / use cases
  repositories/    # data access against our own DB tables (audit, rate_limit)
  infrastructure/  # external integrations: DatabaseManager, LLMClient, prompts
  models/          # domain dataclasses + ORM tables under models/db/
  schemas/         # Pydantic wire DTOs (incl. ApiResponse[T] / ErrorResponse envelope)
  core/            # config, exceptions, error_handlers, rate_limit, deps
```

