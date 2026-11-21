"""Stage 7: static OPDS 1.2 catalog.

Layout under <out>/<profile>/:
    opds/root.xml           navigation feed: one entry per date, newest first
    opds/YYYY-MM-DD.xml     acquisition feed for that date
    opds/flat.xml           fallback: last 3 days in one acquisition feed
    YYYY-MM-DD/index.json   manifest the feeds are regenerated from
    YYYY-MM-DD/*.epub
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape, quoteattr

NAV_TYPE = "application/atom+xml;profile=opds-catalog;kind=navigation"
ACQ_TYPE = "application/atom+xml;profile=opds-catalog;kind=acquisition"
EPUB_TYPE = "application/epub+zip"
MAX_ENTRIES = 20


@dataclass
class CatalogEntry:
    id: str
    title: str
    author: str
    source: str
    topic: str
    read_minutes: int
    summary: str
    file: str  # file name inside the date folder
    size: int
    published: Optional[str] = None  # ISO 8601
    url: str = ""
    topic_label: str = ""

    @property
    def line(self) -> str:
        return f"{self.source} · {self.topic_label or self.topic} · {self.read_minutes} min"


def write_manifest(day_dir: Path, entries: list[CatalogEntry]) -> None:
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "index.json").write_text(
        json.dumps([asdict(e) for e in entries], indent=2, ensure_ascii=False), encoding="utf-8")


def read_manifest(day_dir: Path) -> list[CatalogEntry]:
    path = day_dir / "index.json"
    if not path.exists():
        return []
    return [CatalogEntry(**d) for d in json.loads(path.read_text(encoding="utf-8"))]


def list_days(profile_dir: Path) -> list[date]:
    days = []
    for p in profile_dir.iterdir() if profile_dir.exists() else []:
        if p.is_dir() and (p / "index.json").exists():
            try:
                days.append(date.fromisoformat(p.name))
            except ValueError:
                continue
    return sorted(days, reverse=True)


def day_label(d: date) -> str:
    return f"{d:%a %b} {d.day}"


class _Urls:
    """Builds hrefs: absolute when a base URL is known, else relative to opds/."""

    def __init__(self, base_url: Optional[str], slug: str):
        self.base = f"{base_url.rstrip('/')}/{slug}" if base_url else None

    def opds(self, name: str) -> str:
        return f"{self.base}/opds/{name}" if self.base else name

    def epub(self, day: date, file: str) -> str:
        return f"{self.base}/{day.isoformat()}/{file}" if self.base else f"../{day.isoformat()}/{file}"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _feed(feed_id: str, title: str, self_href: str, self_type: str, start_href: str,
          entries_xml: list[str], updated: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/terms/" '
        'xmlns:opds="http://opds-spec.org/2010/catalog">\n'
        f"  <id>{escape(feed_id)}</id>\n"
        f"  <title>{escape(title)}</title>\n"
        f"  <updated>{updated}</updated>\n"
        "  <author><name>Morning Feed</name></author>\n"
        f'  <link rel="self" href={quoteattr(self_href)} type="{self_type}"/>\n'
        f'  <link rel="start" href={quoteattr(start_href)} type="{NAV_TYPE}"/>\n'
        + "".join(entries_xml)
        + "</feed>\n"
    )


def _acq_entry(e: CatalogEntry, href: str, updated: str, title: Optional[str] = None) -> str:
    # CrossPoint shows <author><name> as the line under each title, so it carries
    # "Source · Topic · N min". The writer's name stays in the EPUB's own metadata.
    summary = (f"By {e.author}. " if e.author and e.author != e.source else "") + (e.summary or "")
    return (
        "  <entry>\n"
        f"    <title>{escape(title or e.title)}</title>\n"
        f"    <id>{escape(e.id)}</id>\n"
        f"    <updated>{e.published or updated}</updated>\n"
        f"    <author><name>{escape(e.line)}</name></author>\n"
        "    <dc:language>en</dc:language>\n"
        f"    <category term={quoteattr(e.topic)} label={quoteattr(e.topic_label or e.topic)}/>\n"
        + (f"    <summary type=\"text\">{escape(summary[:400])}</summary>\n" if summary else "") +
        f'    <link rel="http://opds-spec.org/acquisition" href={quoteattr(href)} '
        f'type="{EPUB_TYPE}" length="{e.size}"/>\n'
        "  </entry>\n"
    )


def write_catalog(out_dir: Path, slug: str, title: str, base_url: Optional[str],
                  flat_days: int = 3) -> Path:
    """Regenerate every OPDS feed for a profile from the manifests on disk."""
    profile_dir = out_dir / slug
    opds_dir = profile_dir / "opds"
    opds_dir.mkdir(parents=True, exist_ok=True)
    urls = _Urls(base_url, slug)
    updated = _now()
    days = list_days(profile_dir)

    nav_entries = []
    for d in days:
        entries = read_manifest(profile_dir / d.isoformat())[:MAX_ENTRIES]
        acq = [_acq_entry(e, urls.epub(d, e.file), updated) for e in entries]
        (opds_dir / f"{d.isoformat()}.xml").write_text(
            _feed(f"urn:morning-feed:{slug}:{d.isoformat()}", day_label(d),
                  urls.opds(f"{d.isoformat()}.xml"), ACQ_TYPE, urls.opds("root.xml"), acq, updated),
            encoding="utf-8")
        nav_entries.append(
            "  <entry>\n"
            f"    <title>{escape(day_label(d))}</title>\n"
            f"    <id>urn:morning-feed:{slug}:{d.isoformat()}</id>\n"
            f"    <updated>{updated}</updated>\n"
            f"    <content type=\"text\">{len(entries)} articles</content>\n"
            f'    <link rel="subsection" href={quoteattr(urls.opds(d.isoformat() + ".xml"))} '
            f'type="{ACQ_TYPE}"/>\n'
            "  </entry>\n"
        )

    root = opds_dir / "root.xml"
    root.write_text(_feed(f"urn:morning-feed:{slug}:root", title, urls.opds("root.xml"),
                          NAV_TYPE, urls.opds("root.xml"), nav_entries, updated), encoding="utf-8")

    flat = []
    for d in days[:flat_days]:
        for e in read_manifest(profile_dir / d.isoformat()):
            flat.append(_acq_entry(e, urls.epub(d, e.file), updated,
                                   title=f"{d.month}/{d.day} · {e.title}"))
    (opds_dir / "flat.xml").write_text(
        _feed(f"urn:morning-feed:{slug}:flat", f"{title} (last {flat_days} days)",
              urls.opds("flat.xml"), ACQ_TYPE, urls.opds("root.xml"), flat[:MAX_ENTRIES], updated),
        encoding="utf-8")
    return root
