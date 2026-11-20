"""The code must contain no feed URLs or source names (see SPEC: Profiles)."""

import re

import yaml

from conftest import ROOT

CODE = [p for p in (ROOT / "feed").glob("*.py")] + [ROOT / "build.py"]


def _source_names():
    names = set()
    for f in (ROOT / "profiles").glob("*/sources.yaml"):
        for s in yaml.safe_load(f.read_text()) or []:
            names.add(s["name"])
    return names


# XML namespace / spec identifiers required by Atom, OPDS and Dublin Core.
STANDARD_URIS = re.compile(r"https?://(www\.w3\.org|purl\.org|opds-spec\.org)/")


def test_no_urls_in_feed_package():
    for f in (ROOT / "feed").glob("*.py"):
        for url in re.findall(r"https?://[^\s\"'<>]*", f.read_text()):
            assert STANDARD_URIS.match(url), f"{url} hard-coded in {f.name}"


def test_no_source_names_in_code():
    names = _source_names()
    assert names
    for f in CODE:
        text = f.read_text()
        for n in names:
            assert n not in text, f"{n!r} appears in {f}"
