"""Stages 3-4: paywall skip and article extraction.

Produces clean, e-ink friendly XHTML fragments: no scripts, embeds, share
buttons or newsletter chrome, and at most a few small grayscale images.
"""

from __future__ import annotations

import html
import io
import logging
import re
from typing import Optional
from urllib.parse import urljoin

import trafilatura
from lxml import etree
from lxml import html as lhtml
from lxml_html_clean import Cleaner
from PIL import Image

from . import http
from .models import Article, Item

log = logging.getLogger(__name__)

IMAGE_MAX_WIDTH = 480
IMAGE_QUALITY = 70

# Phrases that mean the reader is looking at a paywall stub, not the article.
PAID_MARKERS = re.compile(
    r"this post is for paid subscribers"
    r"|keep reading with a \d+-day free trial"
    r"|this post is for paying subscribers"
    r"|subscribe to continue reading"
    r"|upgrade to paid to (?:read|continue)"
    r"|available to paid subscribers",
    re.I,
)
SUBSCRIBE_PROMPT = re.compile(r"\bsubscribe\b", re.I)
# Markers in the raw feed HTML: a paywall element (beehiiv, Ghost, etc.).
RAW_PAYWALL = re.compile(r"""class=["'][^"']*\bpaywall""", re.I)
# Feed content that stops at a "Read more" link is a truncated excerpt.
TRUNCATED = re.compile(r"<a\b[^>]*>\s*(?:read more|continue reading|keep reading)\s*</a>\s*(?:</p>\s*)?$", re.I)

# Class/id fragments of page chrome that should never reach the reader.
BOILERPLATE_ATTR = re.compile(
    r"subscri|share|social|newsletter|footer|button-wrapper|captioned-button|paywall"
    r"|related|comments?-|signup|sign-up|cta\b|promo|advert|cookie|consent|banner"
    r"|image-link-expand|pencraft|tooltip",
    re.I,
)
# Short standalone blocks of call-to-action text.
CTA_TEXT = re.compile(
    r"^\s*(subscribe( now)?|share|leave a comment|give a gift subscription|"
    r"thanks for reading.*subscribe.*|share this post|upgrade to paid|"
    r"read more|listen now|get \d+% off.*)\s*$",
    re.I,
)

_cleaner = Cleaner(
    scripts=True,
    javascript=True,
    comments=True,
    style=True,
    inline_style=True,
    links=False,
    meta=True,
    page_structure=True,
    processing_instructions=True,
    embedded=True,
    frames=True,
    forms=True,
    annoying_tags=True,
    remove_tags=["span", "font", "picture", "figure", "div", "section", "article", "center"],
    kill_tags=["noscript", "svg", "button", "video", "audio", "source", "aside", "nav", "header", "footer"],
    safe_attrs_only=True,
    safe_attrs=frozenset({"href", "src", "alt", "title", "colspan", "rowspan"}),
)


class SkipArticle(Exception):
    """The item should not become an EPUB (paywalled, too short, etc.)."""


def _text(fragment: str) -> str:
    try:
        doc = lhtml.fragment_fromstring(fragment, create_parent="div")
    except (etree.ParserError, ValueError):
        return ""
    return " ".join(doc.text_content().split())


def word_count(fragment: str) -> int:
    return len(_text(fragment).split())


def is_truncated(raw_html: str) -> bool:
    return bool(TRUNCATED.search(raw_html.strip()))


def looks_paywalled(fragment: str, min_words: int) -> bool:
    if RAW_PAYWALL.search(fragment):
        return True
    text = _text(fragment)
    if PAID_MARKERS.search(text):
        return True
    return len(text.split()) < min_words and bool(SUBSCRIBE_PROMPT.search(text))


def _strip_boilerplate(root) -> None:
    for el in list(root.iter()):
        if not isinstance(el.tag, str) or el.getparent() is None:
            continue
        attrs = " ".join(filter(None, [el.get("class"), el.get("id"), el.get("data-component-name")]))
        if attrs and BOILERPLATE_ATTR.search(attrs):
            el.drop_tree()
            continue
        if el.tag in ("p", "a", "h3", "h4", "li") and len(el.text_content()) < 120:
            if CTA_TEXT.match(el.text_content()):
                el.drop_tree()


def _download_image(src: str) -> Optional[bytes]:
    try:
        resp = http.get(src, timeout=15)
        img = Image.open(io.BytesIO(resp.content))
        img = img.convert("L")
        if img.width > IMAGE_MAX_WIDTH:
            h = round(img.height * IMAGE_MAX_WIDTH / img.width)
            img = img.resize((IMAGE_MAX_WIDTH, h), Image.LANCZOS)
        if img.width < 60 or img.height < 60:
            return None  # tracking pixels, icons
        out = io.BytesIO()
        img.save(out, "JPEG", quality=IMAGE_QUALITY, optimize=True, progressive=False)
        return out.getvalue()
    except Exception as e:  # noqa: BLE001
        log.debug("image %s skipped: %s", src, e)
        return None


