"""Shared browser-like HTTP session for all NBA Stats API tools.

NBA Stats is protected by Akamai Bot Manager.  The stock ``requests`` TLS
fingerprint used by nba_api is frequently rejected even when its HTTP headers
are browser-like.  curl_cffi provides a browser TLS fingerprint and shares the
warmup cookies acquired from nba.com with every nba_api endpoint call.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import TypeVar


logger = logging.getLogger(__name__)

WARMUP_URL = "https://www.nba.com/stats/"
IMPERSONATE_PROFILE = "chrome120"
WARMUP_TIMEOUT_SECONDS = 20
LIVE_DATA_TIMEOUT_SECONDS = 20

T = TypeVar("T")
_session_lock = threading.RLock()
_session = None


def _new_session():
    """Create, warm up, and register a curl_cffi session for nba_api."""
    from curl_cffi import requests as curl_requests
    from nba_api.stats.library.http import NBAStatsHTTP

    session = curl_requests.Session(impersonate=IMPERSONATE_PROFILE)
    response = session.get(
        WARMUP_URL,
        timeout=WARMUP_TIMEOUT_SECONDS,
        headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    )
    if response.status_code >= 400:
        session.close()
        raise RuntimeError(f"NBA warmup returned HTTP {response.status_code}")
    NBAStatsHTTP.set_session(session)
    return session


def _ensure_session(force_refresh: bool = False):
    global _session
    if _session is not None and not force_refresh:
        return _session

    previous = _session
    _session = _new_session()
    if previous is not None:
        try:
            previous.close()
        except Exception:  # pragma: no cover - cleanup must not hide a ready session
            logger.debug("Failed to close replaced NBA HTTP session", exc_info=True)
    return _session


def _should_refresh(exc: Exception) -> bool:
    """Recognize endpoint failures that commonly indicate expired/WAF state."""
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    indicators = (
        "timeout",
        "connection",
        "ssl",
        "jsondecode",
        "invalidresponse",
        "403",
        "forbidden",
        "access denied",
        "not a valid json",
    )
    return any(token in name or token in message for token in indicators)


def run_nba_api(operation: Callable[[], T]) -> T:
    """Run one nba_api operation using a warmed browser-like session.

    Calls are serialized because nba_api stores its session globally.  On a
    likely WAF/session failure the old cookies are discarded, a fresh warmup is
    performed, and the operation is retried exactly once.
    """
    with _session_lock:
        _ensure_session()
        try:
            return operation()
        except Exception as first_error:
            if not _should_refresh(first_error):
                raise
            logger.info(
                "NBA API request failed with %s; refreshing browser session and retrying once",
                type(first_error).__name__,
            )
            _ensure_session(force_refresh=True)
            return operation()


def fetch_nba_live_json(url: str) -> dict:
    """Fetch an NBA CDN live-data document with the browser-like session.

    NBA game pages use CDN documents for their Box Score presentation.  Reuse
    the same warmed session as the stats endpoints so Akamai cookies and the
    browser TLS fingerprint are consistent across both hosts.
    """
    with _session_lock:
        for attempt in range(2):
            session = _ensure_session(force_refresh=attempt == 1)
            try:
                response = session.get(
                    url,
                    timeout=LIVE_DATA_TIMEOUT_SECONDS,
                    headers={"Accept": "application/json, text/plain, */*"},
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("NBA live response is not a JSON object")
                return payload
            except Exception:
                if attempt == 1:
                    raise
                logger.info("NBA CDN request failed; refreshing browser session and retrying once", exc_info=True)
    raise RuntimeError("NBA CDN request failed without an exception")  # pragma: no cover
