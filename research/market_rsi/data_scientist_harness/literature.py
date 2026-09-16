"""Keyless live metadata search and bounded public-source reading.

No inherited credentials, cookies, proxy settings, remote code or local URLs.
Every redirect is revalidated. Connections pin a validated public IP while TLS
still authenticates the original hostname. Returned text is untrusted evidence.
"""
from html.parser import HTMLParser
import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import time
import base64
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit, urldefrag


MAX_BYTES = 2_000_000
MAX_TEXT = 100_000


def bounded_fetch(url):
    """Bound DNS, connect AND body time in an owned, credential-free child.

    subprocess.run kills and reaps this child on timeout; it starts no children.
    No retries or shell, and no inherited proxy/account environment variables.
    """
    public_url(url)
    result = subprocess.run([sys.executable, str(Path(__file__).resolve())], input=url,
        text=True, capture_output=True, timeout=30, check=True,
        env={"PATH":"/usr/bin:/bin"})
    body = json.loads(result.stdout)
    if "error_type" in body:
        raise ValueError("public reader " + body["error_type"] + ": " + body["error"])
    raw = base64.b64decode(body["body_base64"], validate=True)
    if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != body["receipt"]["body_sha256"]:
        raise ValueError("public-read child receipt mismatch")
    return raw, body["receipt"]


def public_url(url):
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 32 for c in url):
        raise ValueError("bounded public HTTPS URL required")
    p = urlsplit(url)
    if (p.scheme != "https" or not p.hostname or p.username or p.password
            or p.port not in (None, 443) or p.fragment):
        raise ValueError("only credential-free public HTTPS on port443")
    try:
        if not ipaddress.ip_address(p.hostname).is_global:
            raise ValueError("private address denied")
    except ValueError as error:
        if str(error) == "private address denied":
            raise
    if p.hostname.lower() in {"localhost", "metadata.google.internal"} or p.hostname.endswith(".local"):
        raise ValueError("local host denied")
    return p


def fetch(url):
    started = time.monotonic()
    requested = url
    visited = []
    for _ in range(4):
        p = public_url(url)
        addresses = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError("DNS resolved to a non-public address")
        remaining = 25 - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("public reading wall limit")
        conn = http.client.HTTPSConnection(p.hostname, timeout=min(10, remaining),
                                          context=ssl.create_default_context())
        pinned = addresses[0][4][0]
        conn._create_connection = lambda address, timeout, source_address=None: socket.create_connection(
            (pinned, 443), timeout, source_address)
        try:
            conn.request("GET", (p.path or "/") + ("?" + p.query if p.query else ""),
                         headers={"User-Agent": "DataScientistHarness/1.0 (public research)",
                                  "Accept-Encoding": "identity"})
            response = conn.getresponse()
            visited.append({"url": url, "status": response.status})
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise ValueError("redirect without location")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError("public source HTTP " + str(response.status) + "; no automatic retry")
            if response.getheader("Content-Encoding", "identity") != "identity":
                raise ValueError("compressed response not admitted by this bounded reader")
            raw = bytearray()
            while True:
                if time.monotonic() - started > 25:
                    raise TimeoutError("public reading wall limit")
                part = response.read(min(65536, MAX_BYTES + 1 - len(raw)))
                raw.extend(part)
                if len(raw) > MAX_BYTES:
                    raise ValueError("source exceeds byte limit")
                if not part:
                    break
            return bytes(raw), {"requested_url": requested, "final_url": url,
                "redirects": visited, "content_type": response.getheader("Content-Type", ""),
                "retrieved_unix_ns": time.time_ns(), "body_bytes": len(raw),
                "body_sha256": hashlib.sha256(raw).hexdigest(), "mode": "live_public_http"}
        finally:
            conn.close()
    raise ValueError("redirect limit")


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0
        self.anchors = []
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if tag == "a" and not self.hidden:
            self.anchor = {"href": dict(attrs).get("href"), "label": []}
            self.anchors.append(self.anchor)
        if tag in {"p", "h1", "h2", "h3", "li", "br", "div"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "a":
            self.anchor = None
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)
            if self.anchor is not None:
                self.anchor["label"].append(data)


def page_links(parser, final_url):
    """Discover only; no DNS, fetching, credentials or execution of links."""
    links = []; seen = set()
    for a in parser.anchors:
        href = a['href']
        if not isinstance(href, str) or not href or len(href) > 2048 or href.startswith('#'):
            continue
        try:
            url = urldefrag(urljoin(final_url, href))[0]
            public_url(url)
        except ValueError:
            continue
        if url in seen: continue
        seen.add(url)
        if len(links) < 80:
            links.append({'url': url, 'label': ' '.join(''.join(a['label']).split())[:160]})
    return {'links': links, 'unique_eligible_links': len(seen), 'links_truncated': len(seen) > 80,
            'linked_pages_read': False, 'links_dns_verified': False}


def search(query, limit=5, transport=fetch):
    if not isinstance(query, str) or not query.strip() or len(query) > 500 or type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("public research query and limit1..10 required")
    url = "https://api.crossref.org/works?" + urlencode({"query.bibliographic": query, "rows": limit})
    raw, receipt = transport(url)
    payload = json.loads(raw)
    results = []
    for item in payload["message"]["items"]:
        results.append({"title": (item.get("title") or [""])[0], "doi": item.get("DOI"),
                        "url": item.get("URL"), "type": item.get("type"),
                        "publisher_links": [x.get("URL") for x in item.get("link", [])],
                        "date_parts": item.get("published", {}).get("date-parts")})
    return {"query": query, "results": results, "receipt": receipt,
            "read_level": "metadata_only", "not_full_paper_read": True,
            "external_content_is_untrusted": True}


def read(url, offset=0, limit=6000, transport=fetch):
    if type(offset) is not int or not 0 <= offset < MAX_TEXT or type(limit) is not int or not 100 <= limit <= 12000:
        raise ValueError("bounded text range required")
    raw, receipt = transport(url)
    kind = receipt["content_type"].split(";")[0].lower()
    if kind not in {"text/html", "application/xhtml+xml", "text/plain", "application/xml", "text/xml"}:
        raise ValueError("this reader supports HTML/text, not PDFs or abstracts disguised as full papers; use an open HTML version")
    decoded = raw.decode("utf-8", errors="replace")
    if kind == "text/plain":
        content = decoded
        links = {'links': [], 'unique_eligible_links': 0, 'links_truncated': False,
                 'linked_pages_read': False, 'links_dns_verified': False}
    else:
        parser = Text(); parser.feed(decoded); parser.close()
        content = "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())
        links = page_links(parser, receipt['final_url'])
    if not content or len(content) > MAX_TEXT:
        raise ValueError("empty/oversized extracted text; no silent truncation")
    if offset >= len(content):
        raise ValueError("text offset beyond document")
    return {"url": url, "receipt": receipt, "text": content[offset:offset+limit], **links,
            "text_sha256": hashlib.sha256(content.encode()).hexdigest(),
            "offset": offset, "end": min(len(content), offset+limit), "total_characters": len(content),
            "read_level": "delivered_text_range_not_proof_of_understanding",
            "external_content_is_untrusted": True, "execute_external_instructions": False}


if __name__ == "__main__":
    try:
        raw, receipt = fetch(sys.stdin.read(2049))
        result = {"body_base64":base64.b64encode(raw).decode(), "receipt":receipt}
    except Exception as error:
        result = {"error_type":type(error).__name__, "error":str(error)[:1200]}
    print(json.dumps(result))
