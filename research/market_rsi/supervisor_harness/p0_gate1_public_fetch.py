"""Trusted, allowlisted public-document snapshotter for Gate 1.

The Controller never controls a URL.  The broker receives a compiled task,
requires a separate exact-task admission, performs at most one HTTPS GET, and
writes only a bounded immutable snapshot plus a receipt.  B remains offline.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from market_rsi import canonical, digest
from supervisor_harness.p0_gate1_research_contract import TASK_SCHEMA


ADMISSION_SCHEMA = "market_p0_gate1_fetch_admission_v1"
RECEIPT_SCHEMA = "market_p0_gate1_public_snapshot_receipt_v1"
ALLOWED_CONTENT_TYPES = frozenset({
    "application/json", "text/html", "text/plain", "text/markdown",
})
MAX_HARD_BYTES = 5_000_000
TIMEOUT_SECONDS = 15


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UrlLibTransport:
    def fetch(self, url: str, *, timeout_seconds: int, max_bytes: int) -> dict:
        request = urllib.request.Request(
            url, headers={"User-Agent": "MarketRSI-Public-Research/1.0",
                          "Accept": "application/json,text/html,text/plain;q=0.9"},
            method="GET")
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                body = response.read(max_bytes + 1)
                return {"status": response.status, "final_url": response.geturl(),
                        "headers": dict(response.headers.items()), "body": body}
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"public source returned HTTP {exc.code}") from exc


def _validate_url(url: object) -> str:
    if not isinstance(url, str) or len(url.encode("utf-8")) > 2000:
        raise ValueError("invalid public source URL")
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.port not in {None, 443}
            or parsed.fragment):
        raise ValueError("public source URL is not exact HTTPS")
    return url


def _content_type(headers: dict) -> str:
    if not isinstance(headers, dict):
        raise ValueError("response headers are invalid")
    value = next((item for key, item in headers.items()
                  if isinstance(key, str) and key.lower() == "content-type"), None)
    if not isinstance(value, str):
        raise ValueError("response content type is missing")
    media_type = value.split(";", 1)[0].strip().lower()
    if media_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError("response content type is not allowlisted")
    return media_type


def _exclusive_write(path: Path, body: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError("snapshot destination already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".snapshot-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)
    if path.read_bytes() != body:
        raise ValueError("snapshot changed during publication")


def fetch_snapshot(task: dict, admission: dict, output: Path, transport) -> dict:
    if output.exists():
        raise FileExistsError("Gate 1 fetch output must be fresh")
    if not isinstance(task, dict) or task.get("schema") != TASK_SCHEMA:
        raise ValueError("wrong Gate 1 task")
    task_sha = digest(task)
    required_admission = {"schema", "task_sha256", "source_id",
                          "fetch_authorized", "max_bytes", "max_requests"}
    if (not isinstance(admission, dict) or set(admission) != required_admission
            or admission.get("schema") != ADMISSION_SCHEMA
            or admission.get("task_sha256") != task_sha
            or admission.get("source_id") != task.get("source", {}).get("source_id")
            or admission.get("fetch_authorized") is not True
            or admission.get("max_requests") != 1):
        raise ValueError("exact one-fetch admission is missing")
    task_limit = task.get("bounds", {}).get("max_bytes")
    admitted_limit = admission.get("max_bytes")
    if (type(task_limit) is not int or type(admitted_limit) is not int
            or not 0 < admitted_limit <= task_limit <= MAX_HARD_BYTES):
        raise ValueError("fetch byte bound is invalid")
    url = _validate_url(task["source"].get("url"))
    response = transport.fetch(url, timeout_seconds=TIMEOUT_SECONDS,
                               max_bytes=admitted_limit)
    if not isinstance(response, dict) or set(response) != {
            "status", "final_url", "headers", "body"}:
        raise ValueError("transport response schema is invalid")
    body = response["body"]
    if (response["status"] != 200 or response["final_url"] != url
            or not isinstance(body, bytes) or not 0 < len(body) <= admitted_limit):
        raise ValueError("public response status, URL, or size is invalid")
    media_type = _content_type(response["headers"])
    output.mkdir(parents=True)
    snapshot = output / "public-source.snapshot"
    _exclusive_write(snapshot, body)
    safe_headers = {}
    for name in ("etag", "last-modified"):
        value = next((item for key, item in response["headers"].items()
                      if isinstance(key, str) and key.lower() == name), None)
        if isinstance(value, str) and len(value.encode("utf-8")) <= 500:
            safe_headers[name] = value
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "task_sha256": task_sha,
        "source_id": task["source"]["source_id"],
        "url_sha256": hashlib.sha256(url.encode("utf-8")).hexdigest(),
        "status": 200,
        "content_type": media_type,
        "response_headers": safe_headers,
        "snapshot_bytes": len(body),
        "snapshot_sha256": hashlib.sha256(body).hexdigest(),
        "requests_made": 1,
        "redirects_followed": 0,
        "b_network_access": False,
        "sealed_data_read": False,
        "formal_data_admitted": False,
    }
    receipt_path = output / "receipt.json"
    _exclusive_write(receipt_path, (canonical(receipt) + "\n").encode("utf-8"))
    return receipt
