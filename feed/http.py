from __future__ import annotations

import requests

USER_AGENT = "Mozilla/5.0 (compatible; MorningFeed/0.1; personal e-reader digest)"
TIMEOUT = 20

_session = None


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.8"})
    return _session


def get(url: str, **kw) -> requests.Response:
    kw.setdefault("timeout", TIMEOUT)
    resp = session().get(url, **kw)
    resp.raise_for_status()
    return resp
