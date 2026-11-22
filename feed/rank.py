"""Stages 2 and 5: dedupe, then keyword ranking.

Scores are generic: source weight x topic weight x learned multipliers x a
keyword boost from interests.yaml. Nothing here knows any topic or source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Iterable, Optional

from .config import Profile
from .models import Item
from .state import State, normalize_url


def _norm_title(t: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", t.lower()).split())


def _similar(a: str, b: str, threshold: float) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= threshold


def _priority(i: Item) -> tuple:
    # Keep the always-include / higher-weight / full-text copy of a story.
    return (i.source.tier == "always", i.source.weight, i.source.extract != "summary")


def dedupe(items: Iterable[Item], state: Optional[State], threshold: float) -> list[Item]:
    """Drop items seen in earlier issues, then collapse the same story by URL and title."""
    kept: list[Item] = []
    by_url: dict[str, int] = {}
    for item in sorted(items, key=_priority, reverse=True):
        if state and state.is_seen(item.url):
            continue
        key = normalize_url(item.url)
        if key in by_url:
            continue
        by_url[key] = len(kept)  # remembered even if dropped below, as the same story
        t = _norm_title(item.title)
        if t and any(_similar(t, _norm_title(k.title), threshold) for k in kept):
            continue
        kept.append(item)
    return kept


def in_window(items: Iterable[Item], since: datetime) -> list[Item]:
    return [i for i in items if i.published is None or i.published >= since]


def fetch_since(last_run: Optional[datetime], now: datetime, window_hours: int) -> datetime:
    """Items since the last successful run, but never less than the window."""
    floor = now - timedelta(hours=window_hours)
    return min(floor, last_run) if last_run else floor


@dataclass
class Scored:
    item: Item
    score: float
    blocked: bool = False


def _keyword_hits(text: str, keywords: list[str]) -> int:
    text = text.lower()
    return sum(1 for k in keywords if re.search(rf"(?<![a-z0-9]){re.escape(k.lower())}(?![a-z0-9])", text))


def score_item(item: Item, profile: Profile, learned: Optional[dict] = None) -> Scored:
    learned = learned or {}
    interests = profile.interests
    text = " ".join(filter(None, [item.title, re.sub(r"<[^>]+>", " ", item.summary_html or "")[:2000]]))
    if _keyword_hits(item.title, interests.blocklist):
        return Scored(item, 0.0, blocked=True)
    topic = interests.topics.get(item.source.topic)
    topic_weight = topic.weight if topic else 1.0
    hits = _keyword_hits(text, topic.keywords) if topic else 0
    s = item.source.weight * topic_weight * (1 + 0.25 * min(hits, 3))
    s *= learned.get("sources", {}).get(item.source.name, 1.0)
    s *= learned.get("topics", {}).get(item.source.topic, 1.0)
    if item.points:
        s *= 1 + min(item.points, 1000) / 2000  # mild boost for well-upvoted links
    if item.published:
        age_h = (datetime.now(timezone.utc) - item.published).total_seconds() / 3600
        s *= 1.0 if age_h < 24 else 0.9
    return Scored(item, round(s, 4))


def rank(items: Iterable[Item], profile: Profile, learned: Optional[dict] = None) -> list[Item]:
    """Candidates in fill order: always-include first (newest first), then filtered by score.

    Blocked items are dropped. Caps are applied while filling (see daily.fill),
    because extraction can still reject a candidate."""
    scored = [score_item(i, profile, learned) for i in items]
    always = [s for s in scored if s.item.source.tier == "always" and not s.blocked]
    filtered = [s for s in scored if s.item.source.tier != "always" and not s.blocked]
    always.sort(key=lambda s: s.item.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    filtered.sort(key=lambda s: s.score, reverse=True)
    return [s.item for s in always + filtered]
