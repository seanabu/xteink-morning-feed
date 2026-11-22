# Xteink Morning Feed — Tech Spec

Nov 20, 2026

> **Revision, Nov 21 2026 (after testing on the X3).** Downloading articles one at a time
> was too slow on the device. The catalog now holds **one EPUB per day**, titled
> "Morning Feed - <Weekday>", with a contents page that gives each article's source, topic,
> read time and a one-line summary. Next week's issue for a weekday replaces this week's
> on the device. Also added: a read-later inbox fed by an iPhone share-sheet shortcut, and
> reading-session reports from a CrossPoint plugin that tune source and topic weights. Both
> go through the `Record` workflow into a `state` branch. Sections below that describe
> per-article EPUBs and dated folders are superseded; see README.md and device/README.md.

## Overview

A GitHub Actions job builds 12–15 clean, individually downloadable article EPUBs every morning and publishes them as an OPDS catalog on GitHub Pages, so the Xteink X3 replaces phone scrolling.

**Goal:** a bounded, high-signal morning read on an e-ink device, with no feed to scroll and no notifications.

**Non-goals (v1):**

- Books. They stay in the normal on-device library (SD card, Wi‑Fi upload, Calibre).
- Push delivery to the device. The reader pulls from the catalog.
- Comments, images-heavy pages, video, podcasts.
- Paid content the user doesn't subscribe to.

**Success criteria:**

- By 6:00am Pacific each day, a new dated folder exists in the catalog with 12–15 articles.
- Every article opens cleanly on the X3 (readable text, working title, no paywall stubs or cookie banners).
- Running cost is $0, or under $2/month if LLM ranking is enabled.
- After a week of use, the user reaches for the X3 instead of the phone in the morning.

## User experience

Each morning the user opens the OPDS browser, taps today's date, and downloads only the articles they want, one at a time.

1. Wake the X3 on home Wi‑Fi and open the saved "Morning Feed" OPDS server.
2. The root shows dated folders, newest first: **Fri Nov 20**, **Thu Nov 19**, … (last 7 days).
3. A date opens a list of that day's articles. Each entry shows title, source, topic and read time, e.g. *"Why the Thunder switch everything · Clear Basketball Analysis · NBA · 9 min"*.
4. Tapping an entry downloads one small EPUB (<200 KB) and opens it like a book.
5. Optional: a **"Whole day"** EPUB at the top of each date for offline reading (plane, no Wi‑Fi).

Ordering inside a day: always-include writers first, then filtered articles by rank score. Topic mix is capped so no single topic takes more than 5 slots.

Books are unaffected: they live in the device's normal library and never enter the catalog.

**Fallback if CrossPoint's OPDS browser doesn't handle nested folders:** a flat feed of the last 3 days, with titles prefixed by date ("11/20 · Title").

## Sources

Sources come in two tiers: writers the user already subscribes to always get in, and a larger pool is filtered and ranked by topic. Every URL is checked automatically in milestone 1; anything marked *verify* still needs its exact feed confirmed.

**Always include** (skip the ranker, about 8–10 posts a week combined):

| Source | Topic | Feed URL | Notes |
| --- | --- | --- | --- |
| Derek Thompson | Econ / politics | https://www.derekthompson.org/feed | Some posts paid |
| Kyla Scanlon | Economics | https://kyla.substack.com/feed | verify |
| Vanishing Gradients (Hugo Bowne-Anderson) | DS / AI | https://hugobowne.substack.com/feed | Skip podcast-only posts |
| Sinéad Bovell | AI and society | https://sineadbovell.substack.com/feed | Free |
| Moontower (Kris Abdelmessih) | Markets | https://moontower.substack.com/feed | verify |
| Worse on Purpose | Business / consumer | https://rss.beehiiv.com/feeds/J17ICFTI1f.xml | beehiiv, weekly Wed |
| The Lowe Post (Zach Lowe) | NBA | verify | $10/mo; free posts only |

**Filtered pool** (ranked by topic fit):

