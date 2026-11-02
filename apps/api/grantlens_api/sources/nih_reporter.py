from collections.abc import Iterator
from datetime import date, datetime

import httpx

from .base import NormalizedAward

API = "https://api.reporter.nih.gov/v2/projects/search"
PAGE = 500
FIELDS = [
    "ApplId", "ProjectNum", "ProjectTitle", "AbstractText", "Organization", "AgencyIcAdmin",
    "AwardAmount", "ProjectStartDate", "ProjectEndDate", "PrincipalInvestigators", "Terms",
    "FiscalYear", "ProjectDetailUrl",
]


def _date(value: str | None) -> date | None:
    try:
        return datetime.fromisoformat(value).date() if value else None
    except ValueError:
        return None


def normalize(r: dict) -> NormalizedAward:
    terms = [t for t in (r.get("terms") or "").replace("><", "|").strip("<>").split("|") if t]
    pis = [p.get("full_name") for p in r.get("principal_investigators") or [] if p.get("full_name")]
    return NormalizedAward(
        source="nih_reporter",
        external_id=str(r["appl_id"]),
        project_number=r.get("project_num"),
        title=(r.get("project_title") or "").strip(),
        abstract=(r.get("abstract_text") or "").strip() or None,
        agency=(r.get("agency_ic_admin") or {}).get("name"),
        organization=(r.get("organization") or {}).get("org_name"),
        investigators=pis,
        keywords=sorted(set(terms)),
        amount=r.get("award_amount"),
        fiscal_year=r.get("fiscal_year"),
        start_date=_date(r.get("project_start_date")),
        end_date=_date(r.get("project_end_date")),
        url=r.get("project_detail_url"),
        raw=r,
    )


class NihReporterSource:
    name = "nih_reporter"

    def __init__(self, fiscal_years: list[int] | None = None, text: str | None = None):
        self.fiscal_years = fiscal_years or [datetime.now().year - 1]
        self.text = text

    def fetch(self, limit: int | None = None) -> Iterator[NormalizedAward]:
        criteria: dict = {"fiscal_years": self.fiscal_years}
        if self.text:
            criteria["advanced_text_search"] = {
                "operator": "and", "search_field": "all", "search_text": self.text,
            }
        offset, seen = 0, 0
        with httpx.Client(timeout=60) as client:
            while offset < 14999:  # RePORTER caps paging at 15k; shard by year/text beyond that
                size = PAGE if limit is None else min(PAGE, limit - seen)
                body = {"criteria": criteria, "offset": offset, "limit": size,
                        "include_fields": FIELDS}
                data = client.post(API, json=body).raise_for_status().json()
                results = data.get("results") or []
                for r in results:
                    yield normalize(r)
                    seen += 1
                offset += len(results)
                if not results or offset >= data["meta"]["total"] or (limit and seen >= limit):
                    return
