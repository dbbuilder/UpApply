"""Parse client feedback from the text of an Upwork profile's work history (copied from the page)
into client_quote fact candidates. Pay figures (amounts, rates, hours) are dropped: facts never
carry compensation."""
import re
from dataclasses import dataclass, field
from typing import List, Optional

from app.schemas.fact import FactCandidate

SOURCE_TYPE = "client_feedback"  # in facts.CLIENT_SOURCE_TYPES: always goes to review

_RATING = re.compile(r"^Rating is (\d(?:\.\d)?) out of 5\.$")
_DATES = re.compile(r"^([A-Z][a-z]{2} \d{1,2}, \d{4}) - ([A-Z][a-z]{2} \d{1,2}, \d{4}|Present)$")
_QUOTE = re.compile(r'^["“](.+?)["”]\s*(See more)?$')
_PAY = re.compile(r"^\$[\d,]+(?:\.\d+)?(?:\s*/hr)?$|^\d+ hours?$|^Fixed price$")
_SCORE = re.compile(r"^\d(?:\.\d)?(?: of \d+ reviews?)?$")
_NOISE = re.compile(r"^(?:Completed jobs|In progress) \(\d+\)$|^Pagination$|^Current page \d+ of \d+$|^go to page\d+$")
_MONEY_IN_TEXT = re.compile(r"(?:USD|\$)\s?\d[\d,.]*\s*", re.IGNORECASE)


@dataclass
class Feedback:
    title: str
    rating: Optional[float] = None
    start: str = ""
    end: str = ""
    quote: str = ""
    truncated: bool = False
    endorsements: List[str] = field(default_factory=list)


def parse_work_history(text: str) -> List[Feedback]:
    """One Feedback per job: a title line is the line just before its first "Rating is ..." line."""
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not _NOISE.match(ln)]
    items: List[Feedback] = []
    current: Optional[Feedback] = None
    in_endorsements = False
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if _RATING.match(nxt) and not _RATING.match(line) and not _SCORE.match(line) and not _DATES.match(line):
            current = Feedback(title=line)
            items.append(current)
            in_endorsements = False
            continue
        if current is None:
            continue
        if m := _RATING.match(line):
            current.rating = current.rating or float(m.group(1))
        elif m := _DATES.match(line):
            current.start, current.end = current.start or m.group(1), current.end or m.group(2)
        elif m := _QUOTE.match(line):
            quote = m.group(1).strip()
            current.truncated = bool(m.group(2)) or quote.endswith("...")
            current.quote = quote.rstrip(".").rstrip() + "…" if current.truncated else quote
        elif line == "Endorsed by client":
            in_endorsements = True
        elif _PAY.match(line) or _SCORE.match(line):
            in_endorsements = False
        elif in_endorsements:
            current.endorsements.append(line)
    return items


def _clean_title(title: str) -> str:
    return re.sub(r"\s{2,}", " ", _MONEY_IN_TEXT.sub("", title)).strip(" -")


def to_candidates(items: List[Feedback], include_endorsements: bool = False) -> List[FactCandidate]:
    """Quoted feedback becomes client_quote candidates; endorsement-only jobs only on request."""
    out: List[FactCandidate] = []
    for fb in items:
        title = _clean_title(fb.title)
        rating = f"{fb.rating:g}/5" if fb.rating else "rated"
        when = f"{fb.start} to {fb.end}" if fb.start else ""
        chips = ", ".join(fb.endorsements)
        ref = f"upwork-feedback:{re.sub(r'[^a-z0-9]+', '-', title.lower())[:120]}:{fb.start}"[:200]
        if fb.quote:
            detail = "; ".join(x for x in (
                when, f"Endorsed for: {chips}" if chips else "",
                "Quote shortened on the profile; the full text is on Upwork" if fb.truncated else "",
            ) if x) or None
            out.append(FactCandidate(
                kind="client_quote", statement=f'Client feedback on "{title}" ({rating}): "{fb.quote}"',
                detail=detail, strength=0.8, source_type=SOURCE_TYPE, source_ref=ref, source_snippet=fb.quote,
            ))
        elif include_endorsements and chips:
            out.append(FactCandidate(
                kind="client_quote",
                statement=f'Client endorsed Chris for {chips} on "{title}" ({rating}).',
                detail=when or None, strength=0.6, source_type=SOURCE_TYPE, source_ref=ref, source_snippet=chips,
            ))
    return out