| Source | Topic | Feed URL | Notes |
| --- | --- | --- | --- |
| Hacker News — Show HN | AI / builds | https://hnrss.org/show?points=100 | Main "cool projects" source |
| Hacker News — front page | AI / DS | https://hnrss.org/frontpage?points=150 | Keyword-filtered |
| Simon Willison | AI | https://simonwillison.net/atom/everything/ | Long entries only, skip short links |
| Latent Space | AI engineering | https://www.latent.space/feed | verify |
| Interconnects (Nathan Lambert) | AI | https://www.interconnects.ai/feed | verify |
| Ahead of AI (Sebastian Raschka) | AI / ML | https://magazine.sebastianraschka.com/feed | verify |
| One Useful Thing (Ethan Mollick) | AI | https://www.oneusefulthing.org/feed | verify |
| Statsig blog | Experimentation | verify | |
| Statistical Modeling (Andrew Gelman) | Statistics | https://statmodeling.stat.columbia.edu/feed/ | verify |
| Benn Stancil | Data | https://benn.substack.com/feed | verify |
| Eugene Yan | ML / DS | https://eugeneyan.com/rss/ | verify |
| Noahpinion | Economics | https://www.noahpinion.blog/feed | |
| Marginal Revolution | Economics | https://marginalrevolution.com/feed | High volume; rank hard |
| Apricitas Economics | Economics | https://www.apricitas.io/feed | verify |
| Calculated Risk | Economics | verify | |
| Strength In Numbers (G. Elliott Morris) | Politics data | https://www.gelliottmorris.com/feed | Some posts paid |
| Silver Bulletin | Politics | https://www.natesilver.net/feed | Many posts paid |
| The Argument (with Split Ticket) | Politics | verify | |
| The Dispatch | Politics (center-right) | verify | Balance |
| The Ringer — NBA | NBA | verify | Site moved platforms |
| Clear Basketball Analysis | NBA | https://clearbasketballanalysis.substack.com/feed | |
| Charlie's Court | NBA tactics | https://charliescourt.substack.com/feed | |
| Third Apron (Yossi Gozlan) | NBA cap | verify | |
| The RunBack | NBA analytics | https://therunback.substack.com/feed | |
| America's War Game (Ian Boyd) | CFB scheme | https://americaswargame.substack.com/feed | Many posts paid |
| CFBNumbers | CFB analytics | https://cfbnumbers.substack.com/feed | Free |
| Roll 'Bama Roll | Alabama | verify | Fan blog; filter to analysis |
| NYT — Politics, Upshot, Economy | News | https://rss.nytimes.com/services/xml/rss/nyt/Upshot.xml (and Politics.xml, Economy.xml) | See NYT decision |

These tables are one user's profile, not part of the code. They become `profiles/sean/sources.yaml`; see Profiles and configuration.

## Architecture

Everything runs on free GitHub infrastructure: Actions does the work once a day, Pages serves static files, and the X3 pulls them over Wi‑Fi. No server or VM.

```
Sources (RSS/Atom) ──▶ build.py on GitHub Actions (daily, 4am PT) ──▶ GitHub Pages (OPDS + EPUBs) ◀── Xteink X3 (CrossPoint OPDS, pulls on tap)
                              ▲                ▲
                              │                ┆ (optional, v2)
                      state/seen.json     Claude Haiku ranking
```

The X3 pulls; nothing is pushed to it.

## Pipeline

One Python script (`build.py`) runs seven stages in order and fails soft: one broken feed logs a warning and never blocks the issue.

