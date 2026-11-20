"""Milestone 2: a sample catalog with a handful of real articles.

Picks the newest post from a spread of sources (always-include first, then a
mix of topics), runs fetch -> extract -> EPUB, and writes one date folder plus
the OPDS feeds. No ranking or dedupe state yet; that is milestone 3.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from .config import Profile
from .epub import article_filename, build_epub
from .extract import SkipArticle, extract
from .fetch import fetch_source
from .models import Item
from .opds import CatalogEntry, write_catalog, write_manifest

log = logging.getLogger(__name__)


def _candidates(results, window: timedelta) -> list[Item]:
    """Newest item per source, alternating always-include and filtered sources
    (one per topic first), so a small sample covers every extraction path."""
    now = datetime.now(timezone.utc)
    newest: list[Item] = []
    for r in results:
        recent = [i for i in r.items if i.published and now - i.published <= window]
        recent.sort(key=lambda i: i.published, reverse=True)
        newest.extend(recent[:2])

    def spread(items: list[Item]) -> list[Item]:
        firsts, rest, topics = [], [], set()
        for i in sorted(items, key=lambda i: i.published, reverse=True):
            (rest if i.source.topic in topics else firsts).append(i)
            topics.add(i.source.topic)
        return firsts + rest

    always = spread([i for i in newest if i.source.tier == "always"])
    filtered = spread([i for i in newest if i.source.tier != "always"])
    ordered: list[Item] = []
    while always or filtered:
        for bucket in (always, filtered):
            if bucket:
                ordered.append(bucket.pop(0))
    return ordered


def build_sample(profile: Profile, n: int, out_dir: Path, base_url: Optional[str]) -> Path:
    s = profile.settings
    tz = ZoneInfo(s.timezone)
    issue = datetime.now(tz)
    day = issue.date()
    day_dir = out_dir / profile.slug / day.isoformat()

    log.info("fetching %d feeds", len(profile.active_sources))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(fetch_source, profile.active_sources))
    for r in results:
        if not r.ok:
            log.warning("%s: %s", r.source.name, r.error)

    articles = []
    used_sources: set[str] = set()
    for item in _candidates(results, timedelta(days=7)):
        if len(articles) >= n:
            break
        if item.source.name in used_sources:
            continue
        try:
            art = extract(item, max_images=s.max_images, min_read_minutes=s.min_read_minutes)
        except SkipArticle as e:
            log.info("skip %s — %s: %s", item.source.name, item.title[:60], e)
            continue
        except Exception as e:  # noqa: BLE001 - fail soft
            log.warning("error %s — %s: %s", item.source.name, item.title[:60], e)
            continue
        articles.append(art)
        used_sources.add(item.source.name)
        log.info("ok   %s — %s (%d words, %d images)", item.source.name, art.title[:60],
                 art.word_count, len(art.images))

    # always-include first, as in the daily ordering
    articles.sort(key=lambda a: a.item.source.tier != "always")

    if day_dir.exists():
        for old in day_dir.glob("*.epub"):
            old.unlink()
    entries = []
    for idx, art in enumerate(articles, start=1):
        fname = article_filename(idx, art)
        path = build_epub(art, day_dir / fname, issue)
        entries.append(CatalogEntry(
            id=f"urn:morning-feed:{profile.slug}:{day.isoformat()}:{idx:02d}",
            title=art.title, author=art.author, source=art.item.source.name,
            topic=art.item.source.topic, read_minutes=art.read_minutes,
            summary=art.summary, file=fname, size=path.stat().st_size,
            published=art.item.published.strftime("%Y-%m-%dT%H:%M:%SZ") if art.item.published else None,
            url=art.item.url,
        ))
    write_manifest(day_dir, entries)
    (out_dir / ".nojekyll").touch()
    root = write_catalog(out_dir, profile.slug, s.catalog_title, base_url)

    print(f"\nBuilt {len(entries)} EPUBs in {day_dir}")
    for e in entries:
        print(f"  {e.file}  ({e.size // 1024} KB) — {e.title} · {e.line}")
    print(f"Catalog: {root}")
    return root
