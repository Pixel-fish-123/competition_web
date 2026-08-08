# Repository Instructions

## Project Shape
- This is a FastAPI + SQLAlchemy + SQLite backend with a Vue 3 + Vite + TypeScript frontend.
- Development uses two processes: backend on `:8000` and Vite on `:5173`; production serves the built frontend from `frontend/dist` through FastAPI.
- There is no root package manager, CI workflow, Alembic setup, or frontend unit-test suite.
- Backend entrypoint: `backend/app/main.py` (`app.main:app`). Frontend entrypoint: `frontend/src/main.ts`.

## Commands
- One-time/local Windows startup from the repository root: `powershell -ExecutionPolicy Bypass -File start.ps1`. It creates `backend/.venv`, installs missing dependencies, skips seed data by default, checks that occupied port 8000 is this backend, and starts both services. Add `-Seed` only for a fresh demo database.
- Backend setup/run from `backend/`: `python -m venv .venv`, `.venv\Scripts\python.exe -m pip install -r requirements.txt`, `.venv\Scripts\python.exe seed.py`, then `.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`.
- Backend tests from `backend/`: `.venv\Scripts\python.exe -m pytest tests -q`.
- Focused backend test: `.venv\Scripts\python.exe -m pytest tests\test_ws.py -q`; tournament-only tests live under `tests/test_tournaments/`.
- Tournament engine tests from `backend/`: `.venv\Scripts\python.exe -m pytest tests\test_tournaments -q`.
- Frontend setup/build from `frontend/`: `npm install`, then `npm run build`. `build` runs `vue-tsc -b` before `vite build`.
- Frontend dev server from `frontend/`: `npm run dev`; Vite proxies `/api` and WebSocket `/ws` to `http://127.0.0.1:8000` and fails instead of changing an occupied port (`strictPort`).
- Database reset from `backend/`: stop the backend first, then run `.venv\Scripts\python.exe reset_db.py --yes`.
- Deployment build/run: `docker compose -f deploy/docker-compose.yml up -d --build`; replace the compose file's placeholder `SECRET_KEY` first.

## Backend Traps
- There are no migrations. `Base.metadata.create_all()` and `_ensure_schema_upgrades()` in `backend/app/main.py` run during lifespan; schema changes must be handled there as well as in models.
- The development database is `backend/competition.db` and uses SQLite WAL. Stop the backend before `backend/reset_db.py --yes`, and treat `-wal`/`-shm` as part of the database when copying it.
- Tests set `DATABASE_URL` and `DB_PATH` to a PID-specific temporary database before importing the app; do not make tests depend on or modify `backend/competition.db`.
- The test `client` recreates tables per test and the autouse fixture resets rate-limit and login-lockout state. Preserve this isolation when adding fixtures.
- Backend API errors and docstrings use Chinese. Authentication uses an httpOnly `token` cookie with CSRF protection; authorization reads the database role rather than trusting JWT role claims.

## Frontend Traps
- `frontend/tsconfig.app.json` is strict (`noUnusedLocals` and related checks); `npm run build` is the required type/build verification.
- Do not use `as any` or `@ts-ignore`; fix the actual TypeScript types. Keep UI copy in Chinese and show API error details from `response.data.detail`.
- Production API routing and SPA deep-link fallback are provided by FastAPI only when `frontend/dist` exists; Vite's proxy is development-only.

## Navigation
- Backend route/permission/audit/rate-limit details: `backend/app/api/AGENTS.md`.
- Security, RBAC, CSRF, lockout, rate limiting, and WebSockets: `backend/app/core/AGENTS.md`.
- Match orchestration and scoring: `backend/app/services/AGENTS.md`.
- Swiss and single-elimination engines: `backend/app/tournaments/AGENTS.md`.
- Test fixtures and domain-specific test patterns: `backend/tests/AGENTS.md`.
- Frontend-wide rules and page ownership: `frontend/AGENTS.md` and `frontend/src/views/AGENTS.md`.
- Verified project/deployment context: `docs/README.md`, `docs/backend.md`, `docs/frontend.md`, and `docs/部署手册.md`.

## Development Data
- `backend/seed.py` is idempotent and creates demo accounts (`admin/admin123`, `referee/referee123`, `player1`-`player8` with `player123`); never expose these credentials in production.
