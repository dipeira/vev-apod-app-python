#!/bin/bash
set -e

# Initialize DB and create admin user on every startup (idempotent).
python init_db.py

# Start gunicorn.
# - 2 workers: one free while the other runs a long LibreOffice conversion
# - timeout 600s: keeps request connections alive (pipeline runs in background thread)
exec gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 2 \
    --timeout 600 \
    run:app
