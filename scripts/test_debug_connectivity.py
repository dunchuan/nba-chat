"""Call the local NBA connectivity endpoint and print network-path evidence.

Examples:
    python scripts/test_debug_connectivity.py
    python scripts/test_debug_connectivity.py --game-id 0049900088
"""

from __future__ import annotations

import argparse
import json
import socket
import time
import urllib.parse
import urllib.request


FAKE_IP_PREFIX = "198.18."


def elapsed(started: float) -> float:
    return round(time.perf_counter() - started, 3)


def get_public_ip(timeout: float) -> dict[str, object]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen("https://api64.ipify.org?format=json", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {"ok": True, "ip": payload.get("ip"), "elapsed_seconds": elapsed(started)}
    except Exception as exc:
        return {"ok": False, "error_type": type(exc).__name__, "error": str(exc), "elapsed_seconds": elapsed(started)}


def resolve(host: str) -> dict[str, object]:
    started = time.perf_counter()
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
        fake_ips = [address for address in addresses if address.startswith(FAKE_IP_PREFIX)]
        return {
            "ok": True,
            "addresses": addresses,
            "fake_ip_addresses": fake_ips,
            "likely_tun_fake_ip": bool(fake_ips),
            "elapsed_seconds": elapsed(started),
        }
    except Exception as exc:
        return {"ok": False, "error_type": type(exc).__name__, "error": str(exc), "elapsed_seconds": elapsed(started)}


def call_debug_endpoint(base_url: str, game_id: str, timeout: float) -> dict[str, object]:
    started = time.perf_counter()
    url = f"{base_url.rstrip('/')}/api/debug/nba-connectivity?{urllib.parse.urlencode({'game_id': game_id})}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
        return {"ok": True, "url": url, "response": json.loads(body), "elapsed_seconds": elapsed(started)}
    except Exception as exc:
        return {"ok": False, "url": url, "error_type": type(exc).__name__, "error": str(exc), "elapsed_seconds": elapsed(started)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", default="0049900088")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=35.0)
    args = parser.parse_args()

    dns = {host: resolve(host) for host in ("stats.nba.com", "cdn.nba.com")}
    fake_ip_evidence = {
        host: result.get("fake_ip_addresses", [])
        for host, result in dns.items()
        if result.get("likely_tun_fake_ip")
    }
    report = {
        "client": {"public_ip": get_public_ip(args.timeout)},
        "target_dns": dns,
        "tun_detection": {
            "likely_tun_fake_ip": bool(fake_ip_evidence),
            "evidence": fake_ip_evidence,
            "note": "This detects Fake-IP style TUN DNS only; false does not prove TUN is off.",
        },
        "debug_endpoint": call_debug_endpoint(args.base_url, args.game_id, args.timeout),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
