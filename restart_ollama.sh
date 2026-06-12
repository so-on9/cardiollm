#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="/home/ct/cardiollm/ollama_store"
LOG_FILE="$LOG_DIR/restart_ollama.log"
COMPOSE_DIR="/home/ct/cardiollm"

mkdir -p "$LOG_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

echo "[$(ts)] === restart_ollama.sh start ($*) ===" >> "$LOG_FILE"

cd "$COMPOSE_DIR"

MODE="${1:-fast}"   # fast | deep

if [[ "$MODE" == "deep" ]]; then
  echo "[$(ts)] deep refresh: docker compose up --force-recreate --no-deps ollama" >> "$LOG_FILE"
  /usr/bin/docker compose up -d --force-recreate --no-deps ollama >> "$LOG_FILE" 2>&1
else
  echo "[$(ts)] fast restart: docker compose restart -t 3 ollama" >> "$LOG_FILE"
  /usr/bin/docker compose restart -t 3 ollama >> "$LOG_FILE" 2>&1
fi

# 等待服務恢復。Ollama 不 publish 到 host port，改用 Docker healthcheck。
echo "[$(ts)] waiting for ollama container health ..." >> "$LOG_FILE"
if timeout 60 bash -c 'until [[ "$(/usr/bin/docker inspect -f "{{.State.Health.Status}}" ollama 2>/dev/null)" == "healthy" ]]; do sleep 1; done'; then
  echo "[$(ts)] ollama is healthy" >> "$LOG_FILE"
else
  echo "[$(ts)] ERROR: ollama not healthy within 60s" >> "$LOG_FILE"
fi

echo "[$(ts)] === restart_ollama.sh end ===" >> "$LOG_FILE"
