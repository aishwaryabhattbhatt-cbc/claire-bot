# Clairebot (Local V1)

Step 1 scaffold: project skeleton + environment configuration.

## Stack (current)
- Python 3.11+
- FastAPI
- Env-based config via `pydantic-settings`

## Quick start
1. Create virtual env and install dependencies.
2. Copy env template:
   - `cp .env.example .env`
3. Start server:
   - `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
4. Open browser:
   - Navigate to `http://127.0.0.1:8000`
5. Check health:
   - `GET /health`

## Current structure
- `app/main.py` → FastAPI app bootstrap
- `app/core/config.py` → centralized environment config
- `data/uploads` and `data/processed` → local storage paths (created at startup)

## Next step
Step 2: implement `POST /review` file ingestion endpoint.
