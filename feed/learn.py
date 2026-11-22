"""Learn from what's actually read.

The X3 reports reading sessions (start and end position in basis points of the
whole book, plus active seconds). Each issue record stores where every article
sits in its EPUB, so a session maps onto the articles it covered. Sources and
topics that get read more than average drift up; ones that get skipped drift
down, by at most `learn_strength` either way.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

WORDS_PER_MINUTE = 250
READ_THRESHOLD = 0.5   # share of an article covered to count it as read
PRIOR = 5              # pseudo-observations before a multiplier moves much


def _issue_for(weekday: str, on: date, issues: dict[date, dict]) -> Optional[date]:
    """Newest issue with that weekday published on or before the session's date."""
    days = [d for d, rec in issues.items() if rec.get("weekday") == weekday and d <= on]
    return max(days) if days else None


def coverage(issues: dict[date, dict], sessions: list[dict], tz: str) -> dict[date, list[float]]:
    """Share (0..1) of each article covered by reading, per issue date."""
    zone = ZoneInfo(tz)
    cov: dict[date, list[float]] = {}
    seen_ids: set[str] = set()
    for s in sessions:
        if s.get("id"):
            if s["id"] in seen_ids:
                continue  # delivery is at-least-once
            seen_ids.add(s["id"])
        on = datetime.fromtimestamp(int(s.get("ts", 0)), timezone.utc).astimezone(zone).date()
        d = _issue_for(s.get("weekday", ""), on, issues)
        if d is None:
            continue
        arts = issues[d].get("articles", [])
        row = cov.setdefault(d, [0.0] * len(arts))
        lo, hi = sorted((int(s.get("start_bp", 0)), int(s.get("end_bp", 0))))
        overlaps = []
        for a in arts:
            span = max(1, a["end_bp"] - a["start_bp"])
            ov = max(0, min(hi, a["end_bp"]) - max(lo, a["start_bp"])) / span
            overlaps.append(ov)
        range_words = sum(ov * a.get("words", 0) for ov, a in zip(overlaps, arts))
        # A long jump through the contents page covers articles that were never
        # read; scale credit by how many words the session's time could cover.
        possible = int(s.get("duration", 0)) / 60 * WORDS_PER_MINUTE
        credit = min(1.0, possible / range_words) if range_words else 0.0
        for i, ov in enumerate(overlaps):
            row[i] = min(1.0, row[i] + ov * credit)
    return cov


def _multipliers(stats: dict[str, list[float]], global_rate: float, strength: float) -> dict[str, float]:
    out = {}
    for key, (shown, read) in stats.items():
        rate = read / shown if shown else 0
        rel = (rate - global_rate) / max(global_rate, 0.1)
        confidence = shown / (shown + PRIOR)
        out[key] = round(1 + strength * max(-1.0, min(1.0, rel)) * confidence, 3)
    return out


def learn(issues: dict[date, dict], sessions: list[dict], tz: str, strength: float) -> dict:
    """Return {"sources": {name: x}, "topics": {topic: x}, "stats": {...}}."""
    cov = coverage(issues, sessions, tz)
    by_source: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
    by_topic: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
    shown = read = 0
    for d, row in cov.items():  # only issues that were opened count
        for a, c in zip(issues[d].get("articles", []), row):
            if a.get("kind") != "article":
                continue  # saved links and headline cards aren't ranked
            hit = 1.0 if c >= READ_THRESHOLD else c
            for stats, key in ((by_source, a["source"]), (by_topic, a["topic"])):
                stats[key][0] += 1
                stats[key][1] += hit
            shown += 1
            read += hit
    if not shown:
        return {"sources": {}, "topics": {}, "stats": {"issues_opened": 0}}
    g = read / shown
    return {
        "sources": _multipliers(by_source, g, strength),
        "topics": _multipliers(by_topic, g, strength),
        "stats": {
            "issues_opened": len(cov),
            "articles_shown": shown,
            "articles_read": round(read, 1),
            "read_rate": round(g, 3),
            "by_source": {k: {"shown": v[0], "read": round(v[1], 1)} for k, v in sorted(by_source.items())},
        },
    }
