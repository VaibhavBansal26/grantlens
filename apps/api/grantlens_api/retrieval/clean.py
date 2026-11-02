import html
import re

_TAG = re.compile(r"<[^>]+>")
_BREAK = re.compile(r"</?(?:p|br|li|ul|ol|div|h[1-6])\b[^>]*>", re.IGNORECASE)


def clean_text(text: str | None) -> str:
    """Strip HTML tags and entities that some agencies leave in descriptions."""
    if not text:
        return ""
    text = _BREAK.sub("\n", text)
    text = html.unescape(_TAG.sub("", text)).replace("\xa0", " ")
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()
