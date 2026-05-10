#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
RUN_DIR="${RUN_DIR:-$ROOT_DIR/.run}"
LOG_DIR="${LOG_DIR:-$ROOT_DIR/logs}"
PID_FILE="${PID_FILE:-$RUN_DIR/codebase-investigator.pid}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/codebase-investigator.log}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-5600}"
SESSION_ROOT="${SESSION_ROOT:-$ROOT_DIR/.investigator/sessions}"
OPENAI_MODEL="${OPENAI_MODEL:-gpt-5.5}"
OPENAI_AUDIT_MODEL="${OPENAI_AUDIT_MODEL:-gpt-5.4-mini}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
ACTION="${1:-deploy}"

load_env() {
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
  fi
}

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "error: required command not found: $command_name" >&2
    exit 1
  fi
}

ensure_venv() {
  if [[ ! -d "$VENV_DIR" ]]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
  fi

  "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
  "$VENV_DIR/bin/pip" install -e "$ROOT_DIR"
}

stop_existing() {
  if [[ ! -f "$PID_FILE" ]]; then
    return 0
  fi

  local existing_pid
  existing_pid="$(cat "$PID_FILE")"

  if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" >/dev/null 2>&1; then
    kill "$existing_pid" >/dev/null 2>&1 || true

    for _ in $(seq 1 15); do
      if ! kill -0 "$existing_pid" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done

    if kill -0 "$existing_pid" >/dev/null 2>&1; then
      kill -9 "$existing_pid" >/dev/null 2>&1 || true
    fi
  fi

  rm -f "$PID_FILE"
}

start_app() {
  mkdir -p "$RUN_DIR" "$LOG_DIR" "$SESSION_ROOT"

  nohup "$VENV_DIR/bin/codebase-investigator" \
    --session-root "$SESSION_ROOT" \
    --model "$OPENAI_MODEL" \
    --audit-model "$OPENAI_AUDIT_MODEL" \
    serve --host "$HOST" --port "$PORT" >>"$LOG_FILE" 2>&1 &

  local new_pid="$!"
  echo "$new_pid" > "$PID_FILE"
  sleep 2

  if ! kill -0 "$new_pid" >/dev/null 2>&1; then
    echo "error: app failed to start. Check $LOG_FILE" >&2
    exit 1
  fi

  echo "Codebase Investigator is running in the background."
  echo "PID: $new_pid"
  echo "URL: http://$HOST:$PORT"
  echo "Log file: $LOG_FILE"
}

show_status() {
  if [[ -f "$PID_FILE" ]]; then
    local existing_pid
    existing_pid="$(cat "$PID_FILE")"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" >/dev/null 2>&1; then
      echo "running"
      echo "PID: $existing_pid"
      echo "URL: http://$HOST:$PORT"
      echo "Log file: $LOG_FILE"
      return 0
    fi
  fi

  echo "stopped"
}

main() {
  load_env
  require_command "$PYTHON_BIN"
  require_command git

  if [[ -z "${OPENAI_API_KEY:-}" || "${OPENAI_API_KEY}" == "replace_me" ]]; then
    echo "error: OPENAI_API_KEY is required. Set it in the shell or in $ENV_FILE" >&2
    exit 1
  fi

  case "$ACTION" in
    deploy|start|restart)
      ensure_venv
      stop_existing
      start_app
      ;;
    stop)
      stop_existing
      echo "Codebase Investigator stopped."
      ;;
    status)
      show_status
      ;;
    logs)
      mkdir -p "$LOG_DIR"
      touch "$LOG_FILE"
      tail -f "$LOG_FILE"
      ;;
    *)
      echo "usage: $0 [deploy|start|restart|stop|status|logs]" >&2
      exit 1
      ;;
  esac
}

main
