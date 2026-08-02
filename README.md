# TaskFlow

A Django + Redis background job runner — enqueue work over HTTP, process it asynchronously with workers, and poll for status. Built from first principles (similar idea to Celery/RQ).

## Features

- **REST API** — create jobs and check status
- **Redis queues** — pending, processing, delayed (retry), dead-letter
- **Background workers** — separate processes pull jobs from Redis
- **Idempotency** — prevent duplicate jobs on retry/double-click (`Idempotency-Key` header)
- **Retries + exponential backoff** — transient failures retry automatically
- **Dead-letter queue** — permanently failed jobs isolated for inspection
- **Multiple workers** — scale horizontally with `run_workers.py` or Docker Compose
- **Load testing** — `load_test.py` script included
- **PDF example** — `POST /pdfs/prepare/` enqueues PDF generation

## Architecture

```
Client  →  POST /jobs/  →  Redis (job hash + queue:pending)
                              ↓
                         worker.py (BRPOPLPUSH)
                              ↓
Client  ←  GET /jobs/{id}/  ←  status: pending → processing → completed/failed
```

### Redis keys

| Key | Purpose |
|-----|---------|
| `job:{id}` | Job state hash |
| `queue:pending` | Jobs waiting to run |
| `queue:processing` | Jobs currently running |
| `queue:delayed` | Jobs waiting for retry (backoff) |
| `queue:dead` | Permanently failed jobs |
| `idempotency:{key}` | Idempotency key → job id mapping |

---

## Quick start (local)

### Prerequisites

- Python 3.12+
- PostgreSQL
- Redis (or Docker for Redis)

### 1. Clone and install

```bash
git clone https://github.com/gurumurugan123/TaskFlow.git
cd TaskFlow
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### 2. Environment

```bash
copy .env.example .env          # Windows
# Edit .env with your Postgres and Redis settings
```

### 3. Database

```bash
python manage.py migrate
```

### 4. Run services (3 terminals)

```bash
# Terminal 1 — API
python manage.py runserver

# Terminal 2 — workers (3 parallel)
python run_workers.py --count 3

# Terminal 3 — optional: Redis via Docker
docker run -d -p 6379:6379 --name redis-local redis:7-alpine
```

---

## API reference

### Create job

```http
POST /jobs/
Content-Type: application/json
Idempotency-Key: optional-unique-key

{
  "task": "demo",
  "data": {}
}
```

**Response:** `201` with `{ "id": "...", "status": "pending" }`

### Get job status

```http
GET /jobs/{id}/
```

### Prepare PDF (background)

```http
POST /pdfs/prepare/
Content-Type: application/json
Idempotency-Key: invoice-55-jan

{
  "title": "Invoice",
  "content": "Month: January"
}
```

**Response:** `202` with `job_id` and `status_url`

### Dead-letter queue

```http
GET /jobs/dead/
```

Lists permanently failed jobs.

---

## Supported tasks (worker)

| Task | Description |
|------|-------------|
| `demo` | Sleep 1s, return success |
| `prepare_pdf` | Generate PDF in `media/pdfs/` |
| `send_email` | Placeholder |
| `fail_demo` | Fails until `fail_until_attempt` (for testing retries) |

---

## Idempotency

Send header `Idempotency-Key` on enqueue endpoints to prevent duplicate jobs:

- **Same key + same body** → returns existing job (no new enqueue)
- **Same key + different body** → `409 Conflict`
- **Different key** → new job

The frontend/app generates the key — not the end user.

---

## Retries and dead-letter

- Failed jobs retry up to **3 times** with exponential backoff (2s → 4s → 8s)
- After max retries → moved to `queue:dead`
- Inspect via `GET /jobs/dead/`

---

## Load test

```bash
python load_test.py --count 50 --workers 10 --task demo
```

Requires `runserver` and workers running. Compare 1 worker vs 3 workers for throughput.

---

## Docker Compose (recommended for deploy)

Runs **PostgreSQL + Redis + Django API + Worker** in containers.

### Start all services

```bash
docker compose up --build
```

API: http://localhost:8000

### Run with 3 workers

```bash
docker compose up --build --scale worker=3
```

### Stop

```bash
docker compose down
```

### Services

| Service | Port | Role |
|---------|------|------|
| `web` | 8000 | Django API (Gunicorn) |
| `worker` | — | Background job processor |
| `redis` | 6379 | Queue + job state |
| `db` | 5432 | PostgreSQL |

---

## Deploy to a server

### Option A — Docker Compose (simplest)

1. Install Docker and Docker Compose on the server
2. Clone the repo
3. Set production env vars in `docker-compose.yml` or an `.env` file:
   - `SECRET_KEY` — strong random string
   - `DEBUG=False`
   - `ALLOWED_HOSTS=your-domain.com`
   - Strong `DB_PASSWORD`
4. Run:

```bash
docker compose up -d --build --scale worker=3
```

5. Put Nginx/Caddy in front for HTTPS (reverse proxy to port 8000)

### Option B — Manual deploy

1. Install Python 3.12, PostgreSQL, Redis on the server
2. Clone repo, create venv, `pip install -r requirements.txt`
3. Copy `.env.example` → `.env` and configure production values
4. `python manage.py migrate`
5. Run API with Gunicorn:

```bash
gunicorn taskflow.wsgi:application --bind 0.0.0.0:8000 --workers 2
```

6. Run workers (use systemd or supervisor):

```bash
python run_workers.py --count 3
```

7. Use Nginx as reverse proxy + SSL

---

## Project structure

```
TaskFlow/
├── taskflow/          # Django project settings & urls
├── jobs/              # Job app (models, views, serializers, queue)
├── worker.py          # Background worker (run separately)
├── run_workers.py     # Start N workers locally
├── load_test.py       # Load test script
├── redis_client.py    # Redis connection helper
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## Development checklist (completed)

- [x] Job model + migrations
- [x] Redis client + queues
- [x] POST /jobs + GET /jobs/{id}
- [x] Worker with BRPOPLPUSH
- [x] Idempotency
- [x] Retries + backoff
- [x] Dead-letter queue
- [x] Multiple workers
- [x] Load test
- [x] Docker Compose

---

## License

MIT (or your choice — update as needed)
