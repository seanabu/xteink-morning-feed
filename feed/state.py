"""Per-profile state kept between daily runs.

Lives on the repo's `state` branch (checked out at ./state in CI):

    state/<profile>/seen.json            {normalized url: "YYYY-MM-DD"} for dedupe
    state/<profile>/last_run.json        {"finished": ISO time}
    state/<profile>/issues/DATE.json     what went into each issue (for feedback)
    state/<profile>/learned.json         weights learned from reading, for reference
    state/<profile>/events/save/*.json   read-later links from the phone (consumed)
    state/<profile>/events/reading/*.json  reading sessions from the X3 (kept)

Events are one file each so concurrent writers never conflict.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING = re.compile(r"^(utm_|ref$|ref_|source$|s$|smid$|fbclid$|gclid$|mc_|r$|triedRedirect$)", re.I)


def normalize_url(url: str) -> str:
    """Lowercase host, drop scheme, www, fragments, tracking params, trailing slash."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING.match(k)])
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("", host, path, query, "")).lstrip("/")


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


class State:
    def __init__(self, root: Path, slug: str):
        self.dir = Path(root) / slug
        self.seen: dict[str, str] = _read_json(self.dir / "seen.json", {})

    # --- dedupe -------------------------------------------------------------
    def is_seen(self, url: str) -> bool:
        return normalize_url(url) in self.seen

    def mark_seen(self, url: str, day: date) -> None:
        self.seen[normalize_url(url)] = day.isoformat()

    def prune_seen(self, today: date, keep_days: int) -> None:
        cutoff = (today - timedelta(days=keep_days)).isoformat()
        self.seen = {u: d for u, d in self.seen.items() if d >= cutoff}

    # --- run bookkeeping ----------------------------------------------------
    def last_run(self) -> Optional[datetime]:
        raw = _read_json(self.dir / "last_run.json", {}).get("finished")
        return datetime.fromisoformat(raw) if raw else None

    def save(self, finished: datetime) -> None:
        _write_json(self.dir / "seen.json", self.seen)
        _write_json(self.dir / "last_run.json", {"finished": finished.astimezone(timezone.utc).isoformat()})

    # --- issues -------------------------------------------------------------
    def write_issue(self, day: date, record: dict) -> None:
        _write_json(self.dir / "issues" / f"{day.isoformat()}.json", record)

    def issues(self) -> dict[date, dict]:
        out = {}
        for p in sorted((self.dir / "issues").glob("*.json")):
            try:
                out[date.fromisoformat(p.stem)] = _read_json(p, {})
            except ValueError:
                continue
        return out

    def prune_issues(self, today: date, keep_days: int) -> None:
        for d in self.issues():
            if (today - d).days > keep_days:
                (self.dir / "issues" / f"{d.isoformat()}.json").unlink(missing_ok=True)

    def write_learned(self, data: dict) -> None:
        _write_json(self.dir / "learned.json", data)

    # --- events -------------------------------------------------------------
    def events(self, kind: str) -> list[tuple[Path, dict]]:
        out = []
        for p in sorted((self.dir / "events" / kind).glob("*.json")):
            data = _read_json(p, None)
            if isinstance(data, dict):
                out.append((p, data))
        return out

    def prune_events(self, kind: str, today: date, keep_days: int) -> None:
        cutoff = datetime.combine(today - timedelta(days=keep_days), datetime.min.time(), timezone.utc)
        for p, data in self.events(kind):
            try:
                ts = datetime.fromtimestamp(int(data.get("ts") or 0), timezone.utc)
            except (TypeError, ValueError):
                continue
            if ts < cutoff:
                p.unlink(missing_ok=True)
