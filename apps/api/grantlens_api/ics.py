from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from .models import Opportunity
from .retrieval.clean import clean_text


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", r"\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """RFC 5545: lines are limited to 75 octets; continuation lines start with a space."""
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode()) > (75 if not out else 74):
            out.append(cur)
            cur = ch
        else:
            cur += ch
    return out + [cur]


def vevent(o: Opportunity, stamp: str) -> list[str]:
    assert o.close_date
    return [
        "BEGIN:VEVENT",
        f"UID:opportunity-{o.id}@grantlens",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{o.close_date.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{(o.close_date + timedelta(days=1)).strftime('%Y%m%d')}",
        f"SUMMARY:{_escape('Deadline: ' + clean_text(o.title))}",
        f"DESCRIPTION:{_escape(' '.join(filter(None, [o.number, o.agency, o.url])))}",
        "END:VEVENT",
    ]


def calendar(opportunities: Iterable[Opportunity]) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//GrantLens//EN"]
    for o in opportunities:
        if o.close_date:
            lines += vevent(o, stamp)
    lines.append("END:VCALENDAR")
    folded = []
    for line in lines:
        parts = _fold(line)
        folded += [parts[0]] + [" " + p for p in parts[1:]]
    return "\r\n".join(folded) + "\r\n"
