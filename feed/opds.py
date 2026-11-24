"""Stage 7: static OPDS 1.2 catalog of daily issues.

Layout under <out>/<profile>/:
    opds/root.xml                 one acquisition feed: the last 7 issues, newest first
    issues/YYYY-MM-DD-weekday.epub
    issues/index.json             manifest the feed is regenerated from

One entry per weekday: "Morning Feed - Saturday". On the X3 the file name comes
from the title, so next week's Saturday issue replaces this one on the device.
Links are absolute when a base URL is given (the published site). CrossPoint
does not resolve relative links the RFC way: it appends them to the feed URL
itself (".../opds/root.xml/../issues/x.epub"), which 404s. Without a base URL
(local previews) links fall back to relative.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape, quoteattr

ACQ_TYPE = "application/atom+xml;profile=opds-catalog;kind=acquisition"
NAV_TYPE = "application/atom+xml;profile=opds-catalog;kind=navigation"
EPUB_TYPE = "application/epub+zip"


def _fmt_minutes(m: int) -> str:
    return f"{m // 60}h {m % 60}m" if m >= 60 else f"{m} min"


def entry_line(rec: dict) -> str:
    """Shown under the title on the X3: 'Sat Nov 21 · 14 articles · 2h 5m'."""
    d = date.fromisoformat(rec["date"])
    n = sum(1 for a in rec["articles"] if a["kind"] != "headline")
    return f"{d:%a %b} {d.day} · {n} articles · {_fmt_minutes(rec.get('read_minutes', 0))}"


def read_index(issues_dir: Path) -> list[dict]:
    try:
        return json.loads((issues_dir / "index.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def update_index(issues_dir: Path, record: dict, keep: int = 7) -> list[dict]:
    """Add today's issue, keep one issue per weekday (newest), delete stale EPUBs."""
    issues = [r for r in read_index(issues_dir) if r["date"] != record["date"]] + [record]
    issues.sort(key=lambda r: r["date"], reverse=True)
    kept, weekdays = [], set()
    for r in issues:
        if r["weekday"] in weekdays or len(kept) >= keep:
            continue
        weekdays.add(r["weekday"])
        kept.append(r)
    live = {r["file"] for r in kept}
    for p in issues_dir.glob("*.epub"):
        if p.name not in live:
            p.unlink()
    kept = [r for r in kept if (issues_dir / r["file"]).exists()]
    (issues_dir / "index.json").write_text(json.dumps(kept, indent=2, ensure_ascii=False), encoding="utf-8")
    return kept


def _href(base_url: Optional[str], slug: str, path: str, fallback: str) -> str:
    return f"{base_url.rstrip('/')}/{slug}/{path}" if base_url else fallback


def _entry(rec: dict, slug: str, updated: str, base_url: Optional[str] = None) -> str:
    readable = [a for a in rec["articles"] if a["kind"] != "headline"]
    summary = " · ".join(a["title"] for a in readable)[:400]
    return (
        "  <entry>\n"
        f"    <title>{escape(rec['title'])}</title>\n"
        f"    <id>urn:morning-feed:{slug}:{rec['date']}</id>\n"
        f"    <updated>{updated}</updated>\n"
        f"    <author><name>{escape(entry_line(rec))}</name></author>\n"
        "    <dc:language>en</dc:language>\n"
        f"    <dc:issued>{rec['date']}</dc:issued>\n"
        + (f'    <summary type="text">{escape(summary)}</summary>\n' if summary else "") +
        f'    <link rel="http://opds-spec.org/acquisition" href={quoteattr(_href(base_url, slug, "issues/" + rec["file"], "../issues/" + rec["file"]))} '
        f'type="{EPUB_TYPE}" length="{rec["size"]}"/>\n'
        "  </entry>\n"
    )


def write_catalog(out_dir: Path, slug: str, title: str, now: Optional[datetime] = None,
                  base_url: Optional[str] = None) -> Path:
    """Regenerate root.xml from the issues index."""
    profile_dir = out_dir / slug
    opds_dir = profile_dir / "opds"
    opds_dir.mkdir(parents=True, exist_ok=True)
    updated = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = read_index(profile_dir / "issues")
    root = opds_dir / "root.xml"
    self_href = quoteattr(_href(base_url, slug, "opds/root.xml", "root.xml"))
    root.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/terms/" '
        'xmlns:opds="http://opds-spec.org/2010/catalog">\n'
        f"  <id>urn:morning-feed:{slug}:root</id>\n"
        f"  <title>{escape(title)}</title>\n"
        f"  <updated>{updated}</updated>\n"
        "  <author><name>Morning Feed</name></author>\n"
        f'  <link rel="self" href={self_href} type="{ACQ_TYPE}"/>\n'
        f'  <link rel="start" href={self_href} type="{ACQ_TYPE}"/>\n'
        + "".join(_entry(r, slug, updated, base_url) for r in issues)
        + "</feed>\n",
        encoding="utf-8",
    )
    return root
