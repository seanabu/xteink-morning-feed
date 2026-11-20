# Xteink Morning Feed

Builds a small set of clean, individually downloadable article EPUBs each morning and
publishes them as a static OPDS catalog on GitHub Pages, so an Xteink X3 (running
CrossPoint firmware) can pull a bounded morning read over Wi‑Fi. See [SPEC.md](SPEC.md)
for the full design.

**Status:** milestones 1 (profiles + sources check) and 2 (sample catalog, end to end)
are done. The daily GitHub Actions job, ranking and dedupe state arrive in milestone 3.

## Setup

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12 is picked up from `.python-version`).

```bash
uv sync
```

Secrets (only needed for later milestones) go in a local `.env`, which is git-ignored,
or in GitHub Actions secrets: `ANTHROPIC_API_KEY` (LLM ranking), `NYT_COOKIE` (full-text NYT).

## Usage

Validate a profile and test every feed in it (items and last-post date per feed;
`verify` entries are flagged):

```bash
uv run python build.py --profile sean --check
```

Build a sample catalog with N articles into `site/`:

```bash
uv run python build.py --profile sean --sample 6 --base-url https://www.seanabu.com/xteink-morning-feed
```

`--base-url` makes every OPDS link absolute, which low-memory OPDS clients handle more
reliably. Without it, links are relative.

Publish `site/` to the `gh-pages` branch (this replaces the branch contents):

```bash
scripts/publish_pages.sh
```

Run the tests:

```bash
uv run pytest
```

## Catalog layout

```
site/<profile>/opds/root.xml          navigation feed: one folder per date, newest first
site/<profile>/opds/YYYY-MM-DD.xml    acquisition feed for that date
site/<profile>/opds/flat.xml          fallback: last 3 days in one list, titles prefixed "11/20 · "
site/<profile>/YYYY-MM-DD/*.epub      one EPUB per article
site/<profile>/YYYY-MM-DD/index.json  manifest the feeds are regenerated from
```

Point the X3 at `https://<github-user>.github.io/<repo>/<profile>/opds/root.xml`. If
CrossPoint can't open nested folders, use `.../opds/flat.xml` instead.

## Profiles

The code holds no sources, topics or keywords. Each reader is a folder under `profiles/`:

- `profile.yaml`: settings (timezone, daily target, topic cap, layout, …)
- `sources.yaml`: feeds, each with `tier` (`always` | `filtered`), `topic`, `weight` and
  per-source options: `paywall`, `extract` (`feed` | `page` | `summary`), `min_words`,
  `max_words`, `skip_if_title_matches`, `points_min`, `verify`, `enabled`, `notes`
- `interests.yaml`: keywords per topic and a blocklist

Unknown keys are a validation error. To add a reader, copy `profiles/_template/` to
`profiles/<name>/`, edit the three files, and run `--check`.

## Code

```
build.py          entry point
feed/config.py    profile schema (pydantic) and loader
feed/fetch.py     feed download + parsing
feed/check.py     --check report
feed/extract.py   paywall detection, page extraction, HTML cleanup, image downscaling
feed/epub.py      one EPUB per article
feed/opds.py      OPDS 1.2 navigation / acquisition / flat feeds
feed/sample.py    milestone 2 sample build
tests/            uses tests/fixtures/profile only; never reads real profiles
```
