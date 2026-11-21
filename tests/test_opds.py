from datetime import date

from lxml import etree

from feed.opds import CatalogEntry, write_catalog, write_manifest

ATOM = "{http://www.w3.org/2005/Atom}"


def _entry(i):
    return CatalogEntry(id=f"urn:t:{i}", title=f"Title {i}", author="A", source="Src",
                        topic="t", read_minutes=5, summary="s", file=f"{i:02d}-x.epub", size=100)


def test_nested_catalog(tmp_path):
    for d in ("2026-11-19", "2026-11-20"):
        write_manifest(tmp_path / "p" / d, [_entry(1), _entry(2)])
    root = write_catalog(tmp_path, "p", "Morning Feed", "https://u.example.test/repo")
    nav = etree.parse(str(root)).getroot()
    entries = nav.findall(f"{ATOM}entry")
    assert [e.findtext(f"{ATOM}title") for e in entries] == ["Fri Nov 20", "Thu Nov 19"]
    href = entries[0].find(f"{ATOM}link").get("href")
    assert href == "https://u.example.test/repo/p/opds/2026-11-20.xml"

    acq = etree.parse(str(tmp_path / "p/opds/2026-11-20.xml")).getroot()
    links = acq.findall(f"{ATOM}entry/{ATOM}link")
    assert links[0].get("type") == "application/epub+zip"
    assert links[0].get("href") == "https://u.example.test/repo/p/2026-11-20/01-x.epub"


def test_flat_catalog_prefixes_dates(tmp_path):
    write_manifest(tmp_path / "p" / "2026-11-20", [_entry(1)])
    write_catalog(tmp_path, "p", "Morning Feed", None)
    flat = etree.parse(str(tmp_path / "p/opds/flat.xml")).getroot()
    assert flat.findtext(f"{ATOM}entry/{ATOM}title") == "11/20 · Title 1"
    assert flat.find(f"{ATOM}entry/{ATOM}link").get("href") == "../2026-11-20/01-x.epub"


def test_author_line_shows_source_topic_and_time(tmp_path):
    e = _entry(1)
    e.topic_label = "NBA"
    write_manifest(tmp_path / "p" / "2026-11-20", [e])
    write_catalog(tmp_path, "p", "Morning Feed", None)
    acq = etree.parse(str(tmp_path / "p/opds/2026-11-20.xml")).getroot()
    assert acq.findtext(f"{ATOM}entry/{ATOM}author/{ATOM}name") == "Src · NBA · 5 min"
    assert acq.find(f"{ATOM}entry/{ATOM}category").get("term") == "t"
