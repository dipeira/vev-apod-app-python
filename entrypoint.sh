#!/bin/bash
set -e

# Initialize DB and create admin user on every startup (idempotent).
python init_db.py

# Start gunicorn.
# - 1 worker: pipeline runs in a background thread so the worker stays free for HTTP.
#   Using 2+ workers would split _state (in-memory) across processes, breaking the
#   progress bar (polls hitting a different worker always see progress=0).
# - timeout 1200s: keeps connections alive for very long LibreOffice conversions
exec gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 1 \
    --timeout 1200 \
    run:app
