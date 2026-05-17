# Study Tools Bot

## Stack And Entry Points
- Python 3.12 app: aiogram 3 bot + async SQLAlchemy + asyncpg + Alembic.
- Main runtime entrypoint is `python -m bot.main`.
- Run commands from the repo root. `config/settings.py` loads `.env` via `env_file=".env"`, so the working directory matters.

## Commands
- Install deps: `pip install -r requirements.txt`
- Run bot locally: `python -m bot.main`
- Run with containers: `docker compose up --build`
- Apply migrations: `alembic upgrade head`
- Create migration: `alembic revision --autogenerate -m "..."`
- Run tests: `docker compose exec -T bot python -m pytest tests/ -v`

## Database And Migrations
- `docker-compose.yml` exposes Postgres on host `127.0.0.1:5433`, but `.env.example` defaults to `POSTGRES_PORT=5432`. If the app runs on the host against the compose DB, set `POSTGRES_PORT=5433`.
- Inside Docker Compose, the bot talks to Postgres at host `postgres` and port `5432`.
- Alembic uses `alembic/` (`alembic.ini` sets `script_location = alembic`). `database/migrations/` is currently unused.
- `bot/main.py` still runs `Base.metadata.create_all()` on startup. Local runs can create tables without Alembic; do not assume schema changes are tracked unless you add a migration.
- Alembic gets its sync DB URL from `settings.database_url_sync`, while the app runtime uses the async URL.

## Wiring Gotchas
- New bot handlers must be included in `bot/handlers/__init__.py`; defining a router file is not enough.
- DB sessions reach handlers through `DatabaseMiddleware` as `session`. Middleware is only registered for `message` and `callback_query` in `bot/main.py`.
- Polling is limited to `allowed_updates=["message", "callback_query"]`. If you add other Telegram update types, update both `allowed_updates` and middleware registration.
- SQLAlchemy metadata is discovered by importing `database.models`. If you add a model, re-export/import it in `database/models/__init__.py` so startup and Alembic both see it.
- `bot/handlers/grades.py` uses module-level in-memory state (`_add_state`, `_pending_renames`), not persistent FSM storage. Those flows are single-process and reset on restart.
- Clicking a subject in `/grades` now opens the counter interface directly (subject card was removed). Preserve `_add_state`/`_render_grades_list`/`cnt:` callback flow intact when editing.
- Period selection was moved from `/grades` into `/settings`. `/grades`, `/gpa`, and `/summary` all use `bot.utils.periods.get_active_period()`, which prefers `user.active_period` and falls back to month-based auto-detection.
- `/gpa` was removed. Overall average is now shown at the bottom of `/grades`.
- Subjects are now sorted alphabetically. `Subject.sort_order` is no longer used in queries.

## Verification Reality
- E2E tests live in `tests/` and run via `docker compose exec -T bot python -m pytest tests/ -v` with SQLite in-memory + aiogram mocks.
- For manual smoke testing, `/start` creates the user row and seeds default subjects.
