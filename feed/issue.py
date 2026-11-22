"""Stage 6: one EPUB per day holding the whole issue.

Spine: contents page (title, source line and a one-line summary per article),
then one chapter per article, then a "Headlines" chapter of summary-only
cards. The record returned alongside notes where each article sits in the
book (basis points of total size) so reading sessions can be mapped back.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ebooklib import epub

from .epub import CSS_PATH
from .extract import _text
from .models import Article

e = html.escape


@dataclass
class IssueArticle:
    article: Article
    kind: str          # "saved" | "article" | "headline"
    topic_label: str

    @property
    def source_line(self) -> str:
        a = self.article
        if self.kind == "headline":
            return f"{a.item.source.name} · {self.topic_label}"
        return f"{a.item.source.name} · {self.topic_label} · {a.read_minutes} min"


_SENTENCE = re.compile(r".+?[.!?](?=\s|$)")
# Feed "summaries" that are only link boilerplate (aggregators, link blogs).
_NOT_A_SUMMARY = re.compile(r"article url:|comments url:|points:\s*\d|^https?:", re.I)


def one_liner(article: Article, max_len: int = 160) -> str:
    """A short description of the article: the feed's summary when it has one
    that isn't just the title or link boilerplate, else the article's opening."""
    title = " ".join(article.title.lower().split())
    for text in (article.summary, _text(article.body_html)):
        text = " ".join((text or "").split())
        text = re.sub(r"^(by [^.]{0,60}\.|share|subscribe)\s*", "", text, flags=re.I)
        if len(text.split()) < 6 or (len(title) > 15 and text.lower().startswith(title)) or _NOT_A_SUMMARY.search(text):
            continue
        line = ""
        for m in _SENTENCE.finditer(text):  # whole sentences until it says something
            line = text[: m.end()]
            if len(line) >= 60:
                break
        line = line or text
        if len(line) > max_len:
            line = line[: max_len - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        return line
    return ""


def issue_title(catalog_title: str, day: date) -> str:
    # ASCII hyphen: the X3 builds the file name from this title.
    return f"{catalog_title} - {day:%A}"


def _article_xhtml(n: int, ia: IssueArticle) -> str:
    a = ia.article
    body = a.body_html
    for name, _ in a.images:
        body = body.replace(f'src="images/{name}"', f'src="images/a{n:02d}-{name}"')
    byline = a.author if a.author and a.author != a.item.source.name else ""
    meta = " · ".join(filter(None, [byline, ia.source_line]))
    return (
        f"<h1>{e(a.title)}</h1>"
        f'<p class="meta">{e(meta)}</p>'
        f"{body}"
        f'<p class="source-link">{e(a.item.url)}</p>'
        '<p class="back"><a href="contents.xhtml">Back to contents</a></p>'
    )


def _card(ia: IssueArticle) -> str:
    a = ia.article
    summary = one_liner(a, max_len=400) or _text(a.summary)
    return (
        f"<h3>{e(a.title)}</h3>"
        f'<p class="meta">{e(ia.source_line)}</p>'
        + (f"<p>{e(summary)}</p>" if summary else "")
        + f'<p class="source-link">{e(a.item.url)}</p>'
    )


def _contents_xhtml(title: str, day: date, chapters: list[tuple[str, IssueArticle]],
                    headlines: list[IssueArticle], inbox_label: str) -> str:
    parts = [f'<div class="masthead"><h1>{e(title)}</h1><p class="meta">{day:%A, %B} {day.day}, {day:%Y}</p></div>']
    section = None
    for href, ia in chapters:
        label = inbox_label if ia.kind == "saved" else "Today"
        if label != section and (ia.kind == "saved" or section is not None):
            parts.append(f'<h2 class="section">{e(label)}</h2>')
        section = label
        line = one_liner(ia.article)
        parts.append(
            '<div class="toc-entry">'
            f'<p class="toc-title"><a href="{href}">{e(ia.article.title)}</a></p>'
            f'<p class="toc-meta">{e(ia.source_line)}</p>'
            + (f'<p class="toc-summary">{e(line)}</p>' if line else "")
            + "</div>"
        )
    if headlines:
        parts.append('<h2 class="section"><a href="headlines.xhtml">Headlines</a></h2>')
        parts.append('<p class="toc-meta">' + e(" · ".join(h.article.title for h in headlines[:3]))
                     + ("…" if len(headlines) > 3 else "") + "</p>")
    return "".join(parts)


def build_issue(items: list[IssueArticle], path: Path, day: date, slug: str,
                catalog_title: str, inbox_label: str) -> dict:
    """Write the issue EPUB; return its record (title, article positions, sizes)."""
    title = issue_title(catalog_title, day)
    readable = [i for i in items if i.kind != "headline"]
    headlines = [i for i in items if i.kind == "headline"]

    book = epub.EpubBook()
    book.set_identifier(f"urn:morning-feed:{slug}:{day.isoformat()}")
    book.set_title(title)
    book.set_language("en")
    book.add_author(f"{day:%b} {day.day}")
    book.add_metadata("DC", "date", day.isoformat())
    book.add_metadata("DC", "description", f"{len(readable)} articles")
    css = epub.EpubItem(uid="style", file_name="style.css", media_type="text/css",
                        content=CSS_PATH.read_bytes())
    book.add_item(css)

    chapters = [(f"a{n:02d}.xhtml", ia) for n, ia in enumerate(readable, start=1)]
    docs: list[tuple[epub.EpubHtml, str]] = []

    contents = epub.EpubHtml(title="Contents", file_name="contents.xhtml", lang="en")
    contents.content = _contents_xhtml(title, day, chapters, headlines, inbox_label)
    docs.append((contents, contents.content))

    for n, (href, ia) in enumerate(chapters, start=1):
        ch = epub.EpubHtml(title=ia.article.title, file_name=href, lang="en")
        ch.content = _article_xhtml(n, ia)
        docs.append((ch, ch.content))
        for name, data in ia.article.images:
            book.add_item(epub.EpubImage(uid=f"a{n:02d}-{name.split('.')[0]}",
                                         file_name=f"images/a{n:02d}-{name}",
                                         media_type="image/jpeg", content=data))
    if headlines:
        hl = epub.EpubHtml(title="Headlines", file_name="headlines.xhtml", lang="en")
        hl.content = "<h1>Headlines</h1>" + "".join(_card(h) for h in headlines)
        docs.append((hl, hl.content))

    for doc, _ in docs:
        doc.add_item(css)
        book.add_item(doc)
    book.toc = [epub.Link(doc.file_name, doc.title, doc.file_name.split(".")[0]) for doc, _ in docs]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = [doc for doc, _ in docs]

    path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(path), book, {"epub3_pages": False})

    # Position of each chapter as a share of the book, like the reader's progress.
    sizes = [len(text.encode()) for _, text in docs]
    total = sum(sizes)
    bounds, acc = [], 0
    for s in sizes:
        bounds.append((round(acc / total * 10000), round((acc + s) / total * 10000)))
        acc += s
    records = []
    for i, (href, ia) in enumerate(chapters, start=1):
        records.append(_record(ia, *bounds[i]))
    if headlines:
        lo, hi = bounds[-1]
        for h in headlines:
            records.append(_record(h, lo, hi))
    return {
        "date": day.isoformat(),
        "weekday": f"{day:%A}".lower(),
        "title": title,
        "file": path.name,
        "size": path.stat().st_size,
        "sha1": hashlib.sha1(path.read_bytes()).hexdigest(),
        "read_minutes": sum(ia.article.read_minutes for ia in readable),
        "articles": records,
    }


def _record(ia: IssueArticle, start_bp: int, end_bp: int) -> dict:
    a = ia.article
    return {
        "kind": ia.kind, "title": a.title, "source": a.item.source.name,
        "topic": a.item.source.topic, "url": a.item.url, "words": a.word_count,
        "read_minutes": a.read_minutes, "start_bp": start_bp, "end_bp": end_bp,
    }
