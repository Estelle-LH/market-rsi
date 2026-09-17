"""Application-level E2B network observation, not an isolation certificate.

The trusted host supplies harmless public/peer HTTPS URLs and preserves this
exact source hash. The guest performs one bounded GET with environment proxy
settings and one without them for each URL. An HTTP response, including 403,
is evidence that application bytes reached some HTTP endpoint; a mere TCP
handshake is not. Negative observations on two URLs cannot prove that every
possible route is blocked. The host must separately verify E2B policy, both
roles, broker-positive access, peer-marker denial, and exact cleanup.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener


SCHEMA = "market_rsi_protocol_network_probe_v1"
MAX_RESPONSE_BYTES = 2048
TIMEOUT_SECONDS = 3
MODES = ("environment_proxy", "direct_no_proxy")


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("bounded HTTPS URL required")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.fragment or parsed.port not in {None, 443}):
        raise ValueError("public and peer probes require credential-free HTTPS URLs")
    return value


def _one_get(url: str, *, direct: bool) -> dict:
    opener = build_opener(ProxyHandler({}) if direct else ProxyHandler())
    request = Request(url, headers={"User-Agent": "MarketRSI-isolation-canary/1"},
                      method="GET")
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            return {"http_response": True, "status": response.status,
                    "body_sha256": hashlib.sha256(body).hexdigest(),
                    "body_truncated": len(body) > MAX_RESPONSE_BYTES,
                    "error_type": None}
    except HTTPError as error:
        # A 4xx/5xx is still an application-level response; never count it as
        # proof that the guest could not communicate with a remote endpoint.
        with error:
            body = error.read(MAX_RESPONSE_BYTES + 1)
        return {"http_response": True, "status": error.code,
                "body_sha256": hashlib.sha256(body).hexdigest(),
                "body_truncated": len(body) > MAX_RESPONSE_BYTES,
                "error_type": None}
    except (URLError, OSError, TimeoutError) as error:
        return {"http_response": False, "status": None,
                "body_sha256": None, "body_truncated": False,
                "error_type": type(error).__name__}


def observe(public_url: str, peer_url: str) -> dict:
    public_url, peer_url = _url(public_url), _url(peer_url)
    return {"schema": SCHEMA,
            "url_sha256": {"public": _sha(public_url), "peer": _sha(peer_url)},
            "observations": {
                label: {"environment_proxy": _one_get(url, direct=False),
                        "direct_no_proxy": _one_get(url, direct=True)}
                for label, url in (("public", public_url), ("peer", peer_url))}}


def review(report: dict, *, public_url: str, peer_url: str,
           peer_marker_sha256: str) -> dict:
    """Host checks the shape and reports observations; never certifies isolation."""
    urls = {"public": _url(public_url), "peer": _url(peer_url)}
    if (not isinstance(peer_marker_sha256, str) or len(peer_marker_sha256) != 64
            or any(c not in "0123456789abcdef" for c in peer_marker_sha256)):
        raise ValueError("peer marker SHA256 required")
    if (not isinstance(report, dict) or set(report) != {"schema", "url_sha256", "observations"}
            or report["schema"] != SCHEMA
            or report["url_sha256"] != {label: _sha(url) for label, url in urls.items()}
            or not isinstance(report["observations"], dict)
            or set(report["observations"]) != set(urls)):
        raise ValueError("probe report is not bound to the two host-selected URLs")
    observed = {}
    for label in urls:
        modes = report["observations"][label]
        if not isinstance(modes, dict) or set(modes) != set(MODES):
            raise ValueError("missing protocol probe mode")
        observed[label] = []
        for mode in MODES:
            item = modes[mode]
            if (not isinstance(item, dict)
                    or set(item) != {"http_response", "status", "body_sha256",
                                     "body_truncated", "error_type"}
                    or type(item["http_response"]) is not bool
                    or type(item["body_truncated"]) is not bool):
                raise ValueError("invalid protocol observation")
            if item["http_response"]:
                if (type(item["status"]) is not int or not 100 <= item["status"] <= 599
                        or not isinstance(item["body_sha256"], str)
                        or len(item["body_sha256"]) != 64
                        or any(c not in "0123456789abcdef" for c in item["body_sha256"])
                        or item["error_type"] is not None):
                    raise ValueError("invalid HTTP response receipt")
            elif (item["status"] is not None or item["body_sha256"] is not None
                  or item["body_truncated"] is not False
                  or not isinstance(item["error_type"], str)
                  or not item["error_type"]):
                raise ValueError("invalid blocked/failed response receipt")
            observed[label].append(item)
    return {"schema": "market_rsi_protocol_network_review_v1",
            "public_http_response_observed": any(
                item["http_response"] for item in observed["public"]),
            "peer_http_response_observed": any(
                item["http_response"] for item in observed["peer"]),
            "peer_marker_observed": any(
                item["http_response"] and item["body_sha256"] == peer_marker_sha256
                and not item["body_truncated"] for item in observed["peer"]),
            "isolation_proven": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--peer-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = observe(args.public_url, args.peer_url)
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError("fresh protocol probe output required")
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, separators=(",", ":"))


if __name__ == "__main__":
    main()
