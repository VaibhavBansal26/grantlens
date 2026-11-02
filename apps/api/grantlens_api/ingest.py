import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass

from .extensions import db
from .models import Opportunity
from .sources.base import NormalizedOpportunity

HASHED = (
    "number", "title", "abstract", "agency", "categories", "eligibility",
    "funding_instruments", "amount_min", "amount_max", "open_date", "close_date", "status",
)


@dataclass
class SyncStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0


def content_hash(item: NormalizedOpportunity) -> str:
    fields = {k: v for k, v in asdict(item).items() if k in HASHED}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, default=str).encode()).hexdigest()


def upsert(items: Iterable[NormalizedOpportunity]) -> SyncStats:
    stats = SyncStats()
    for item in items:
        digest = content_hash(item)
        row = Opportunity.query.filter_by(source=item.source, external_id=item.external_id).first()
        if row is None:
            db.session.add(Opportunity(content_hash=digest, **_columns(item)))
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


def _columns(item: NormalizedOpportunity) -> dict:
    cols = asdict(item)
    cols["raw_json"] = cols.pop("raw")
    return cols
