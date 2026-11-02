from sqlalchemy import select

from ..extensions import db
from ..models import Opportunity
from .embedder import embed_query


def search(query: str, k: int, conditions: list) -> list[int]:
    stmt = (
        select(Opportunity.id)
        .where(Opportunity.embedding.is_not(None), *conditions)
        .order_by(Opportunity.embedding.cosine_distance(embed_query(query)))
        .limit(k)
    )
    return list(db.session.scalars(stmt))
