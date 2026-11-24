"""Milestone 3: the daily issue.

fetch -> dedupe -> rank -> extract and fill -> one issue EPUB -> OPDS -> state.
Fails soft per feed and per article; only an issue with nothing in it fails.
"""

from __future__ import annotations

import logging
import shutil
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import trafilatura

from . import http
from .config import Profile, Source
from .extract import SkipArticle, extract
from .fetch import fetch_source
from .issue import IssueArticle, build_issue
from .learn import learn
from .models import Article, Item
from .opds import update_index, write_catalog
from .rank import dedupe, fetch_since, in_window, rank
from .state import State, normalize_url

log = logging.getLogger(__name__)
SAVED_TOPIC = "saved"


def _try_extract(item: Item, profile: Profile, min_minutes: float) -> Optional[Article]:
    try:
        return extract(item, max_images=profile.settings.max_images, min_read_minutes=min_minutes)
    except SkipArticle as e:
        log.info("skip  %s — %s: %s", item.source.name, item.title[:60], e)
    except Exception as e:  # noqa: BLE001 - fail soft
        log.warning("error %s — %s: %s", item.source.name, item.title[:60], e)
    return None


def _page_title(url: str) -> Optional[str]:
    try:
        meta = trafilatura.extract_metadata(http.get(url).text)
        return meta.title if meta and meta.title else None
    except Exception:  # noqa: BLE001
        return None


def saved_items(state: State) -> list[Item]:
    """Links shared from the phone since the last issue, oldest first."""
    items = []
    for _, ev in state.events("save"):
        url = ev.get("url")
        if not url:
            continue
        host = urlsplit(url).netloc.lower().removeprefix("www.") or "link"
        src = Source(name=host, url=url, tier="always", topic=SAVED_TOPIC, extract="page", min_words=0)
        title = ev.get("title") or _page_title(url) or url
        published = datetime.fromtimestamp(int(ev.get("ts", 0)), timezone.utc)
        items.append(Item(source=src, title=title, url=url, published=published))
    return items


def _headline_card(item: Item) -> Article:
    """Fallback for a saved link that wouldn't extract: title, summary, URL."""
    return Article(item=item, title=item.title, author=item.source.name,
                   body_html="", word_count=0, summary="")


def fill(candidates: list[Item], profile: Profile, pool: ThreadPoolExecutor) -> list[tuple[Article, str]]:
    """Extract candidates in rank order, in parallel batches, until the issue is full."""
    s = profile.settings
    picked: list[tuple[Article, str]] = []
    topics: Counter = Counter()
    sources: Counter = Counter()

    def n_articles() -> int:
        return sum(1 for _, k in picked if k == "article")

    def fits(item: Item) -> bool:
        if item.source.extract == "summary":
            return (sum(1 for _, k in picked if k == "headline") < s.headline_cap
                    and topics[("h", item.source.topic)] < s.topic_cap)
        if item.source.tier == "always":
            return True
        return (n_articles() < s.daily_target and topics[item.source.topic] < s.topic_cap
                and sources[item.source.name] < s.source_cap)

    queue = list(candidates)
    while queue:
        # Only extract what could still fit; batch size tracks the open slots.
        batch, rest = [], []
        for item in queue:
            (batch if fits(item) and len(batch) < max(8, s.daily_target) else rest).append(item)
        if not batch:
            break
        queue = [i for i in rest if fits(i)]
        for item, art in zip(batch, pool.map(lambda i: _try_extract(i, profile, s.min_read_minutes), batch)):
            if art is None or not fits(item):
                continue
            if item.source.extract == "summary":
                picked.append((art, "headline"))
                topics[("h", item.source.topic)] += 1
                continue
            picked.append((art, "article"))
            topics[item.source.topic] += 1
            if item.source.tier != "always":
                sources[item.source.name] += 1
    return picked


def _clean_site(profile_dir: Path) -> None:
    """Remove the per-article layout from earlier builds (date folders, nested feeds)."""
    if not profile_dir.exists():
        return
    for p in profile_dir.iterdir():
        if p.name in ("issues", "opds"):
            continue
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    for p in (profile_dir / "opds").glob("*.xml"):
        if p.name != "root.xml":
            p.unlink()


