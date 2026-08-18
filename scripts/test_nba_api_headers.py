"""Probe ScheduleLeagueV2 with browser-like NBA Stats request headers.

Examples:
    python scripts/test_nba_api_headers.py
    python scripts/test_nba_api_headers.py --season 1999-00 --timeout 30

This script calls the exact Stats API URL directly. It does not call the
application cache or LangGraph agent, so it isolates the network/WAF result.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request


NBA_STATS_HEADERS = {
    "Host": "stats.nba.com",
    "Connection": "keep-alive",
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Accept-Language": "en-US,en;q=0.9",
}
BODY_PREVIEW_LIMIT = 4_000


def elapsed(started: float) -> float:
    return round(time.perf_counter() - started, 3)


def describe_body(raw_body: bytes) -> dict[str, object]:
    text = raw_body.decode("utf-8", errors="replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {
            "json": {"ok": False},
            "raw_body_preview": text[:BODY_PREVIEW_LIMIT],
            "raw_body_truncated": len(text) > BODY_PREVIEW_LIMIT,
        }
    return {
        "json": {
            "ok": True,
            "top_level_keys": sorted(payload) if isinstance(payload, dict) else [],
        }
    }


def request_schedule(season: str, timeout: float) -> dict[str, object]:
    url = "https://stats.nba.com/stats/scheduleleaguev2?" + urllib.parse.urlencode(
        {"LeagueID": "00", "Season": season}
    )
    started = time.perf_counter()
    request = urllib.request.Request(url, headers=NBA_STATS_HEADERS)
    base = {"url": url, "request_headers": NBA_STATS_HEADERS}
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw_body = response.read()
            return {
                **base,
                "ok": True,
                "status_code": response.status,
                "content_type": response.headers.get("content-type", ""),
                "bytes": len(raw_body),
                "elapsed_seconds": elapsed(started),
                **describe_body(raw_body),
            }
    except urllib.error.HTTPError as exc:
        raw_body = exc.read()
        return {
            **base,
            "ok": False,
            "status_code": exc.code,
            "content_type": exc.headers.get("content-type", ""),
            "bytes": len(raw_body),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_seconds": elapsed(started),
            **describe_body(raw_body),
        }
    except Exception as exc:
        return {
            **base,
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_seconds": elapsed(started),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", default="1999-00")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    print(json.dumps(request_schedule(args.season, args.timeout), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
