# GrantLens v2

Hybrid semantic search over research funding + an academic research assistant.
Stack: Flask API, Postgres/pgvector, Redis, Next.js. See the roadmap (phases 0-7).

**[Watch the 8-minute demo](demo/grantlens_demo.mp4)**: every feature, the stack and models, and the measured results, including what didn't work.

```bash
cp .env.example .env
make up      # api :5000, web :3000
make test
```