1. **Fetch.** Pull every feed in `sources.yaml` with `feedparser`; keep items published since the last successful run (window: 36 hours, to survive a missed day).
2. **Dedupe.** Drop URLs already in `state/seen.json` (kept 30 days). Collapse the same story from several sources by normalized URL, then by title similarity over 0.85.
3. **Paywall skip.** Drop items whose feed entry or page signals paid-only: Substack `audience: only_paid`, a "This post is for paid subscribers" marker, or extracted body under 300 words with a subscribe prompt.
4. **Extract.** Use full feed content when the feed has it (most Substacks do); otherwise fetch the page and extract with `trafilatura`. Strip scripts, embeds, share buttons and newsletter footers. Keep up to 4 images per article, downscaled to 480 px grayscale JPEG; drop the rest.
5. **Rank and fill.**
   - Always-include items go straight in.
   - Filtered items get a topic and a score. **v1:** keyword and source weights from `interests.yaml`. **v2 (optional):** an LLM call (Claude Haiku) that scores 0–10 for "thoughtful analysis vs. drama/news" against the user's interest profile, and writes a one-line summary.
   - Fill to the daily target (default 14) with per-topic caps (default 5) and a minimum read time (3 min) to filter out link posts.
6. **Build EPUBs.** One EPUB per article with `ebooklib`: title page (title, author, source, date, original URL as text), body, simple CSS (serif, no fixed widths). Filename: `YYYY-MM-DD/NN-source-slug.epub`. Optional `whole-day.epub` with a table of contents.
7. **Write OPDS and publish.** Generate static OPDS 1.2 Atom XML: a root navigation feed listing dates, plus one acquisition feed per date with title, author, summary and an `application/epub+zip` link per article. Delete folders older than 7 days. Commit to the `gh-pages` branch.

**Schedule:** cron `0 12 * * *` UTC (4am Pacific standard time; adjust for daylight saving) plus a manual "Run workflow" button.

**NYT handling (pending decision):** headlines-only puts the Times summary and a link in a short EPUB. Full-text mode reads an `NYT_COOKIE` secret and fetches pages as the logged-in user, for personal use only; it's a gray area under NYT's terms, and the cookie needs refreshing every few weeks.

## Repo layout and config

A single public repo holds code on `main` and the generated catalog on `gh-pages`; nothing secret is ever written to `gh-pages`.

```
morning-feed/
  .github/workflows/daily.yml   # cron + manual trigger, one job per profile
  build.py                      # entry point: build.py --profile <name>
  feed/
    fetch.py  extract.py  rank.py  epub.py  opds.py
  profiles/
    _template/                  # copy this to add a user
      profile.yaml  sources.yaml  interests.yaml
    sean/
      profile.yaml  sources.yaml  interests.yaml
  state/<profile>/seen.json     # dedupe history per profile
  templates/article.css
  tests/fixtures/profile/       # test-only profile; tests never read real profiles
```

**`sources.yaml` entry:**

```yaml
- name: Clear Basketball Analysis
  url: https://clearbasketballanalysis.substack.com/feed
  tier: filtered        # or: always
  topic: nba
  weight: 1.2
```

**`interests.yaml`** holds topics with positive keywords ("pick-and-roll", "defensive scheme", "SP+", "A/B test", "causal inference", "open-source", "Show HN") and a blocklist for drama ("trade rumors", "beef", "fires back", "recruiting commit").

**Secrets (GitHub repo settings → Secrets and variables → Actions):**

- `ANTHROPIC_API_KEY`: only for v2 LLM ranking.
- `NYT_COOKIE`: only if full-text NYT is chosen.

**Privacy:** GitHub Pages sites are public. The catalog URL isn't linked anywhere, but anyone who finds it can read the EPUBs. That's acceptable for public articles; full-text NYT copies would make it a real problem (see Open decisions).

## Profiles and configuration

The code contains no sources, topics, keywords or user settings: everything that differs between readers lives in a profile folder, so adding a user means copying a folder, not editing Python.

**Rules for the code:**

- No feed URL, source name, topic, keyword or number of articles appears in `.py` files. Lint check in CI: fail the build if `feed/` contains `http` or any source name from a profile.
- Topics are free-form strings defined by the profile. The ranker, caps and EPUB metadata treat them generically; nothing special-cases "nba" or "nyt".
- Source behaviors are options on the source entry, not code branches: `paywall: substack | none`, `extract: feed | page`, `min_words`, `skip_if_title_matches`, `points_min` for HN-style feeds.
- Unknown keys in a profile cause a clear validation error (pydantic or JSON Schema), so typos don't fail silently.

**`profile.yaml`** (per-user settings; all optional with defaults):

