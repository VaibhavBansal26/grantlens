# Runbook

## First deploy

```bash
cp .env.prod.example .env.prod        # then fill it in; generate secrets with: python3 -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
scripts/smoke.sh https://your-site --limits
```

What starts: Postgres (pgvector), Redis (rate-limit counters only), the API, the web app, and Caddy. **Only Caddy is
published** (ports 80 and 443). It gets a TLS certificate for `SITE_ADDRESS` automatically and overwrites
`X-Forwarded-For`, which the API's per-address rate limits depend on (`TRUSTED_PROXY_HOPS=1`). If you put another
load balancer in front instead, it must **replace** that header with the client's address, not append to it; otherwise
anyone can dodge the limits by forging it. `scripts/smoke.sh --limits` checks exactly this.

The API applies database migrations on every start and then warms up (builds the keyword index, loads the embedding
model) **before** taking traffic, so it needs about 80 to 130 seconds to become healthy. That is expected.

The API refuses to start in production with a missing, placeholder or short (< 32 characters) `SECRET_KEY`.

## Routine jobs (schedule these, e.g. with cron)

| Job | Command (inside the API container) | Suggested schedule |
|---|---|---|
| Pull new opportunities | `flask sync --source grants_gov` (add `--statuses "closed\|archived"` for the archive) | daily |
| Embed new rows | `flask embed` | **after every sync** |
| Send alerts and reminders | `flask send-alerts` | daily |
| Back up the database | `scripts/backup.sh` | daily |

Run a job with: `docker compose -f docker-compose.prod.yml --env-file .env.prod exec api flask <command>`.

**Do not skip `flask embed`.** Rows without an embedding are invisible to semantic search (keyword search still
finds them). Once, after a large archive sync, semantic search could see only about a third of the corpus (24,960 of
80,960 rows) because the embedding step had not been re-run. Embedding the 58,698 missing rows took about 20 minutes on
a laptop CPU (the pace was 35 to 70 rows per second). Check coverage any time with:
`select count(*) - count(embedding) as without_embedding from opportunity;` (it should be 0 after a run).

## Backups

```bash
scripts/backup.sh [keep]                         # pg_dump to backups/, verified readable, keeps the newest 14
scripts/restore.sh backups/<file>.dump --yes     # DESTRUCTIVE: drops the current database first
```

Tested on the real data: a 1.3 GB database backed up in 93 s to a 433 MB file, restored in 92 s into an empty stack,
and the restored `award` table (75,784 rows) matched the original by row count and checksum; the vector index and the
migration version came back intact and the stack was healthy afterwards. Copy `backups/` off the machine; a backup on
the same disk is not a backup. Deleted accounts remain in older backups until those rotate out (see PRIVACY.md).

## Rotating secrets

- **`SECRET_KEY`**: changing it signs every user out and invalidates outstanding password-reset and unsubscribe links.
  Do it if it may have leaked.
- **`OPENAI_API_KEY`**: change it in `.env.prod` and recreate the API (`up -d api`).
- **`POSTGRES_PASSWORD`**: changing it in `.env.prod` alone does not change the password inside an existing database;
  change it in Postgres first (`ALTER USER`), then in `.env.prod`.

## Capacity (measured)

Measured with `scripts/loadtest.py` against this stack on a laptop (8 CPUs available to Docker, also running the
database, the load generator and a data sync), mixed traffic of 70% search, 20% detail pages, 10% deadlines, with
rate limits **off**. Results varied by up to about 30% from run to run, so treat them as ranges.

| Concurrent users | Throughput | Search p50 / p95 | Detail p95 | Deadlines p95 | Errors |
|---|---|---|---|---|---|
| 4 | 33 to 42 req/s | 110 to 150 ms / 220 to 280 ms | 24 to 30 ms | 62 to 77 ms | 0 |
| 16 | 30 to 46 req/s | 360 to 500 ms / 650 to 1,250 ms | 400 to 830 ms | 410 to 800 ms | 0 |
| 48 | ~30 req/s | ~1.6 s / ~3 s | ~2.7 s | ~4 s | 0 |

- **The original target (50 users with search p95 under 800 ms) is not met** on this hardware with this setup.
  Up to roughly 16 concurrent users it is met or close. Memory is steady at about 1.3 GB and nothing restarted.
- The API is CPU-bound. **Two workers measured best**; four workers were about twice as slow (about 20 req/s), and
  the cause was not found. To go beyond ~45 req/s, run more API replicas on separate machines or move query embedding
  and keyword search out of the web process; do not simply raise `WEB_CONCURRENCY`.
- First request after a start is still slower (a few seconds) while a freshly started database reads its pages from disk.

What the load test found and fixed along the way: keyword search originally built a separate in-memory index in every
worker (50 to 115 s each, over 1 GB) and scored queries in a Python loop: 0.2 req/s with a worst case of 115 s. It is
now a sparse matrix with scores identical to the original library (tested to 1e-9), warmed before a worker takes
traffic and refreshed in the background. `/deadlines` loaded large unused columns and had no index on `close_date`
(p95 894 ms to 62 ms after deferring the columns and adding the index).

## Logs and troubleshooting

API logs are JSON, one line per request: `request_id`, `method`, `path`, `status`, `ms`, `user` (numeric id). Query
strings, bodies and IP addresses are deliberately not logged. Every response carries `X-Request-ID`; an error shown to
a user includes it, so you can find the matching line (and, for 500s, the stack trace).

| Symptom | Likely cause |
|---|---|
| Everyone gets 429 on login | The proxy is not setting `X-Forwarded-For`, so all users look like one address. Run `scripts/smoke.sh --limits`. |
| 502 "AI service ..." from AI features | OpenAI error, quota or key. The message says which; failed calls are refunded from the daily allowance. |
| 503 "AI answers are not configured" | `OPENAI_API_KEY` is empty in `.env.prod`. |
| Semantic search misses recent grants | `flask embed` has not run since the last sync. |
| Page shows an error after ~30 s on slow AI requests | A proxy in front of Caddy has a short timeout; AI requests can take a minute. Caddy allows 180 s, the web app 150 s. |
| API unhealthy for ~2 minutes after start | Normal: migrations, then warm-up. |

## Not done yet

Error tracking (Sentry) and tracing (OpenTelemetry) need an external account and are not wired in; metrics/alerting;
email verification; automatic data-retention limits; moving PDF parsing and AI calls into background jobs with
progress (they are synchronous, so a slow request holds a worker thread); off-site backup automation; a staging
environment and a deploy pipeline (CI builds the images but nothing publishes or deploys them).
