"""Stage 1: fetch feeds and normalise entries into Items."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import feedparser

from . import http
from .config import Source
from .models import Item

log = logging.getLogger(__name__)

_POINTS_RE = re.compile(r"Points:\s*(\d+)", re.I)


@dataclass
class FeedResult:
    source: Source
    items: list[Item] = field(default_factory=list)
    error: Optional[str] = None
    feed_title: Optional[str] = None
    final_url: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def last_post(self) -> Optional[datetime]:
        dates = [i.published for i in self.items if i.published]
        return max(dates) if dates else None


def _entry_date(entry) -> Optional[datetime]:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def _entry_content(entry) -> Optional[str]:
    contents = entry.get("content") or []
    best = max((c.get("value", "") for c in contents), key=len, default="")
    return best or None


def parse_entries(source: Source, parsed) -> list[Item]:
    items = []
    for entry in parsed.entries:
        url = entry.get("link")
        title = (entry.get("title") or "").strip()
        if not url or not title:
            continue
        summary = entry.get("summary")
        points = None
        if summary:
            m = _POINTS_RE.search(summary)
            if m:
                points = int(m.group(1))
        items.append(
            Item(
                source=source,
                title=title,
                url=url,
                published=_entry_date(entry),
                author=entry.get("author"),
                content_html=_entry_content(entry),
                summary_html=summary,
                points=points,
            )
        )
    return items


def fetch_source(source: Source) -> FeedResult:
    """Fetch one feed. Never raises: errors are reported on the result."""
    result = FeedResult(source=source)
    if not source.url:
        result.error = "no feed URL configured"
        return result
    try:
        resp = http.get(source.url)
    except Exception as e:  # noqa: BLE001 - fail soft on any network error
        result.error = f"fetch failed: {e}"
        return result
    result.final_url = resp.url
    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        result.error = f"not a feed: {parsed.get('bozo_exception', 'parse error')}"
        return result
    result.feed_title = parsed.feed.get("title")
    result.items = parse_entries(source, parsed)
    if not result.items:
        result.error = "feed has 0 items"
    return result
