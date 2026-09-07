"""Test BoxScoreTraditionalV3 with a warmed browser-like NBA session.

Examples:
    python scripts/test_nba_boxscore_curl_cffi.py
    python scripts/test_nba_boxscore_curl_cffi.py --game-id 0040000083 --timeout 30

The script warms the same curl_cffi session on nba.com and the public game
page before calling the BoxScoreTraditionalV3 Stats API endpoint.
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any


NBA_HOME_URL = "https://www.nba.com/"
GAME_URL_TEMPLATE = "https://www.nba.com/game/{game_id}/box-score"
IMPERSONATE_PROFILE = "chrome120"


def elapsed(started: float) -> float:
    return round(time.perf_counter() - started, 3)


def warm_session(game_id: str, timeout: float):
    from curl_cffi import requests as curl_requests

    session = curl_requests.Session(impersonate=IMPERSONATE_PROFILE)
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    results = []
    for url in (NBA_HOME_URL, GAME_URL_TEMPLATE.format(game_id=game_id)):
        started = time.perf_counter()
        response = session.get(url, timeout=timeout, headers=headers)
        results.append(
            {
                "url": url,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "bytes": len(response.content),
                "contains_game_id": game_id in response.text,
                "elapsed_seconds": elapsed(started),
            }
        )
        if response.status_code >= 400:
            break
    cookies = sorted(
        cookie if isinstance(cookie, str) else cookie.name
        for cookie in session.cookies
    )
    return session, {"requests": results, "cookie_names": cookies, "cookie_count": len(cookies)}


def request_boxscore(session: Any, game_id: str, timeout: float) -> dict[str, object]:
    from nba_api.stats.endpoints import boxscoretraditionalv3
    from nba_api.stats.library.http import NBAStatsHTTP

    NBAStatsHTTP.set_session(session)
    started = time.perf_counter()
    try:
        endpoint = boxscoretraditionalv3.BoxScoreTraditionalV3(
            game_id=game_id,
            timeout=timeout,
        )
        payload = endpoint.get_dict()
        frames = endpoint.get_data_frames()
        return {
            "ok": True,
            "endpoint": "BoxScoreTraditionalV3",
            "game_id": game_id,
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
            "endpoint": "BoxScoreTraditionalV3",
            "game_id": game_id,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_seconds": elapsed(started),
        }


def attempt(attempt_number: int, game_id: str, timeout: float) -> dict[str, object]:
    started = time.perf_counter()
    try:
        session, warmup = warm_session(game_id, timeout)
        try:
            boxscore = request_boxscore(session, game_id, timeout)
        finally:
            session.close()
        return {
            "attempt": attempt_number,
            "warmup": warmup,
            "boxscore": boxscore,
            "elapsed_seconds": elapsed(started),
        }
    except Exception as exc:
        return {
            "attempt": attempt_number,
            "warmup": {"ok": False, "error_type": type(exc).__name__, "error": str(exc)},
            "boxscore": {"ok": False, "skipped": True},
            "elapsed_seconds": elapsed(started),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", default="0040000083")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    attempts = [attempt(1, args.game_id, args.timeout)]
    if not attempts[0]["boxscore"].get("ok"):
        attempts.append(attempt(2, args.game_id, args.timeout))

    print(
        json.dumps(
            {
                "impersonate": IMPERSONATE_PROFILE,
                "game_id": args.game_id,
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
