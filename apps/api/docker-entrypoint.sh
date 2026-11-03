#!/bin/sh
set -e
# Apply database migrations, then serve. With several API replicas, run migrations as a separate step instead.
flask --app grantlens_api:create_app db upgrade
# AI endpoints can run for a minute or more, so the worker timeout is generous. Threads share one copy of
# the embedding model per worker; --max-requests recycles workers to contain slow memory growth.
exec gunicorn "grantlens_api:create_app()" --config gunicorn.conf.py \
  --bind 0.0.0.0:5000 --worker-class gthread \
  --workers "${WEB_CONCURRENCY:-2}" --threads "${GUNICORN_THREADS:-4}" \
  --timeout 180 --graceful-timeout 30 --keep-alive 5 \
  --max-requests 2000 --max-requests-jitter 200 \
  --access-logfile /dev/null --error-logfile -
