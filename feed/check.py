"""Milestone 1: validate a profile and test every feed in it."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .config import Profile
from .fetch import FeedResult, fetch_source


def _age(dt: datetime | None, now: datetime) -> str:
    if not dt:
        return "-"
    days = (now - dt).total_seconds() / 86400
    if days < 1:
        return f"{dt:%Y-%m-%d} (<1d)"
    return f"{dt:%Y-%m-%d} ({days:.0f}d)"


def run_check(profile: Profile, stale_days: int = 30) -> int:
    """Print a table of feed health. Returns the number of failing feeds."""
    now = datetime.now(timezone.utc)
    sources = profile.active_sources
    print(f"Profile '{profile.slug}' ({profile.settings.name}): config OK, "
          f"{len(sources)} active sources, {len(profile.interests.topics)} topics\n")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results: list[FeedResult] = list(pool.map(fetch_source, sources))

    name_w = max(len(s.name) for s in sources) + 1
    print(f"{'STATUS':6} {'SOURCE':{name_w}} {'TIER':8} {'TOPIC':15} {'ITEMS':>5}  LAST POST")
    failures = 0
    flagged = []
    for r in results:
        s = r.source
        last = r.last_post
        if not r.ok:
            status = "FAIL"
            failures += 1
        elif last and (now - last).days > stale_days:
            status = "STALE"
        else:
            status = "ok"
        print(f"{status:6} {s.name:{name_w}} {s.tier:8} {s.topic[:15]:15} {len(r.items):>5}  {_age(last, now)}")
        detail = []
        if r.error:
            detail.append(r.error)
        if r.final_url and s.url and r.final_url.rstrip("/") != s.url.rstrip("/"):
            detail.append(f"redirects to {r.final_url}")
        if s.verify:
            detail.append("VERIFY: feed URL not yet confirmed by hand")
            flagged.append(s.name)
        for d in detail:
            print(f"{'':6} {'':{name_w}} ↳ {d}")

    ok = len(results) - failures
    print(f"\n{ok}/{len(results)} feeds OK, {failures} failing, {len(flagged)} marked verify.")
    if flagged:
        print("Verify:", ", ".join(flagged))
    return failures
