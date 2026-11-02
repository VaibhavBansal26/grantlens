import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass

from .extensions import db
from .models import Award, Opportunity
from .sources.base import NormalizedAward, NormalizedOpportunity

HASHED = (
    "number", "title", "abstract", "agency", "categories", "eligibility",
    "funding_instruments", "amount_min", "amount_max", "open_date", "close_date", "status",
    "project_number", "organization", "investigators", "keywords", "amount", "fiscal_year",
    "start_date", "end_date",
)
BATCH = 500
MODELS = {NormalizedOpportunity: Opportunity, NormalizedAward: Award}


@dataclass
class SyncStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0


def content_hash(item: NormalizedOpportunity | NormalizedAward) -> str:
    fields = {k: v for k, v in asdict(item).items() if k in HASHED}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, default=str).encode()).hexdigest()


def upsert(items: Iterable[NormalizedOpportunity | NormalizedAward]) -> SyncStats:
    stats = SyncStats()
    for n, item in enumerate(items, 1):
        if n % BATCH == 0:
            db.session.commit()
        digest = content_hash(item)
        model = MODELS[type(item)]
        row = model.query.filter_by(source=item.source, external_id=item.external_id).first()
        if row is None:
            db.session.add(model(content_hash=digest, **_columns(item)))
            stats.inserted += 1
        elif row.content_hash != digest:
            for key, value in _columns(item).items():
                setattr(row, key, value)
            row.content_hash = digest
            stats.updated += 1
        else:
            stats.unchanged += 1
    db.session.commit()
    return stats


def _columns(item: NormalizedOpportunity | NormalizedAward) -> dict:
    cols = asdict(item)
    cols["raw_json"] = cols.pop("raw")
    return cols
