# Study Tools Bot

## Stack And Entry Points
- Python 3.12 app: aiogram 3 bot + async SQLAlchemy + asyncpg + Alembic.
- Main runtime entrypoint is `python -m bot.main`.
- Run commands from the repo root. `config/settings.py` loads `.env` via `env_file=".env"`, so the working directory matters.

## Commands
- Install deps: `pip install -r requirements.txt`
- Run bot locally: `python -m bot.main`
- Run with containers: `docker compose up --build`
- Apply migrations: `alembic upgrade head` (the bot also applies them on every start)
- Create migration: `alembic revision --autogenerate -m "..."`
- Run tests: `docker compose exec -T bot python -m pytest tests/ -v`

## Database And Migrations
- `docker-compose.yml` exposes Postgres on host `127.0.0.1:5433`, but `.env.example` defaults to `POSTGRES_PORT=5432`. If the app runs on the host against the compose DB, set `POSTGRES_PORT=5433`.
- Inside Docker Compose, the bot talks to Postgres at host `postgres` and port `5432`.
- Alembic uses `alembic/` (`alembic.ini` sets `script_location = alembic`). `database/migrations/` is currently unused.
- Alembic is the single source of truth for the schema: `bot/main.py` runs `database.schema.apply_migrations()` on startup, there is no `create_all()`. Every model change needs a migration; `alembic check` compares models with migrations. Production predates Alembic and is stamped `20260430_000001`; the baseline `20260426_000000` only runs on new databases.
- Alembic gets its sync DB URL from `settings.database_url_sync`, while the app runtime uses the async URL.

## Wiring Gotchas
- New bot handlers must be included in `bot/handlers/__init__.py`; defining a router file is not enough.
- DB sessions reach handlers through `DatabaseMiddleware` as `session`. Middleware is only registered for `message` and `callback_query` in `bot/main.py`.
- Polling is limited to `allowed_updates=["message", "callback_query"]`. If you add other Telegram update types, update both `allowed_updates` and middleware registration.
- SQLAlchemy metadata is discovered by importing `database.models`. If you add a model, re-export/import it in `database/models/__init__.py` so startup and Alembic both see it.
- `bot/handlers/grades.py` uses module-level in-memory state (`_add_state`, `_pending_renames`), not persistent FSM storage. Those flows are single-process and reset on restart. `_add_state` is keyed by `(telegram_id, message_id)`: each open counter message has its own state. `_pending_renames` is dropped by `ResetPendingSubjectInput` as soon as the user sends a command or presses another button.
- Clicking a subject in `/grades` now opens the counter interface directly (subject card was removed). Preserve `_add_state`/`_render_grades_list`/`cnt:` callback flow intact when editing.
- Period selection lives only in `/settings`. `/grades` and `/summary` use `bot.utils.periods.get_active_period()`, which prefers `user.active_period` (only if `user.active_school_year` is the current school year) and falls back to month-based auto-detection. Period buttons in `/summary` only show another period's statistics and never change `active_period`.
- Periods repeat every school year, so a grade is identified by `(school_year, period)`: every query filtering `Grade.period` must also filter `Grade.school_year`. The school year is the calendar year it starts in (2026 = 2026/27), starts on September 1st, summer belongs to the ending year (`database/models/grade.py`). All calendar decisions go through `school_today()` (Europe/Moscow); tests freeze it there. `/grades` always works with the current school year; past years are viewed only in `/summary` (`summary_year:` buttons). Screens carry the year in callback_data (`subject:{id}:{year}:{period}`, `summary_period:{year}:{period}`); the older formats without a year mean the current school year.
- Message text is sent with `parse_mode=HTML`: escape any user input (subject names, first names) — use `subject_title()` / `html.escape`. Button texts and callback answers are plain text and must not be escaped.
- Re-rendering a screen with identical content is fine: `IgnoreMessageNotModified` (attached in `build_bot()`) turns Telegram's "message is not modified" into a no-op.
- `/gpa` was removed. Overall average is now shown at the bottom of `/grades`.
- Subjects are now sorted alphabetically. `Subject.sort_order` is no longer used in queries.

## Verification Reality
- Unit tests live in `tests/` and run via `docker compose exec -T bot python -m pytest tests/ -v` with SQLite in-memory + aiogram mocks.
- E2E scenarios live in `tests/e2e/` and run via `scripts/e2e.sh`: the real dispatcher (`build_dispatcher()`/`build_bot()`), a Telegram API emulator that enforces Bot API rules, and a throwaway Postgres migrated with Alembic. See `tests/e2e/README.md`.
- For manual smoke testing, `/start` creates the user row and seeds default subjects.
