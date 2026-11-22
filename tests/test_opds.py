import zipfile
from datetime import date

from lxml import etree

from conftest import FIXTURE_PROFILE
from feed.config import load_profile
from feed.issue import IssueArticle, build_issue, issue_title, one_liner
from feed.models import Article, Item
from feed.opds import update_index, write_catalog

ATOM = "{http://www.w3.org/2005/Atom}"


def _art(profile, src_idx, title, words=900, summary=""):
    src = profile.sources[src_idx]
    item = Item(source=src, title=title, url=f"https://x.example.test/{title.replace(' ', '-')}", published=None)
    body = "<p>" + " ".join(["word"] * words) + "</p>"
    return Article(item=item, title=title, author="Writer", body_html=body, word_count=words, summary=summary)


def _issue(tmp_path, day, n=3):
    p = load_profile(FIXTURE_PROFILE)
    items = [IssueArticle(_art(p, i % 2, f"Story {i}"), "article", "Topic A") for i in range(n)]
    items.append(IssueArticle(_art(p, 1, "Headline one", words=40), "headline", "Topic B"))
    path = tmp_path / "p" / "issues" / f"{day.isoformat()}-{day:%A}.epub".lower()
    return build_issue(items, path, day, "p", "Morning Feed", "Saved")


def test_issue_record_positions_cover_the_book(tmp_path):
    rec = _issue(tmp_path, date(2026, 11, 21))
    assert rec["title"] == "Morning Feed - Saturday" and rec["weekday"] == "saturday"
    arts = [a for a in rec["articles"] if a["kind"] == "article"]
    assert arts[0]["start_bp"] > 0  # the contents page comes first
    assert all(a["end_bp"] <= b["start_bp"] for a, b in zip(arts, arts[1:]))
    assert rec["articles"][-1]["end_bp"] == 10000
    names = zipfile.ZipFile(tmp_path / "p/issues" / rec["file"]).namelist()
    assert "EPUB/contents.xhtml" in names and "EPUB/headlines.xhtml" in names


def test_catalog_lists_one_issue_per_weekday(tmp_path):
    issues = tmp_path / "p" / "issues"
    for d in (date(2026, 11, 14), date(2026, 11, 20), date(2026, 11, 21)):
        update_index(issues, _issue(tmp_path, d))
    # The older Saturday was replaced by the newer one, file and all.
    assert sorted(p.name for p in issues.glob("*.epub")) == ["2026-11-20-friday.epub", "2026-11-21-saturday.epub"]
    root = etree.parse(str(write_catalog(tmp_path, "p", "Morning Feed"))).getroot()
    entries = root.findall(f"{ATOM}entry")
    assert [e.findtext(f"{ATOM}title") for e in entries] == ["Morning Feed - Saturday", "Morning Feed - Friday"]
    assert entries[0].findtext(f"{ATOM}author/{ATOM}name").startswith("Sat Nov 21 · 3 articles · ")
    link = entries[0].find(f"{ATOM}link")
    assert link.get("href") == "../issues/2026-11-21-saturday.epub"
    assert link.get("type") == "application/epub+zip"


def test_issue_title_uses_weekday():
    assert issue_title("Morning Feed", date(2026, 11, 23)) == "Morning Feed - Monday"


def test_one_liner_skips_link_boilerplate():
    p = load_profile(FIXTURE_PROFILE)
    a = _art(p, 0, "A long enough title here", summary="Article URL: https://a Comments URL: https://b Points: 9")
    a.body_html = "<p>The model is small. It runs on a laptop and beats last year's large model.</p>"
    assert one_liner(a) == "The model is small. It runs on a laptop and beats last year's large model."
