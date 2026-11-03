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
| Delete expired documents and old counters | `flask retention` (`--dry-run` to count first) | daily |
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

## Background jobs

Building a literature review takes 15 to 60 seconds, so it does not run inside the web request. `POST /reviews`
validates, takes one AI request from the user's daily allowance and queues a row in the `job` table; the browser polls
`GET /reviews/jobs/<id>`. A job that fails gives the allowance back, and a job a crashed worker left "running" is failed
and refunded after 15 minutes. At most two reviews per user are in flight.

`JOBS_MODE` decides who runs the queue: `worker` (production: the `worker` service in `docker-compose.prod.yml`, which
also keeps this work off the processes that serve search), `thread` (development default: a thread in the web process,
nothing extra to start) or `sync` (tests). With `worker`, jobs stay queued until the worker is up, so check
`docker compose logs worker` if reviews sit at "waiting to start". Document Q&A and the fit check take a few seconds and
stay synchronous.

## Deploying

CI (`ci.yml`) must pass first. Then `release.yml` publishes `grantlens-api` and `grantlens-web` to GitHub's container
registry (`ghcr.io/<owner>/...`, tagged with the commit and `latest`) and deploys: a push to `master` goes to the
`staging` environment, a tag like `v1.2.0` goes to `production`. Add required reviewers to `production`
(Settings, Environments) to make every production deploy wait for an approval.

One-time server setup (any Linux host with Docker):

1. Clone the repository to the path you will give as `DEPLOY_PATH`; copy `.env.prod.example` to `.env.prod` and fill it
   in (including `GHCR_OWNER`, lower-case).
2. If the image packages are private, run `docker login ghcr.io` once with a token that can read packages.
3. Create a deploy-only SSH key and add the public half to the server. In each GitHub environment add the secrets
   `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_PATH`, `DEPLOY_SSH_KEY` (the private key) and `DEPLOY_KNOWN_HOSTS`
   (`ssh-keyscan <host>`). Without `DEPLOY_HOST` the deploy job only reports that no server is configured.
4. First deploy by hand: `BACKUP=0 scripts/deploy.sh <git sha or tag>`.

`scripts/deploy.sh <ref>` checks out the ref, takes a database backup, pulls the images, starts them, waits for
`scripts/smoke.sh` to pass and records the version. If the new version does not come up healthy it puts the previous one
back and exits non-zero. Migrations run when the new API starts and are additive, so rolling images back is safe; if a
migration itself went wrong, restore the backup that was just taken (`scripts/restore.sh`). `DRY_RUN=1` prints the
steps. The script is tested against stand-in tools (`sh scripts/test_deploy.sh`, part of CI). To roll back by hand:
`scripts/deploy.sh <older sha>`.

## Capacity (measured)

For a number you can trust, run the **capacity** workflow (Actions tab, or `gh workflow run capacity.yml -f users=50`).
It starts Postgres and the API on a clean GitHub runner, loads a synthetic corpus the size of the real one
(`scripts/seed_synthetic.py`: realistic keyword statistics and index size, meaningless relevance), runs the load test and
fails unless search p95 stays under the target with no errors. The laptop figures below predate that and were measured
on a machine that was also running a database, a browser and the load generator.

Measured with `scripts/loadtest.py` against this stack on a laptop (8 CPUs available to Docker, also running the
database, the load generator and a data sync), mixed traffic of 70% search, 20% detail pages, 10% deadlines, with
rate limits **off**. Results varied by up to about 30% from run to run, so treat them as ranges.

| Concurrent users | Throughput | Search p50 / p95 | Detail p95 | Deadlines p95 | Errors |
|---|---|---|---|---|---|
| 4 | 33 to 42 req/s | 110 to 150 ms / 220 to 280 ms | 24 to 30 ms | 62 to 77 ms | 0 |
| 16 | 30 to 46 req/s | 360 to 500 ms / 650 to 1,250 ms | 400 to 830 ms | 410 to 800 ms | 0 |
| 48 | ~30 req/s | ~1.6 s / ~3 s | ~2.7 s | ~4 s | 0 |

- **Clean-runner result (the `capacity` workflow, 2026-11-03):** 50 concurrent users, 60 seconds, 2 workers, 83,000
  synthetic opportunities, queries drawn from the corpus' own vocabulary: **201 req/s, search p50 241 ms / p95 464 ms**
  (target: p95 under 800 ms), detail p95 402 ms, deadlines p95 501 ms, 0 errors. **The target is met on that setup.**
  Caveats: the corpus is synthetic (vector-search and keyword-index cost are realistic, relevance is not), it is one
  60-second run on a shared 4-CPU runner, and an earlier run whose English queries matched nothing in the corpus gave p95 536 ms at
  173 req/s, so run-to-run variation is at least that large, and the test must use queries that exercise the keyword index.
- Before that, on the laptop, the target was **not** met: that setup ran the database, a browser and the load
  generator on 8 GB of memory that was already swapping, and every worker used 4 torch threads. The code now limits torch
  to one thread per process and caches repeated query embeddings.
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
| Paper search, "find grants for my work" or the review builder say OpenAlex's budget is used up | Anonymous OpenAlex use shares a small daily budget per IP address (resets at midnight UTC). Get a free key and set `OPENALEX_API_KEY`. |
| Semantic search misses recent grants | `flask embed` has not run since the last sync. |
| Page shows an error after ~30 s on slow AI requests | A proxy in front of Caddy has a short timeout; AI requests can take a minute. Caddy allows 180 s, the web app 150 s. |
| API unhealthy for ~2 minutes after start | Normal: migrations, then warm-up. |

## Not done yet

Distributed tracing (OpenTelemetry) and metrics/alerting; changing an account's email address (so verification is only
on sign-up); off-site backup automation; background jobs for PDF upload and document Q&A (only review building is queued);
and an actual staging or production server: the pipeline deploys to whatever host you configure, but none exists yet.