def build_daily(profile: Profile, out_dir: Path, state_dir: Path, now: Optional[datetime] = None,
                base_url: Optional[str] = None, force: bool = True) -> int:
    """Build today's issue. With force=False, a day that already has an issue is
    left alone (the schedule fires several times so a late or dropped run is covered)."""
    s = profile.settings
    now = now or datetime.now(timezone.utc)
    day = now.astimezone(ZoneInfo(s.timezone)).date()
    state = State(state_dir, profile.slug)

    if not force and day in state.issues():
        log.info("%s already has an issue for %s; skipping", profile.slug, day)
        if base_url:  # still refresh the catalog, so link fixes reach the site
            write_catalog(out_dir, profile.slug, s.catalog_title, now, base_url)
        return 0

    # A re-run on the same day rebuilds from the same pool of articles.
    previous = state.issues().get(day)
    if previous:
        for a in previous.get("articles", []):
            state.seen.pop(normalize_url(a["url"]), None)

    learned = {}
    if s.learn_from_reading:
        sessions = [ev for _, ev in state.events("reading")]
        learned = learn(state.issues(), sessions, s.timezone, s.learn_strength)
        state.write_learned(learned)
        log.info("learned from %s opened issues", learned["stats"].get("issues_opened", 0))

    log.info("fetching %d feeds", len(profile.active_sources))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(fetch_source, profile.active_sources))
        for r in results:
            if not r.ok:
                log.warning("feed  %s: %s", r.source.name, r.error)
        since = fetch_since(state.last_run(), now, s.fetch_window_hours)
        items = in_window([i for r in results for i in r.items], since)
        items = dedupe(items, state, s.title_similarity)
        candidates = rank(items, profile, learned)
        log.info("%d new items since %s", len(candidates), since.isoformat(timespec="minutes"))

        saved = [i for i in saved_items(state) if not state.is_seen(i.url)]
        saved_articles = []
        for item, art in zip(saved, pool.map(lambda i: _try_extract(i, profile, 0), saved)):
            saved_articles.append((art or _headline_card(item), "saved" if art else "headline"))

        picked = saved_articles + fill(candidates, profile, pool)

    readable = [p for p in picked if p[1] != "headline"]
    if not readable:
        log.error("no articles made it into the issue; nothing published")
        return 1

    def label(art: Article) -> str:
        t = art.item.source.topic
        return s.inbox_label if t == SAVED_TOPIC else profile.topic_label(t)

    order = {"saved": 0, "article": 1, "headline": 2}
    picked.sort(key=lambda p: order[p[1]])  # stable: keeps rank order within each group
    issue_items = [IssueArticle(article=a, kind=k, topic_label=label(a)) for a, k in picked]

    profile_dir = out_dir / profile.slug
    _clean_site(profile_dir)
    issues_dir = profile_dir / "issues"
    epub_path = issues_dir / f"{day.isoformat()}-{day:%A}.epub".lower()
    record = build_issue(issue_items, epub_path, day, profile.slug, s.catalog_title, s.inbox_label)
    update_index(issues_dir, record)
    (out_dir / ".nojekyll").touch()
    root = write_catalog(out_dir, profile.slug, s.catalog_title, now, base_url)

    # State: remember what was used, consume the inbox, prune old history.
    for a in record["articles"]:
        state.mark_seen(a["url"], day)
    for p, _ in state.events("save"):
        p.unlink(missing_ok=True)
    state.write_issue(day, record)
    state.prune_seen(day, s.seen_days)
    state.prune_issues(day, s.seen_days)
    state.prune_events("reading", day, s.seen_days)
    state.save(now)

    print(f"\n{record['title']} ({day}) — {record['size'] // 1024} KB, {record['read_minutes']} min")
    for a in record["articles"]:
        print(f"  [{a['kind']:8}] {a['source']} · {a['topic']} · {a['read_minutes']} min — {a['title'][:70]}")
    print(f"Catalog: {root}")
    return 0
