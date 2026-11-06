#!/bin/sh
# Apply database migrations, then start the web server.
# One worker + threads keeps the in-memory rate limiter exact. If you raise WEB_CONCURRENCY,
# point RATELIMIT_STORAGE_URI at Redis so limits are shared between workers.
set -e
python -m flask --app wsgi db upgrade
exec gunicorn wsgi:app --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-1} --threads ${WEB_THREADS:-8} --timeout 90 --access-logfile -
