from sqlalchemy import func

from .extensions import db
from .models import Award, Opportunity

OPP_FIELDS = ("abstract", "agency", "close_date", "amount_max", "eligibility", "categories")
AWARD_FIELDS = ("abstract", "agency", "organization", "amount", "investigators", "end_date")


def _missing(col):
    return func.sum(db.case((col.is_(None), 1), else_=0))


def report() -> list[str]:
    lines: list[str] = []
    for model, fields in ((Opportunity, OPP_FIELDS), (Award, AWARD_FIELDS)):
        sources = db.session.query(model.source, func.count()).group_by(model.source).all()
        for source, total in sources:
            lines.append(f"{model.__tablename__}/{source}: {total} rows")
            q = db.session.query(*[_missing(getattr(model, f)) for f in fields])
            row = q.filter(model.source == source).one()
            for field, miss in zip(fields, row):
                lines.append(f"  {field:<14} null {100 * (miss or 0) / total:5.1f}%")
            dupes = (
                db.session.query(func.lower(model.title), func.count())
                .filter(model.source == source)
                .group_by(func.lower(model.title))
                .having(func.count() > 1)
                .count()
            )
            lines.append(f"  duplicate titles: {dupes}")
    return lines
