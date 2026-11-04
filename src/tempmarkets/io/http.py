"""Shared HTTP session: GET only, polite UA, retries."""
from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "tempmarkets-research/0.1 (read-only analysis)"

_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers["User-Agent"] = USER_AGENT
        retry = Retry(total=4, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET",))
        s.mount("https://", HTTPAdapter(max_retries=retry))
        _session = s
    return _session


def get(url: str, params: dict | None = None, timeout: float = 60) -> requests.Response:
    r = session().get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r