```yaml
name: Sean
timezone: America/Los_Angeles
daily_target: 14
topic_cap: 5
retention_days: 7
min_read_minutes: 3
ranking: keywords        # or: llm
whole_day_epub: true
catalog_layout: nested   # or: flat
nyt_mode: headlines      # or: off, full_text
```

**`sources.yaml`** lists feeds with `tier`, `topic`, `weight` and the per-source options above. **`interests.yaml`** holds topics, keywords and the blocklist.

**Adding a user:**

1. Copy `profiles/_template/` to `profiles/<name>/` and edit the three files.
2. Run `python build.py --profile <name> --check` to validate config and test every feed.
3. The workflow builds every folder under `profiles/` except `_template`, so nothing else needs editing.
4. Their catalog appears at `https://<github-user>.github.io/morning-feed/<name>/opds/root.xml`.

**For someone running their own copy:** they fork the repo, delete `profiles/sean/`, and add their own profile. Nothing else changes.

**Optional later:** starter packs (`packs/nba-analysis.yaml`, `packs/ai-builders.yaml`) that a profile pulls in with `include: [nba-analysis]`, so new users start from curated sets instead of a blank list.

## Device setup

The X3 needs CrossPoint firmware for OPDS; Xteink's stock OPDS support covers the X4 Pro and X4 Classic, not the X3.

- [ ] Back up the stock firmware with the [X3 flash tool](https://x3.crosspointreader.com/) (Chrome or Edge on a computer, USB).
- [ ] If flashing is blocked, run the unlock tool from [crosspointreader.com](https://crosspointreader.com/) first. International units ship with USB flashing disabled.
- [ ] Flash CrossPoint. Later updates arrive over the air.
- [ ] Join home Wi‑Fi on the device.
- [ ] Add an OPDS server: name "Morning Feed", URL `https://<github-user>.github.io/morning-feed/sean/opds/root.xml`.
- [ ] Test against the sample catalog from milestone 2: does a date folder open into its article list? Does a single EPUB download and open? Record the result here; it decides nested vs. flat catalog.

Books keep working as before through the SD card, browser upload at `crosspoint.local`, or Calibre.

Flashing third-party firmware isn't supported by Xteink, and they may not honor the warranty. Stock firmware can be flashed back from the same page.

## Open decisions, risks and milestones

Three decisions are still open; none blocks milestones 1–3.

**Open decisions:**

- [ ] **NYT:** headlines-only (recommended) or full text via cookie. Full text plus a public Pages site means paywalled articles sitting on a public URL, so it would need a private host (e.g. Cloudflare Pages with Access, or a token in the URL path).
- [ ] **Ranking:** keyword rules only, or add LLM scoring (about $1–2/month with Claude Haiku).
- [ ] **Source cuts:** confirm which filtered-pool feeds to keep (AL.com was left out as too noisy).

**Risks:**

- Feeds change URLs or break silently. Mitigation: the build logs per-source item counts and opens a GitHub issue if a source returns 0 items for 7 days.
- Extraction quality varies by site. Mitigation: per-source extractor overrides and a fixture test per source.
- CrossPoint's OPDS browser may not handle nested navigation or large feeds on its low-memory chip. Mitigation: the flat-feed fallback, at most 20 entries per feed.
- Hacker News links point at arbitrary sites, and some won't extract well. Mitigation: skip if under 300 words or over 15,000.

**Build milestones for Claude Code:**

1. **Profiles and sources check.** Profile loader with schema validation, plus `build.py --profile sean --check`, which tests every feed in the profile, flags the *verify* entries, and prints items and last-post date per feed.
2. **One article, end to end.** Fetch, extract and EPUB for 5 sample articles, plus a static OPDS catalog with one date folder. Publish to Pages and test on the X3.
3. **Daily job.** Full pipeline with keyword ranking, dedupe state, retention, GitHub Actions cron.
4. **Polish.** Whole-day EPUB, per-source extractor fixes, health issue on broken feeds.
5. **Optional.** LLM ranking and summaries; NYT mode per decision.
