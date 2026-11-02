from dataclasses import dataclass
from datetime import date

from ..models import Opportunity


@dataclass
class Filters:
    status: list[str] | None = None
    agency: str | None = None  # case-insensitive substring
    closes_after: date | None = None
    closes_before: date | None = None
    min_amount: int | None = None  # grant must allow at least this much
    max_amount: int | None = None  # grant floor must not exceed this
    include_no_deadline: bool = True  # rolling/forecast grants have no close date

    def conditions(self) -> list:
        c = []
        if self.status:
            c.append(Opportunity.status.in_(self.status))
        if self.agency:
            c.append(Opportunity.agency.ilike(f"%{self.agency}%"))
        if self.closes_after or self.closes_before:
            window = []
            if self.closes_after:
                window.append(Opportunity.close_date >= self.closes_after)
            if self.closes_before:
                window.append(Opportunity.close_date <= self.closes_before)
            cond = Opportunity.close_date.is_not(None)
            for w in window:
                cond = cond & w
            c.append(cond | Opportunity.close_date.is_(None) if self.include_no_deadline else cond)
        if self.min_amount is not None:
            c.append(Opportunity.amount_max >= self.min_amount)
        if self.max_amount is not None:
            c.append(Opportunity.amount_min <= self.max_amount)
        return c
