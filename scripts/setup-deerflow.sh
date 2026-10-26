#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."

if ! command -v python3.12 >/dev/null 2>&1; then
  echo "DeerFlow 2.1 requires Python 3.12. Install it before running this setup."
  exit 1
fi

python3.12 -m venv runtime/.venv
if command -v uv >/dev/null 2>&1; then
  uv pip install --python runtime/.venv/bin/python \
    vendor/deerflow/deerflow-extension-api-e9074b7.tar.gz \
    vendor/deerflow/deerflow-harness-e9074b7.tar.gz \
    -r requirements.txt \
    'langchain-ollama>=1.0,<2.0'
else
  runtime/.venv/bin/python -m pip install --upgrade pip
  runtime/.venv/bin/python -m pip install \
    vendor/deerflow/deerflow-extension-api-e9074b7.tar.gz \
    vendor/deerflow/deerflow-harness-e9074b7.tar.gz \
    -r requirements.txt \
    'langchain-ollama>=1.0,<2.0'
fi

runtime/.venv/bin/python -c 'from deerflow.client import DeerFlowClient; print("DeerFlow runtime ready")'
touch runtime/.ready
