"""Record one event from the phone or the X3 into the state folder.

Run by the `record` GitHub Actions workflow (stdlib only, no install step):

    python -m feed.record --state state --profile sean --kind save --url <link>
    python -m feed.record --state state --profile sean --kind reading --book "/Morning Feed - Monday.epub" \
        --start-bp 0 --end-bp 2300 --duration 610 --ts 1763700000 --event-id abc

Reading sessions for books that are not daily issues are dropped here, so the
state branch never records which other books are being read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")


def issue_weekday(book: str, issue_title: str) -> str | None:
    """'/Downloads/Morning Feed - Monday.epub' -> 'monday' (None if not an issue)."""
    name = Path(book).name.lower()
    prefix = re.sub(r"[^a-z0-9]+", "", issue_title.lower())
    if prefix and prefix not in re.sub(r"[^a-z0-9]+", "", name):
        return None
    for d in WEEKDAYS:
        if re.search(rf"\b{d}\b", name):
            return d
    return None


def catalog_title(profile_dir: Path) -> str:
    """catalog_title from profile.yaml without a YAML parser (this runs before any install)."""
    try:
        text = (profile_dir / "profile.yaml").read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"unknown profile {profile_dir.name!r}")
    m = re.search(r"^catalog_title:\s*[\"']?([^\"'#\n]+?)[\"']?\s*(?:#.*)?$", text, re.M)
    return m.group(1).strip() if m else "Morning Feed"


def _int(v, lo=0, hi=10**12) -> int:
    try:
        return max(lo, min(hi, int(float(v))))
    except (TypeError, ValueError):
        raise SystemExit(f"not a number: {v!r}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--state", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--kind", choices=["save", "reading"], required=True)
    p.add_argument("--profiles", default="profiles", help="to read the profile's catalog_title")
    p.add_argument("--url", default="")
    p.add_argument("--title", default="")
    p.add_argument("--book", default="")
    p.add_argument("--start-bp", default="0")
    p.add_argument("--end-bp", default="0")
    p.add_argument("--duration", default="0")
    p.add_argument("--ts", default="")
    p.add_argument("--event-id", default="")
    a = p.parse_args(argv)

    if not SLUG.match(a.profile):
        raise SystemExit(f"bad profile name {a.profile!r}")
    now = int(time.time())

    if a.kind == "save":
        m = re.search(r"https?://\S+", a.url or "")
        if not m:
            raise SystemExit("no URL in the shared text")
        url = m.group(0).rstrip(").,>\"'")
        record = {"url": url, "title": a.title.strip()[:300], "ts": now}
        key = hashlib.sha1(url.encode()).hexdigest()[:12]
    else:
        weekday = issue_weekday(a.book, catalog_title(Path(a.profiles) / a.profile))
        if not weekday:
            print("not a Morning Feed issue; ignored")
            return 0
        ts = _int(a.ts) if a.ts and a.ts.strip("{}").isdigit() else now
        record = {
            "weekday": weekday,
            "start_bp": _int(a.start_bp, 0, 10000),
            "end_bp": _int(a.end_bp, 0, 10000),
            "duration": _int(a.duration, 0, 86400),
            "ts": ts,
            "id": re.sub(r"[^A-Za-z0-9_-]", "", a.event_id)[:64],
        }
        key = record["id"] or hashlib.sha1(json.dumps(record, sort_keys=True).encode()).hexdigest()[:12]

    out = Path(a.state) / a.profile / "events" / a.kind / f"{record['ts']}-{key}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"recorded {a.kind} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
