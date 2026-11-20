from datetime import datetime, timezone

import pytest

from conftest import FIXTURE_PROFILE
from feed.config import load_profile
from feed.extract import SkipArticle, clean_html, extract, is_truncated, looks_paywalled
from feed.models import Item

PROFILE = load_profile(FIXTURE_PROFILE)
ALWAYS, FILTERED = PROFILE.sources[0], PROFILE.sources[1]
LONG = "".join(f"<p>Paragraph {i} " + "word " * 60 + "</p>" for i in range(8))


def _item(source, content, title="A title"):
    return Item(source=source, title=title, url="https://x.example.test/p/a",
                published=datetime(2026, 1, 1, tzinfo=timezone.utc), content_html=content)


def test_full_feed_content_becomes_article():
    art = extract(_item(ALWAYS, LONG), max_images=0)
    assert art.word_count > 400
    assert art.read_minutes >= 2


def test_substack_truncated_post_is_skipped():
    raw = LONG + '<p> <a href="https://x.example.test/p/a"> Read more </a> </p>'
    assert is_truncated(raw)
    with pytest.raises(SkipArticle, match="paid"):
        extract(_item(ALWAYS, raw), max_images=0)


def test_paywall_markers():
    assert looks_paywalled("<p>Intro</p><div class='paywall'><hr class='paywall__break'/></div>", 300)
    assert looks_paywalled("<p>This post is for paid subscribers</p>", 300)
    assert looks_paywalled("<p>Short teaser. Subscribe to read.</p>", 300)
    assert not looks_paywalled(LONG, 300)


def test_title_skip_regex():
    with pytest.raises(SkipArticle, match="title"):
        extract(_item(FILTERED, LONG, title="Weekly Podcast #4"), max_images=0)


def test_clean_html_strips_chrome_and_scripts():
    raw = ('<p>Real text here.</p><script>alert(1)</script>'
           '<div class="subscription-widget"><p>Subscribe now</p></div>'
           '<p><a href="/share">Share</a></p><iframe src="x"></iframe>'
           '<p style="color:red" class="x">More text.</p>')
    body, images = clean_html(raw, "https://x.example.test/", max_images=0)
    assert "Real text here." in body and "More text." in body
    for bad in ("script", "Subscribe", "Share", "iframe", "style=", "class="):
        assert bad not in body
    assert images == []
