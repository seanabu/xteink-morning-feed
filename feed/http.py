from __future__ import annotations

import time

import requests

USER_AGENT = "Mozilla/5.0 (compatible; MorningFeed/0.1; personal e-reader digest)"
TIMEOUT = 20          # seconds per connect/read
DEADLINE = 45         # seconds for the whole download
MAX_BYTES = 15 * 1024 * 1024

_session = None


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.8"})
    return _session


def get(url: str, deadline: float = DEADLINE, **kw) -> requests.Response:
    """GET with a total time and size limit, so a slow-drip server can't stall a build."""
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
