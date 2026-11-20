from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .config import Source


@dataclass
class Item:
    """One feed entry, before extraction."""

    source: Source
    title: str
    url: str
    published: Optional[datetime]
    author: Optional[str] = None
    content_html: Optional[str] = None  # full content from the feed, if any
    summary_html: Optional[str] = None
    points: Optional[int] = None


@dataclass
class Article:
    """An extracted article, ready to become an EPUB."""

    item: Item
    title: str
    author: str
    body_html: str
    word_count: int
    images: list[tuple[str, bytes]] = field(default_factory=list)  # (filename, jpeg bytes)
    summary: str = ""

    @property
    def read_minutes(self) -> int:
        return max(1, round(self.word_count / 230))
