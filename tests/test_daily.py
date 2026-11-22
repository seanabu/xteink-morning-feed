import json
from datetime import date, datetime, timedelta, timezone

from conftest import FIXTURE_PROFILE
from feed import record
from feed.config import load_profile
from feed.learn import coverage, learn
from feed.models import Item
from feed.rank import dedupe, fetch_since, rank
from feed.state import State, normalize_url

NOW = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)


def _item(p, idx, title, url, hours_old=2):
    return Item(source=p.sources[idx], title=title, url=url, published=NOW - timedelta(hours=hours_old))


def test_normalize_url_drops_tracking():
    assert normalize_url("https://www.A.test/post/?utm_source=x&id=3#c") == "a.test/post?id=3"


def test_dedupe_by_state_url_and_title(tmp_path):
    p = load_profile(FIXTURE_PROFILE)
    st = State(tmp_path, "p")
    st.mark_seen("https://a.test/old", date(2026, 11, 20))
    items = [
        _item(p, 1, "Old story", "https://a.test/old"),
        _item(p, 1, "The big story of the day", "https://b.test/1"),
        _item(p, 0, "The big story of the day!", "https://c.test/2"),  # same story, always tier wins
        _item(p, 1, "Something else", "https://www.b.test/1?utm_medium=rss"),
    ]
    kept = dedupe(items, st, 0.85)
    assert [i.url for i in kept] == ["https://c.test/2"]


def test_rank_puts_always_first_and_drops_blocklist():
    p = load_profile(FIXTURE_PROFILE)
    items = [
        _item(p, 1, "Plain post", "https://b.test/1"),
        _item(p, 1, "A beta deep dive", "https://b.test/2"),
        _item(p, 1, "Drama erupts", "https://b.test/3"),
        _item(p, 0, "Writer post", "https://a.test/1"),
    ]
    assert [i.title for i in rank(items, p)] == ["Writer post", "A beta deep dive", "Plain post"]
    learned = {"sources": {"Fixture Filtered": 1.0}, "topics": {}}
    assert rank(items, p, learned)[0].title == "Writer post"


def test_fetch_since_covers_missed_days():
    assert fetch_since(None, NOW, 36) == NOW - timedelta(hours=36)
    assert fetch_since(NOW - timedelta(days=3), NOW, 36) == NOW - timedelta(days=3)


def _issues():
    arts = [
        {"kind": "article", "source": "A", "topic": "t1", "words": 1000, "start_bp": 1000, "end_bp": 4000},
        {"kind": "article", "source": "B", "topic": "t2", "words": 1000, "start_bp": 4000, "end_bp": 7000},
        {"kind": "article", "source": "B", "topic": "t2", "words": 1000, "start_bp": 7000, "end_bp": 10000},
    ]
    return {date(2026, 11, 21): {"weekday": "saturday", "articles": arts}}


def test_coverage_maps_sessions_to_articles():
    ts = int(NOW.timestamp())
    s = {"weekday": "saturday", "start_bp": 1000, "end_bp": 4000, "duration": 300, "ts": ts, "id": "x"}
    cov = coverage(_issues(), [s, s], "UTC")  # duplicate delivery counted once
    assert cov[date(2026, 11, 21)] == [1.0, 0.0, 0.0]


def test_coverage_discounts_a_jump_through_the_book():
    ts = int(NOW.timestamp())
    # 30 seconds can't cover 3000 words: it was a skim, not a read.
    s = {"weekday": "saturday", "start_bp": 1000, "end_bp": 10000, "duration": 30, "ts": ts}
    assert max(coverage(_issues(), [s], "UTC")[date(2026, 11, 21)]) < 0.1


def test_learn_boosts_what_gets_read():
    ts = int(NOW.timestamp())
    s = {"weekday": "saturday", "start_bp": 1000, "end_bp": 4000, "duration": 300, "ts": ts}
    out = learn(_issues(), [s], "UTC", 0.3)
    assert out["sources"]["A"] > 1 > out["sources"]["B"]
    assert 0.7 <= out["sources"]["B"] and out["sources"]["A"] <= 1.3
    assert learn(_issues(), [], "UTC", 0.3)["sources"] == {}


def test_record_reading_keeps_only_issues(tmp_path):
    prof = tmp_path / "profiles" / "p"
    prof.mkdir(parents=True)
    (prof / "profile.yaml").write_text("name: X\ncatalog_title: Morning Feed\n")
    args = ["--state", str(tmp_path / "st"), "--profile", "p", "--profiles", str(tmp_path / "profiles"),
            "--kind", "reading", "--start-bp", "10", "--end-bp", "900", "--duration", "60", "--ts", "1763700000"]
    record.main(args + ["--book", "/books/Some Novel.epub", "--event-id", "a"])
    assert not (tmp_path / "st").exists()
    record.main(args + ["--book", "/Morning Feed - Saturday.epub", "--event-id", "b"])
    (f,) = (tmp_path / "st/p/events/reading").glob("*.json")
    assert json.loads(f.read_text())["weekday"] == "saturday"


def test_record_save_extracts_url_from_shared_text(tmp_path):
    record.main(["--state", str(tmp_path), "--profile", "p", "--kind", "save",
                 "--url", "Check this out https://a.test/post?x=1."])
    (f,) = (tmp_path / "p/events/save").glob("*.json")
    assert json.loads(f.read_text())["url"] == "https://a.test/post?x=1"
