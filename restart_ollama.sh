#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="/home/ct/cardiollm-k8s"
LOG_FILE="$LOG_DIR/ollama_refresh.log"
COMPOSE_DIR="/home/ct/cardiollm-k8s"

mkdir -p "$LOG_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

echo "[$(ts)] === restart_ollama.sh start ($*) ===" >> "$LOG_FILE"

cd "$COMPOSE_DIR"

# This K8s repo does not run a local Ollama container.
# It only checks the protected remote endpoint configured in .env.
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-}"
if [[ -z "$OLLAMA_BASE_URL" ]]; then
  echo "[$(ts)] ERROR: OLLAMA_BASE_URL is not set" >> "$LOG_FILE"
  exit 1
fi

echo "[$(ts)] checking remote Ollama: ${OLLAMA_BASE_URL}/api/tags" >> "$LOG_FILE"
if timeout 30 bash -c 'until curl -fsS "${OLLAMA_BASE_URL}/api/tags" >/dev/null; do sleep 1; done'; then
  echo "[$(ts)] remote ollama is reachable" >> "$LOG_FILE"
else
  echo "[$(ts)] ERROR: remote ollama not responding within 30s" >> "$LOG_FILE"
fi

echo "[$(ts)] === restart_ollama.sh end ===" >> "$LOG_FILE"
