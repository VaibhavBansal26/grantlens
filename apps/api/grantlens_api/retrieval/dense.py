from sqlalchemy import select, text

from ..extensions import db
from ..models import Opportunity
from .embedder import embed_query


def search(query: str, k: int, conditions: list) -> list[int]:
    # HNSW applies WHERE filters after the index scan; keep scanning until k rows survive.
    db.session.execute(text("SET LOCAL hnsw.ef_search = 200"))
    db.session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    stmt = (
        select(Opportunity.id)
        .where(Opportunity.embedding.is_not(None), *conditions)
        .order_by(Opportunity.embedding.cosine_distance(embed_query(query)))
        .limit(k)
    )
    return list(db.session.scalars(stmt))
