"""Fill an EMPTY, migrated database with a synthetic corpus the size of the real one, for capacity tests in CI.

  cd apps/api && DATABASE_URL=... uv run python ../../scripts/seed_synthetic.py 83000

Titles and abstracts are drawn from a Zipf-shaped vocabulary (so the keyword index has realistic posting lists) and the
embeddings are random unit vectors (so the vector index has realistic size). Search results are meaningless, but the
work the database and the web process do per request is close to the real thing. Refuses to touch a database that
already has rows.
"""
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))  # so it runs from any directory

import numpy as np  # noqa: E402
from sqlalchemy import insert  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthetic_vocab import vocabulary, zipf_weights  # noqa: E402
from grantlens_api import create_app  # noqa: E402
from grantlens_api.extensions import db  # noqa: E402
from grantlens_api.models import EMBED_DIM, Opportunity  # noqa: E402

AGENCIES = ["HHS-NIH", "NSF", "DOE", "USDA", "NASA", "DOD", "ED", "EPA", "DOT", "DOC"]
STATUSES = ["posted"] * 6 + ["forecasted"] * 3 + ["closed"] * 40 + ["archived"] * 51  # about 9% open, like the real data


def main(total: int, batch: int = 1000) -> None:
    rng, np_rng = random.Random(1), np.random.default_rng(1)
    vocab = vocabulary(6000, rng)
    weights = zipf_weights(len(vocab))
    today = date.today()
    with create_app().app_context():
        if db.session.query(Opportunity).count():
            sys.exit("refusing to seed a database that already has opportunities")
        for start in range(0, total, batch):
            n = min(batch, total - start)
            vecs = np_rng.standard_normal((n, EMBED_DIM)).astype("float32")
            vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
            rows = []
            for k in range(n):
                i = start + k
                status = rng.choice(STATUSES)
                open_status = status in ("posted", "forecasted")
                rows.append({
                    "source": "synthetic", "external_id": str(i), "content_hash": f"s{i}",
                    "title": " ".join(rng.choices(vocab, weights, k=rng.randint(6, 14))).capitalize(),
                    "abstract": " ".join(rng.choices(vocab, weights, k=rng.randint(120, 260))),
                    "agency": rng.choice(AGENCIES), "status": status, "amount_max": rng.choice([None, 50000, 250000, 1000000]),
                    "close_date": today + timedelta(days=rng.randint(1, 120)) if open_status
                    else today - timedelta(days=rng.randint(1, 3000)),
                    "embedding": vecs[k].tolist(), "categories": [], "eligibility": [], "funding_instruments": [],
                })
            db.session.execute(insert(Opportunity), rows)
            db.session.commit()
            print(f"seeded {start + n}/{total}", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 83000)
