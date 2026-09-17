"""Synthetic peer service for a two-E2B isolation canary only.

The host gives each sandbox a different random public marker. A local GET
proves the service is actually running before the other sandbox attempts its
unauthenticated E2B URL. Never serve market data, keys, or protected files.
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
from pathlib import Path
import time
from urllib.request import build_opener, ProxyHandler, Request


MAX_MARKER_BYTES = 128


def _marker(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MARKER_BYTES:
        raise ValueError("missing or oversized synthetic marker")
    value = path.read_bytes()
    if not 16 <= len(value) <= MAX_MARKER_BYTES:
        raise ValueError("synthetic marker length invalid")
    return value


def serve(marker_path: Path, *, bind: str, port: int) -> None:
    marker = _marker(marker_path)
    if bind not in {"127.0.0.1", "0.0.0.0"} or not 1024 <= port <= 65535:
        raise ValueError("invalid peer server bind or port")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/marker":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(marker)))
            self.end_headers()
            self.wfile.write(marker)

        def log_message(self, format, *args):
            pass

    with http.server.HTTPServer((bind, port), Handler) as server:
        server.serve_forever(poll_interval=0.1)


def self_check(*, port: int, marker_path: Path, attempts: int = 5) -> dict:
    marker = _marker(marker_path)
    if not 1024 <= port <= 65535 or not 1 <= attempts <= 10:
        raise ValueError("invalid local peer check bound")
    url = f"http://127.0.0.1:{port}/marker"
    opener = build_opener(ProxyHandler({}))
    for attempt in range(attempts):
        try:
            with opener.open(Request(url, method="GET"), timeout=1) as response:
                body = response.read(MAX_MARKER_BYTES + 1)
                if response.status != 200 or body != marker:
                    raise ValueError("peer service returned a different marker")
                return {"schema": "market_rsi_peer_local_positive_v1",
                        "port": port, "marker_sha256": hashlib.sha256(body).hexdigest(),
                        "attempts": attempt + 1, "local_service_responded": True}
        except OSError:
            if attempt + 1 == attempts:
                raise
            time.sleep(0.1)
    raise AssertionError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--serve", action="store_true")
    mode.add_argument("--self-check", action="store_true")
    parser.add_argument("--marker", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--bind", default="0.0.0.0")
    args = parser.parse_args()
    if args.serve:
        serve(args.marker, bind=args.bind, port=args.port)
    else:
        import json
        print(json.dumps(self_check(port=args.port, marker_path=args.marker), sort_keys=True))


if __name__ == "__main__":
    main()