def _process_images(root, base_url: str, max_images: int) -> list[tuple[str, bytes]]:
    images: list[tuple[str, bytes]] = []
    for img in list(root.iter("img")):
        src = img.get("src")
        if not src or src.startswith("data:") or len(images) >= max_images:
            img.drop_tree()
            continue
        data = _download_image(urljoin(base_url, src))
        if data is None:
            img.drop_tree()
            continue
        name = f"img{len(images) + 1}.jpg"
        images.append((name, data))
        for attr in list(img.attrib):
            if attr not in ("alt",):
                del img.attrib[attr]
        img.set("src", f"images/{name}")
        img.set("alt", img.get("alt") or "")
    return images


def clean_html(fragment: str, base_url: str, max_images: int) -> tuple[str, list[tuple[str, bytes]]]:
    """Return (xhtml body fragment, images)."""
    root = lhtml.fragment_fromstring(fragment, create_parent="div")
    _strip_boilerplate(root)  # before cleaning, while class names still exist
    _cleaner(root)
    images = _process_images(root, base_url, max_images)
    # Absolute links so they read sensibly as text; drop empty paragraphs.
    for a in root.iter("a"):
        if a.get("href"):
            a.set("href", urljoin(base_url, a.get("href")))
    for p in list(root.iter("p")):
        if not p.text_content().strip() and not len(p.findall(".//img")):
            p.drop_tree()
    # Serialise as XHTML (well-formed XML for the EPUB).
    parts = [etree.tostring(child, method="xml", encoding="unicode") for child in root]
    lead = html.escape(root.text.strip()) if root.text and root.text.strip() else ""
    body = (f"<p>{lead}</p>" if lead else "") + "".join(parts)
    return body, images


def _fetch_page_html(url: str) -> Optional[str]:
    try:
        resp = http.get(url)
    except Exception as e:  # noqa: BLE001
        log.warning("page fetch failed %s: %s", url, e)
        return None
    if "html" not in resp.headers.get("content-type", "html"):
        return None
    return trafilatura.extract(
        resp.text,
        url=url,
        output_format="html",
        include_images=True,
        include_links=True,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )


def _summary_body(item: Item) -> str:
    summary = _text(item.summary_html or "") or "No summary in the feed."
    return (f"<p>{html.escape(summary)}</p>"
            f"<p class=\"source-link\">Read the full article: {html.escape(item.url)}</p>")


def extract(item: Item, max_images: int = 4, min_read_minutes: float = 0) -> Article:
    """Turn a feed item into an Article, or raise SkipArticle."""
    src = item.source

    for pat in src.skip_if_title_matches:
        if re.search(pat, item.title):
            raise SkipArticle(f"title matches {pat!r}")
    if src.points_min is not None and item.points is not None and item.points < src.points_min:
        raise SkipArticle(f"{item.points} points < {src.points_min}")

    if src.extract == "summary":
        if len(_text(item.summary_html or "").split()) < 12:
            raise SkipArticle("summary too short for a headline card")
        body = _summary_body(item)
        return Article(item=item, title=item.title, author=item.author or src.name,
                       body_html=body, word_count=word_count(body),
                       summary=_text(item.summary_html or "")[:300])

    raw = None
    if src.extract == "feed":
        raw = item.content_html
        if raw and looks_paywalled(raw, src.min_words):
            raise SkipArticle("paid-only post")
        if raw and is_truncated(raw):
            if src.paywall == "substack":
                # Substack sends free posts in full; a cut-off one is paid.
                raise SkipArticle("truncated in feed (paid post)")
            raw = None
        if raw and word_count(raw) < 150:
            raw = None  # feed only has an excerpt; fall back to the page
    if raw is None:
        raw = _fetch_page_html(item.url)
        if not raw:
            raise SkipArticle("could not extract page")

    if looks_paywalled(raw, src.min_words):
        raise SkipArticle("paywall stub")

    body, images = clean_html(raw, item.url, max_images)
    words = word_count(body)
    if words < src.min_words:
        raise SkipArticle(f"only {words} words (< {src.min_words})")
    if src.max_words and words > src.max_words:
        raise SkipArticle(f"{words} words (> {src.max_words})")
    article = Article(item=item, title=item.title, author=item.author or src.name,
                      body_html=body, word_count=words, images=images,
                      summary=_text(item.summary_html or "")[:300])
    if article.read_minutes < min_read_minutes:
        raise SkipArticle(f"{article.read_minutes} min read (< {min_read_minutes})")
    return article
