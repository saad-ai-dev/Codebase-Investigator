#!/usr/bin/env sh
set -eu

exec codebase-investigator \
  --session-root "${SESSION_ROOT:-/app/.investigator/sessions}" \
  --model "${OPENAI_MODEL:-gpt-5.5}" \
  --audit-model "${OPENAI_AUDIT_MODEL:-gpt-5.4-mini}" \
  serve --host 0.0.0.0 --port 8000
