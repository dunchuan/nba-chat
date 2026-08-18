"""Test ScheduleLeagueV2 through curl_cffi browser impersonation.

The script creates a Chrome-like TLS session, warms it up on nba.com to
receive Akamai cookies, then injects that session into nba_api. If the first
Stats API call does not produce valid JSON, it creates a fresh session and
retries exactly once.

Examples:
    python scripts/test_nba_api_curl_cffi.py
    python scripts/test_nba_api_curl_cffi.py --season 1999-00 --timeout 30
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any


WARMUP_URL = "https://www.nba.com/stats/"


def elapsed(started: float) -> float:
    return round(time.perf_counter() - started, 3)


def create_warmed_session(impersonate: str, timeout: float):
    """Return a curl_cffi session after warming it up on nba.com."""
    from curl_cffi import requests as curl_requests

    session = curl_requests.Session(impersonate=impersonate)
    started = time.perf_counter()
    response = session.get(
        WARMUP_URL,
        timeout=timeout,
        headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    )
    # curl_cffi's cookie container iterates cookie names as strings, whereas
    # some requests-compatible containers yield Cookie objects. Keep the
    # diagnostic compatible with both without printing cookie values.
    cookies = sorted(
        cookie if isinstance(cookie, str) else cookie.name
        for cookie in session.cookies
    )
    return session, {
        "url": WARMUP_URL,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "cookie_names": cookies,
        "cookie_count": len(cookies),
        "elapsed_seconds": elapsed(started),
    }


def schedule_request(session: Any, season: str, timeout: float) -> dict[str, object]:
    """Inject one session into nba_api and call the same ScheduleLeagueV2 API."""
    from nba_api.stats.endpoints import scheduleleaguev2
    from nba_api.stats.library.http import NBAStatsHTTP

    NBAStatsHTTP.set_session(session)
    started = time.perf_counter()
    try:
        endpoint = scheduleleaguev2.ScheduleLeagueV2(season=season, timeout=timeout)
        payload = endpoint.get_dict()
        frames = endpoint.get_data_frames()
        return {
            "ok": True,
            "endpoint": "ScheduleLeagueV2",
            "season": season,
            "url": endpoint.nba_response.get_url(),
            "status_code": getattr(endpoint.nba_response, "_status_code", None),
            "top_level_keys": sorted(payload) if isinstance(payload, dict) else [],
            "frame_count": len(frames),
            "frame_sizes": [len(frame) for frame in frames],
            "elapsed_seconds": elapsed(started),
        }
    except Exception as exc:
        return {
            "ok": False,
            "endpoint": "ScheduleLeagueV2",
            "season": season,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_seconds": elapsed(started),
        }


def attempt(attempt_number: int, impersonate: str, season: str, timeout: float) -> dict[str, object]:
    try:
        session, warmup = create_warmed_session(impersonate, timeout)
        result = schedule_request(session, season, timeout)
        return {"attempt": attempt_number, "warmup": warmup, "scheduleleaguev2": result}
    except Exception as exc:
        return {
            "attempt": attempt_number,
            "warmup": {"ok": False, "error_type": type(exc).__name__, "error": str(exc)},
            "scheduleleaguev2": {"ok": False, "skipped": True},
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", default="1999-00")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--impersonate", default="chrome120")
    args = parser.parse_args()

    attempts = [attempt(1, args.impersonate, args.season, args.timeout)]
    if not attempts[0]["scheduleleaguev2"].get("ok"):
        attempts.append(attempt(2, args.impersonate, args.season, args.timeout))

    print(
        json.dumps(
            {
                "impersonate": args.impersonate,
                "retry_policy": "retry once after a fresh warmup when attempt 1 fails",
                "attempts": attempts,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
