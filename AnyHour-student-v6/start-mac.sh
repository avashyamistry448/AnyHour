#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [[ -f canvas.env ]]; then
  set -a
  source ./canvas.env
  set +a
fi
if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
source .venv/bin/activate
python -m pip install -r requirements.txt
printf '\nOpen http://127.0.0.1:%s in Safari or Chrome. Keep this terminal open.\n' "${PORT:-8000}"
python server.py
