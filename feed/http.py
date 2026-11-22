from __future__ import annotations

import time

import requests

# A current desktop browser's headers. Some hosts refuse obvious bots from cloud
# IP ranges (e.g. GitHub Actions) but serve a normal browser request.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "application/rss+xml,application/atom+xml,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}
TIMEOUT = 20          # seconds per connect/read
DEADLINE = 45         # seconds for the whole download
MAX_BYTES = 15 * 1024 * 1024

_session = None


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
    return _session


# Refusals worth one retry with plain headers: some hosts reject a request that
# claims to be a browser but doesn't look like one (Hacker News answers 419).
RETRY_PLAIN = {403, 419, 429}


def get(url: str, deadline: float = DEADLINE, **kw) -> requests.Response:
    """GET with a total time and size limit, so a slow-drip server can't stall a build."""
    try:
        return _get(url, deadline, **kw)
    except requests.HTTPError as e:
        if e.response is None or e.response.status_code not in RETRY_PLAIN or "headers" in kw:
            raise
        return _get(url, deadline, headers={"User-Agent": requests.utils.default_user_agent()}, **kw)


def _get(url: str, deadline: float, **kw) -> requests.Response:
    kw.setdefault("timeout", TIMEOUT)
    start = time.monotonic()
    resp = session().get(url, stream=True, **kw)
    try:
        resp.raise_for_status()
        chunks, size = [], 0
        for chunk in resp.iter_content(64 * 1024):
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_BYTES:
                raise requests.RequestException(f"response over {MAX_BYTES // 1048576} MB")
            if time.monotonic() - start > deadline:
                raise requests.Timeout(f"download took over {deadline}s")
        resp._content = b"".join(chunks)
        resp._content_consumed = True
    finally:
        resp.close()
    return resp
