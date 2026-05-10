# PromptHire Backend

FastAPI service that generates three role-specific interview questions for a 30-minute screening, given a job title. Built with a strict layered architecture, resilient LLM access (retries + multi-model fallback), Postgres-backed caching and rate limiting, and a typed wire envelope shared with the [PromptHire frontend](https://github.com/thenoblet/prompthire-frontend).

## What this service does

- Accepts `POST /api/v1/generate` with a job role (e.g. `"Senior Backend Engineer"`).
- Returns exactly three structured questions: `{ category, question, rationale }`.
- Caches identical roles for 24 hours, so repeat traffic doesn't hit the LLM.
- Applies layered rate limits (per-IP/min, per-IP/day, global/day) sized for free-tier provider quotas.
- Falls back through a configurable model chain when a provider rate-limits, times out, or auth-fails — so a free-tier outage doesn't take the demo down.
- Audits every attempt (success, schema failure, upstream error, cache hit) to a `generations` table for post-hoc analysis.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Web framework | **FastAPI** + Uvicorn | Async-first, strong Pydantic integration, lifespan-managed app state. |
| Validation / config | **Pydantic v2** + `pydantic-settings` | Wire DTOs and env-driven config in one type system. |
| LLM access | **litellm** + **instructor** | Provider-agnostic SDK; structured outputs enforced via Pydantic schemas. |
| Resilience | **tenacity** | Exponential-backoff retries on transient provider errors. |
| Storage | **PostgreSQL 16** via async **SQLAlchemy 2.0** + **asyncpg** | Async-friendly ORM, atomic `INSERT … ON CONFLICT DO UPDATE` for counters. |
| Migrations | **Alembic** | Async-engine env, hand-written migrations for predictability. |
| Tooling | **ruff** (lint + format), `pip` + `requirements.txt` | Single tool for style; no Poetry/uv ceremony. |

## Resilience model

Two stacked layers of fault tolerance around every LLM call:

```
┌───────────────────────────────────────────────────────────────────┐
│   Outer:  fallback chain over models                              │
│           Gemini → OpenRouter A → OpenRouter B → ...              │
│   Inner:  tenacity retries (3 attempts, 2s/4s/8s backoff)         │
│           on RateLimitError / Timeout / APIConnectionError        │
└───────────────────────────────────────────────────────────────────┘
```

- A model failure (any classified or unknown error) advances the fallback chain.
- The model that *actually answered* is recorded in the audit row (not just the primary).
- All retries exhausted across all models → `502` with a typed error envelope.

Plus a Postgres-backed question cache: identical normalised role + model → cached 24h, no LLM call.

## API contract

### Endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/healthz` | Liveness probe; reports DB connectivity. No rate limit. |
| `POST` | `/api/v1/generate` | Generate three questions. Rate-limited per IP + global daily cap. |

### Request

```json
POST /api/v1/generate
Content-Type: application/json

{ "role": "Senior Backend Engineer" }
```

`role` is `min_length=1, max_length=200, strip_whitespace=True`.

### Successful response

```json
{
  "data": {
    "questions": [
      { "category": "...", "question": "...", "rationale": "..." },
      { "category": "...", "question": "...", "rationale": "..." },
      { "category": "...", "question": "...", "rationale": "..." }
    ]
  },
  "meta": null
}
```

Always exactly three questions. Schema enforced via instructor's `response_model`.

### Error response (any non-2xx)

```json
{
  "error": {
    "message": "user-facing string",
    "code": "STABLE_TAG",
    "error_code": null,
    "severity": "error" | "warning",
    "retryable": true | false,
    "reference_id": "9f3c…",
    "details": null
  }
}
```

`reference_id` is a fresh UUID per error and is logged at the same severity, so support reports correlate to log lines. `details` carries per-field info on validation errors.

### Error code reference

| Source | HTTP | `code` | `retryable` |
|---|---|---|---|
| Pydantic request validation | 422 | `VALIDATION_ERROR` | `false` |
| Per-IP rate limit (min or day) exceeded | 429 | `RATE_LIMITED` | `true` |
| Global daily cap reached | 503 | `SERVICE_AT_CAPACITY` | `false` |
| All models in chain exhausted retries | 502 | `UPSTREAM_ERROR` | `true` |
| All models produced malformed output | 502 | `BAD_SHAPE` | `true` |
| DB unreachable on critical path | 503 | `DB_UNAVAILABLE` | `true` |
| Service misconfigured | 500 | `CONFIG_ERROR` | `false` |
| Unhandled exception | 500 | `INTERNAL_ERROR` | `false` |

## Project layout

```
src/app/
├── main.py                      # FastAPI factory, lifespan (DatabaseManager + LLMClient on app.state)
│
├── core/                        # Cross-cutting; no business logic. Leaf module.
│   ├── config.py                # Pydantic-Settings; required + optional env vars
│   ├── exceptions.py            # Domain error hierarchy with HTTP codes & severities
│   ├── error_handlers.py        # FastAPI exception handlers → ErrorResponse envelope
│   ├── rate_limit.py            # Multi-window FastAPI dependency
│   └── deps.py                  # SessionDep / LLMClientDep / QuestionServiceDep
│
├── routers/                     # HTTP layer; thin
│   ├── health.py                # GET /healthz
│   └── v1/                      # Versioned API
│       └── generate.py          # POST /api/v1/generate
│
├── services/                    # Use case orchestration
│   └── question_service.py      # Cache → cap check → LLM → counter → audit
│
├── repositories/                # Postgres-backed persistence per table
│   ├── audit_repository.py      # Writes to `generations`
│   ├── cache_repository.py      # Reads/writes `question_cache` (normalize_role lives here)
│   └── rate_limit_repository.py # Three windows: minute, day, global
│
├── infrastructure/              # External integrations; the only place these libs are imported
│   ├── database.py              # DatabaseManager: engine + sessionmaker + lifecycle
│   ├── llm.py                   # LLMClient: litellm + instructor + tenacity + fallback chain
│   └── prompts.py               # System + user prompt templates
│
├── models/                      # Domain types and ORM tables
│   ├── question.py              # Question (frozen dataclass) — domain shape
│   └── db/                      # SQLAlchemy ORM models — owned by persistence layer
│       ├── base.py
│       ├── generation.py        # Audit row
│       ├── question_cache.py    # 24h LLM-response cache
│       ├── rate_limit_bucket.py # Per-IP per-minute counter
│       ├── rate_limit_daily.py  # Per-IP per-day counter
│       └── global_daily_count.py# Service-wide per-day counter
│
└── schemas/                     # All Pydantic models live here
    ├── generate.py              # Wire DTOs for /api/v1/generate
    ├── health.py                # Wire DTO for /healthz
    ├── response.py              # Generic ApiResponse[T] + ErrorResponse envelope
    └── llm.py                   # LLMQuestion / LLMQuestions — instructor binds against this
```

### Dependency rule (enforced by code review)

```
routers   →  services  →  repositories ──┐
   ↓            ↓                          ├──→  asyncpg, SQLAlchemy
schemas      models      infrastructure ──┘     litellm, instructor, tenacity
   ↓            ↓               ↓
              core            core
```

- `routers` never import litellm or SQLAlchemy.
- `repositories` never import FastAPI.
- `infrastructure` is the only ring that imports external SDKs.
- `schemas` and `models` don't import each other; translation happens at the router boundary.
- `core` is leaf — everything imports from it; it imports nothing else from `app/`.

## Database schema

| Table | Purpose | Key |
|---|---|---|
| `generations` | Audit log of every `/generate` attempt (success, cache hit, schema failure, upstream error). Stores model, latency, JSONB questions or error summary. | `id BIGSERIAL` |
| `question_cache` | TTL-bound cache of LLM responses keyed by `sha256(model + ":" + normalized_role)`. Includes `hit_count` for hot-role analysis. | `role_hash` |
| `rate_limit_buckets` | Per-IP per-minute counter (atomic UPSERT). | `(ip, route, window_start)` |
| `rate_limit_daily` | Per-IP per-day counter. | `(ip, route, day)` |
| `global_daily_count` | Service-wide per-day counter. Cache hits do **not** count against this. | `(day, route)` |

Migration `0001_initial.py` creates `generations` + `rate_limit_buckets`. Migration `0002_cache_and_rate_limit_v2.py` adds the three new tables and extends `generations.status` to allow `'cache_hit'`.

## Setup

### Local development

```bash
# 1. Clone and create venv
python3.11 -m venv .venv
source .venv/bin/activate

# 2. Install deps
pip install -r requirements.txt -r requirements-dev.txt
pip install -e . --no-deps                       # src-layout: register the `app` package

# 3. Local Postgres for dev (compose ships a healthchecked postgres:16 container)
docker compose up -d postgres

# 4. Configure env
cp .env.example .env                             # edit: LITELLM_MODEL, provider key,
                                                 #       DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME
                                                 # see Configuration section below

# 5. Apply migrations  (only needed for local dev — Docker handles this in production)
alembic upgrade head

# 6. Run
uvicorn app.main:app --reload                    # listens on :8000
```

Verify:

```bash
curl -s http://localhost:8000/healthz | jq
# → {"data": {"status": "ok", "db": "ok"}, "meta": null}

curl -s -X POST http://localhost:8000/api/v1/generate \
  -H "content-type: application/json" \
  -d '{"role": "Senior Backend Engineer"}' | jq
```

### Docker / production

The container is **self-deploying**: `entrypoint.sh` runs `alembic upgrade head` and then `exec`s the CMD (uvicorn). Pull the new image, start it, and the schema migrates itself before the first request lands.

```bash
docker build -t prompthire-backend:dev .
docker run --rm \
  -e LITELLM_MODEL=gemini/gemini-2.5-flash \
  -e GEMINI_API_KEY=... \
  -e DB_HOST=postgres -e DB_PORT=5432 \
  -e DB_USER=postgres -e DB_PASSWORD=... -e DB_NAME=prompthire \
  -p 8000:8000 \
  prompthire-backend:dev
```

What that one `docker run` does:

1. `entrypoint.sh` runs `alembic upgrade head` — idempotent; no-op if already at head.
2. Logs `[entrypoint] Migrations applied. Starting application: …`.
3. `exec`s into uvicorn so `SIGTERM` from `docker stop` reaches the app directly and shutdown is graceful.

If a migration fails, the container exits non-zero and the orchestrator's restart policy applies. **Trade-off worth knowing:** in a multi-instance deploy (e.g. multiple replicas behind a load balancer) every replica races to apply the same migration. Acceptable for single-instance Dokploy deploys; for multi-instance the right answer is a separate "migrate" job in the deploy pipeline. See `entrypoint.sh` for the full script.

**Operator escape hatches** (when you need to bypass the auto-migrate or roll back):

```bash
# drop into a shell, no migrations
docker run --rm -it --entrypoint /bin/sh prompthire-backend:dev

# roll back one migration without starting the app
docker run --rm --entrypoint alembic prompthire-backend:dev downgrade -1

# the entrypoint still runs first, but CMD is overridable for one-off ops
docker run --rm prompthire-backend:dev alembic current
```

## Configuration

All config is environment-driven via `pydantic-settings`. See `.env.example` for the full list with comments. The notable ones:

| Var | Required | Default | Notes |
|---|---|---|---|
| `LITELLM_MODEL` | yes | — | Primary model id (e.g. `gemini/gemini-2.5-flash`). |
| `LITELLM_FALLBACK_MODELS` | no | `""` | Comma-separated chain. Tried in order if primary exhausts retries. |
| `<PROVIDER>_API_KEY` | yes | — | E.g. `GEMINI_API_KEY`, `OPENROUTER_API_KEY`. Loaded by `python-dotenv` into `os.environ` at startup so litellm picks them up. |
| `DB_HOST` | yes | — | Postgres hostname (e.g. `localhost`, or service name in a Docker network). |
| `DB_PORT` | no | `5432` | Postgres TCP port. |
| `DB_USER` | yes | — | Postgres username. |
| `DB_PASSWORD` | yes | — | Postgres password. URL-encoded automatically when the connection string is composed, so special characters are safe. |
| `DB_NAME` | yes | — | Postgres database name. |
| `RATE_LIMIT_PER_MIN` | no | `5` | Per-IP per-minute cap. |
| `RATE_LIMIT_PER_DAY` | no | `20` | Per-IP per-day cap. |
| `GLOBAL_DAILY_CAP` | no | `200` | Service-wide cap on LLM calls per UTC day (cache hits exempt). |
| `CACHE_ENABLED` | no | `true` | Operator kill-switch for the question cache. |
| `CACHE_TTL_HOURS` | no | `24` | Cache entry lifetime. |
| `LITELLM_TIMEOUT_SECONDS` | no | `30` | Hard ceiling on a single LLM call. |
| `CORS_ORIGINS` | no | `""` | Comma-separated allowlist; empty = same-origin only. |
| `TRUST_FORWARDED_FOR` | no | `false` | Trust the first hop of `X-Forwarded-For` for rate-limit IP keying. Enable only behind a known proxy. |
| `LOG_LEVEL` | no | `INFO` | Standard Python logging level. |

### Multi-model fallback example

```bash
LITELLM_MODEL=gemini/gemini-2.5-flash
LITELLM_FALLBACK_MODELS=openrouter/poolside/laguna-m.1:free,openrouter/meta-llama/llama-3.1-8b-instruct:free
GEMINI_API_KEY=...
OPENROUTER_API_KEY=...
```

When Gemini's free tier 429s, the request transparently rolls over to the first OpenRouter model; if that also fails, it tries the second. The audit row records which model actually answered.

## Engineering decisions worth a closer look

If a reviewer is scrolling, these are the spots that demonstrate non-obvious thinking — start here:

- **`src/app/infrastructure/llm.py`** — multi-model fallback wrapping per-model tenacity retries; `_root_cause` walks the full `__cause__`/`__context__` chain because instructor wraps provider errors at varying depths.
- **`src/app/services/question_service.py`** — fixed-order pipeline (cache → cap → LLM → counter → cache write → audit) with explicit non-fatal failure modes documented inline.
- **`src/app/core/exceptions.py`** — domain errors carry their own `code`/`http_status`/`severity`/`retryable`, so the wire envelope is a near-mechanical translation in `error_handlers.py`.
- **`src/app/repositories/cache_repository.py`** — `normalize_role` order matters (NFKC → strip → lowercase → collapse whitespace → strip control chars); `sha256(model + ":" + normalized_role)` so model swaps invalidate cache automatically.
- **`src/app/repositories/rate_limit_repository.py`** — three atomic UPSERT counters (minute / day / global) with `RETURNING count` so we never read-then-write.
- **`src/app/schemas/response.py`** — single `ApiResponse[T]` + `ErrorResponse` envelope used by every route; consistent shape regardless of payload.
- **`src/app/main.py`** — composition root; only place where `DatabaseManager` and `LLMClient` are constructed; loads `.env` into `os.environ` so litellm sees provider keys.
- **`entrypoint.sh` + `Dockerfile`** — self-deploying container: migrations run on container start before uvicorn. `exec "$@"` so `SIGTERM` reaches the app directly. The CMD remains overridable for operator one-offs.

## Frontend integration

The [frontend](../prompthire-frontend) `lib/generator.ts` posts to `/api/v1/generate` and unwraps the `ApiResponse[T]` / `ErrorResponse` envelope into a typed `GeneratorError` (with `severity` / `retryable` / `referenceId`). In dev, Vite proxies `/api/*` to `http://localhost:8000`. Same-origin in prod via nginx.

## Things deliberately *not* in this version

These were considered and deferred — listed here so a reviewer knows they were thought about, not missed:

- **Tests.** No pytest harness in this revision. Manual smoke verification via TestClient/curl. Adding a behaviour-driven test pass is a tracked next step.
- **Auth.** Public endpoint by design; per-IP + global rate limits + budget cap are the only guards.
- **Sliding-window rate limit.** Fixed-window is sufficient for the threat model and single-instance deploy.
- **Token / cost tracking.** Free-tier providers; no dollars to count. The audit row carries enough to retrofit later.
- **Observability beyond logs.** Stdlib logging with structured-ish messages; metrics / traces / structlog deferred.
- **Streaming responses.** Three-question payload is small; streaming would be theatre.
- **Distributed cache / rate-limit.** Postgres scales horizontally; Redis is the obvious upgrade path if traffic warrants.

## License

For demonstration / portfolio use.
