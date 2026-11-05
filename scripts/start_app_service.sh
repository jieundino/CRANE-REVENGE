#!/usr/bin/env bash
set -euo pipefail

# CRANE REVENGE — Azure App Service (Linux) 통합 시작 스크립트
# - 외부 진입 포트($PORT, 기본 8000): Streamlit 프론트엔드 (0.0.0.0 바인딩)
# - 내부 API 포트($BACKEND_PORT, 기본 8001): FastAPI 백엔드 (127.0.0.1 바인딩)
# - 두 프로세스 중 하나라도 비정상 종료되면(wait -n) 나머지 프로세스를 정리하고 종료하여
#   Azure App Service가 컨테이너 상태를 즉시 감지하고 재시작할 수 있도록 구성함.

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

export PYTHONPATH="${APP_DIR}:${PYTHONPATH:-}"

FRONTEND_PORT="${PORT:-${WEBSITES_PORT:-8000}}"
BACKEND_PORT="${BACKEND_PORT:-8001}"

# 만약 FRONTEND_PORT와 BACKEND_PORT가 같으면 충돌 방지를 위해 BACKEND_PORT를 8001(또는 8002)로 분리
if [ "$FRONTEND_PORT" = "$BACKEND_PORT" ]; then
    if [ "$FRONTEND_PORT" = "8001" ]; then
        BACKEND_PORT="8002"
    else
        BACKEND_PORT="8001"
    fi
fi

export API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:${BACKEND_PORT}}"

# Azure App Service Linux의 영속 디렉터리(/home)가 존재하면 /home/data 에 SQLite DB 저장
if [ -z "${DATABASE_PATH:-}" ]; then
    if [ -d "/home" ] && [ -w "/home" ]; then
        mkdir -p /home/data
        export DATABASE_PATH="/home/data/crane_revenge.db"
    else
        mkdir -p "${APP_DIR}/data"
        export DATABASE_PATH="${APP_DIR}/data/crane_revenge.db"
    fi
fi

echo "[CRANE REVENGE] Starting services..."
echo "[CRANE REVENGE] APP_DIR=${APP_DIR}"
echo "[CRANE REVENGE] FRONTEND_PORT=${FRONTEND_PORT}, BACKEND_PORT=${BACKEND_PORT}"
echo "[CRANE REVENGE] API_BASE_URL=${API_BASE_URL}"
echo "[CRANE REVENGE] DATABASE_PATH=${DATABASE_PATH}"

if [ -x "${APP_DIR}/.venv/bin/python" ]; then
    PY_CMD="${APP_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PY_CMD="python3"
else
    PY_CMD="python"
fi

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo "[CRANE REVENGE] Stopping processes..."
    if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# 1. FastAPI 백엔드 실행 (내부 루프백 전용)
"$PY_CMD" -m uvicorn backend.main:app --host 127.0.0.1 --port "$BACKEND_PORT" &
BACKEND_PID=$!

# FastAPI 헬스체크 대기 (최대 20초)
for _ in $(seq 1 20); do
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "[CRANE REVENGE] ERROR: FastAPI process terminated prematurely."
        exit 1
    fi
    if command -v curl >/dev/null 2>&1; then
        if curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1; then
            echo "[CRANE REVENGE] FastAPI is ready at 127.0.0.1:${BACKEND_PORT}"
            break
        fi
    fi
    sleep 1
done

# 2. Streamlit 프론트엔드 실행 (외부 공개 포트 바인딩)
"$PY_CMD" -m streamlit run frontend/app.py \
    --server.address 0.0.0.0 \
    --server.port "$FRONTEND_PORT" \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection false &
FRONTEND_PID=$!

# 두 프로세스 중 하나라도 종료되면 즉시 감지하여 컨테이너 재시작 유도
wait -n "$BACKEND_PID" "$FRONTEND_PID"
EXIT_CODE=$?
echo "[CRANE REVENGE] A process exited with code ${EXIT_CODE}. Exiting..."
exit "$EXIT_CODE"
