#!/usr/bin/env bash
# E2E-сценарии: настоящий диспетчер бота + эмулятор Telegram API + одноразовый Postgres.
#
# Рабочие контейнеры не затрагиваются: своя сеть без выхода наружу (--internal),
# своя база в tmpfs, код монтируется только для чтения, токен бота фальшивый.
# Аргументы передаются pytest: scripts/e2e.sh -k grades -x
set -euo pipefail
cd "$(dirname "$0")/.."

NET=stb-e2e-net
PG=stb-e2e-pg
IMAGE=${E2E_IMAGE:-study_tools_bot-bot}
PG_IMAGE=postgres:16.9-alpine  # та же версия и локаль, что в проде

cleanup() {
    docker rm -f "$PG" >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

docker network create --internal "$NET" >/dev/null
docker run -d --name "$PG" --network "$NET" -m 192m --tmpfs /var/lib/postgresql/data \
    -e POSTGRES_USER=study_bot -e POSTGRES_PASSWORD=e2e -e POSTGRES_DB=study_tools_e2e \
    "$PG_IMAGE" >/dev/null

# Во время initdb сервер слушает только unix-сокет; TCP отвечает уже после финального старта.
for _ in $(seq 1 60); do
    docker exec "$PG" pg_isready -h 127.0.0.1 -U study_bot -d study_tools_e2e -q && break
    sleep 0.5
done

docker run --rm --network "$NET" -m 384m -v "$PWD":/app:ro -w /app \
    -e E2E=1 -e PYTHONDONTWRITEBYTECODE=1 \
    -e BOT_TOKEN=4200000001:e2e-fake-token \
    -e POSTGRES_HOST="$PG" -e POSTGRES_PORT=5432 -e POSTGRES_USER=study_bot \
    -e POSTGRES_PASSWORD=e2e -e POSTGRES_DB=study_tools_e2e \
    -e ADMIN_USERNAME=e2e-admin -e ADMIN_PASSWORD=e2e-password -e ADMIN_SECRET_KEY=e2e-secret \
    "$IMAGE" python -m pytest -p no:cacheprovider tests/e2e "$@"
