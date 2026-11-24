# Xteink Morning Feed

Builds one EPUB each morning, a daily issue of 10–15 clean articles with a contents page,
and publishes it as a static OPDS catalog on GitHub Pages, so an Xteink X3 (running
CrossPoint firmware) can pull a bounded morning read over Wi‑Fi in one download. See [SPEC.md](SPEC.md)
for the full design.

**Status:** milestones 1–3 are done: daily GitHub Actions job, keyword ranking, dedupe
state, a read-later inbox from the iPhone share sheet, and learning from what gets read
on the X3 (see [device/README.md](device/README.md)).

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

Build today's issue into `site/`, with state (dedupe, inbox, reading history) in `state/`:

```bash
uv run python build.py --profile sean --daily
```

Publish `site/` to the `gh-pages` branch (this replaces the branch contents):

```bash
scripts/publish_pages.sh
```

Run the tests:

```bash
uv run pytest
```

## Daily job

`.github/workflows/daily.yml` is scheduled at several times between 10:23 and 15:23 UTC,
because GitHub often starts scheduled runs hours late or drops them. The first run that
happens builds the day's issue and the later ones skip (`--if-missing`). Running it by
hand (Actions → Daily issue → Run workflow) always rebuilds. It checks out the `state`
branch and the current `gh-pages` site, builds every profile, pushes state, and republishes.

Catalog links are absolute (`--base-url`, or `SITE_URL`; CI reads it from the Pages
settings). CrossPoint appends relative links to the feed URL as-is, so they 404.

`.github/workflows/record.yml` takes one event at a time (a saved link from the phone, or
a reading session from the X3) and writes it to the `state` branch.

## Catalog layout

```
site/<profile>/opds/root.xml                      the last 7 issues, newest first
site/<profile>/issues/YYYY-MM-DD-weekday.epub     one issue per day
site/<profile>/issues/index.json                  manifest the feed is regenerated from
```

Each issue is titled "Morning Feed - <Weekday>". With CrossPoint's download file name
set to **Title**, next week's Monday issue replaces this one on the device, so the X3
never holds more than seven. Inside: a contents page (saved links first, then today's
articles with source, topic, read time and a one-line summary), one chapter per article,
and a Headlines chapter of summary-only cards.

Point the X3 at `https://<pages host>/<repo>/<profile>/opds/root.xml`.

State on the `state` branch, per profile: `seen.json` (dedupe, 30 days), `issues/`
(what went into each issue and where it sits in the book), `events/` (saved links and
reading sessions), `learned.json` (current learned weights).

## Profiles

The code holds no sources, topics or keywords. Each reader is a folder under `profiles/`:

- `profile.yaml`: settings (timezone, daily target, topic and source caps, headline cap,
  inbox label, learning strength, …)
- `sources.yaml`: feeds, each with `tier` (`always` | `filtered`), `topic`, `weight` and
  per-source options: `paywall`, `extract` (`feed` | `page` | `summary`), `min_words`,
  `max_words`, `skip_if_title_matches`, `points_min`, `verify`, `enabled`, `notes`
- `interests.yaml`: keywords per topic and a blocklist

Unknown keys are a validation error. To add a reader, copy `profiles/_template/` to
`profiles/<name>/`, edit the three files, and run `--check`. The daily job builds every
profile folder except `_template`.

## Code

```
build.py          entry point
feed/config.py    profile schema (pydantic) and loader
feed/fetch.py     feed download + parsing
feed/check.py     --check report
feed/rank.py      dedupe and keyword ranking
feed/extract.py   paywall detection, page extraction, HTML cleanup, image downscaling
feed/issue.py     the daily issue EPUB and one-line summaries
feed/opds.py      OPDS 1.2 catalog of issues
feed/learn.py     reading sessions -> per-article coverage -> weight multipliers
feed/state.py     state folder (seen, issues, events)
feed/record.py    records one phone/X3 event (stdlib only; used by record.yml)
feed/daily.py     the daily pipeline
device/           CrossPoint plugin + iPhone shortcut instructions
tests/            uses tests/fixtures/profile only; never reads real profiles
```
