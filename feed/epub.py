"""Stage 6: one small EPUB per article."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from ebooklib import epub

from .models import Article

CSS_PATH = Path(__file__).resolve().parent.parent / "templates" / "article.css"


def slugify(text: str, max_len: int = 40) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:max_len].rstrip("-") or "article"


def article_filename(index: int, article: Article) -> str:
    return f"{index:02d}-{slugify(article.item.source.name, 24)}-{slugify(article.title, 40)}.epub"


def build_epub(article: Article, path: Path, issue_date: datetime, topic_label: str = "") -> Path:
    item = article.item
    e = html.escape
    book = epub.EpubBook()
    book.set_identifier("urn:sha1:" + hashlib.sha1(item.url.encode()).hexdigest())
    book.set_title(article.title)
    book.set_language("en")
    book.add_author(article.author)
    book.add_metadata("DC", "publisher", item.source.name)
    book.add_metadata("DC", "subject", item.source.topic)
    book.add_metadata("DC", "source", item.url)
    pub = item.published or issue_date
    book.add_metadata("DC", "date", pub.strftime("%Y-%m-%d"))
    if article.summary:
        book.add_metadata("DC", "description", article.summary)

    css = epub.EpubItem(uid="style", file_name="style.css", media_type="text/css",
                        content=CSS_PATH.read_bytes())
    book.add_item(css)

    title_page = epub.EpubHtml(title="Title", file_name="title.xhtml", lang="en")
    title_page.content = (
        '<div class="titlepage">'
        f"<h1>{e(article.title)}</h1>"
        f'<p class="byline">{e(article.author)}</p>'
        f'<p class="meta">{e(item.source.name)} · {e(topic_label or item.source.topic)} · {article.read_minutes} min</p>'
        f'<p class="meta">{pub:%B %-d, %Y}</p>'
        f'<p class="url">{e(item.url)}</p>'
        "</div>"
    )
    title_page.add_item(css)

    body = epub.EpubHtml(title=article.title, file_name="article.xhtml", lang="en")
    body.content = f"<h1>{e(article.title)}</h1>{article.body_html}"
    body.add_item(css)

    book.add_item(title_page)
    book.add_item(body)
    for name, data in article.images:
        book.add_item(epub.EpubImage(uid=name.split(".")[0], file_name=f"images/{name}",
                                     media_type="image/jpeg", content=data))

    book.toc = [epub.Link("article.xhtml", article.title, "article")]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = [title_page, body]

    path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(path), book, {"epub3_pages": False})
    return path
