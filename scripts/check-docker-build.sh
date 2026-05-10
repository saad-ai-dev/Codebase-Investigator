#!/usr/bin/env sh
set -eu

if ! command -v docker >/dev/null 2>&1; then
  echo "Skipping Docker build check because docker is not installed."
  exit 0
fi

docker build -t codebase-investigator:precommit .
