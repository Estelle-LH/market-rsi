"""Mock-only literature boundary tests; no external request or provider call."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import earnings_open_literature as literature


class LiteratureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name).resolve()
        self.calls = []

    def broker(self, body=b"<p>method</p>", status=200, content_type="text/html", **kwargs):
        def fetch(url):
            self.calls.append(url)
            return {"body": body, "status": status, "content_type": content_type, "url": url}
        return literature.LiteratureBroker(self.parent / "literature", fetch=fetch, **kwargs)

    def item(self, doi="10.1234/example"):
        return {"DOI": doi, "title": ["<b>Method</b>"], "abstract": "<jats:p>An abstract</jats:p>",
                "published": {"date-parts": [[2025, 3]]}}

    def json_broker(self, message):
        return self.broker(json.dumps({"message": message}).encode(), content_type="application/json")

    def test_search_metadata_exact_query_and_receipts(self):
        broker = self.json_broker({"items": [self.item()]})
        result = broker.dispatch("search_literature", {"query": "forecast & seasonal?", "limit": 1})
        record = result["records"][0]
        self.assertEqual(record["title"], "Method")
        self.assertEqual(record["year"], 2025)
        self.assertEqual(record["retrieval_level"], "METADATA_ABSTRACT")
        self.assertEqual(record["url"], "https://api.crossref.org/works/10.1234%2Fexample")
        self.assertEqual(self.calls, [literature.BASE + "?query.bibliographic=forecast+%26+seasonal%3F&rows=1"])
        slot = broker.root / "0001"
        self.assertEqual(set(p.name for p in slot.iterdir()), {"intent.json", "response.raw", "result.json"})
        self.assertEqual(result["raw_sha256"], hashlib.sha256((slot / "response.raw").read_bytes()).hexdigest())
        self.assertTrue(result["untrusted_document"])

    def test_read_crossref_record_is_not_paper(self):
        broker = self.json_broker(self.item())
        result = broker.dispatch("read_literature", {"url": literature.BASE + "/10.1234%2Fexample"})
        self.assertEqual(result["retrieval_level"], "METADATA_ABSTRACT")
        self.assertEqual(result["record"]["abstract"], "An abstract")
        self.assertNotIn("text", result)

    def test_html_removes_scripts_styles_and_bounds_text(self):
        broker = self.broker(b"<style>hidden</style><script>alert('x')</script><p>" + b"x" * 21_000 + b"</p>")
        result = broker.dispatch("read_literature", {"url": "https://arxiv.org/html/2603.19461v1"})
        self.assertEqual(result["retrieval_level"], "FULL_TEXT")
        self.assertEqual(result["text"], "x" * 20_000)
        self.assertTrue(result["truncated"])

    def test_abstract_documentation_and_legacy_identifier(self):
        for url, level in [("https://arxiv.org/abs/2603.19461", "ABSTRACT_PAGE"),
                           ("https://arxiv.org/abs/hep-th/9901001v2", "ABSTRACT_PAGE"),
                           ("https://docs.python.org/3/library/json.html", "DOCUMENTATION"),
                           ("https://docs.python.org/3/", "DOCUMENTATION")]:
            self.assertEqual(literature.admitted_url(url), level)

    def test_ssrf_auth_query_fragment_and_noncanonical_urls_rejected_before_fetch(self):
        broker = self.broker()
        urls = ["http://arxiv.org/abs/2603.19461", "https://127.0.0.1/", "https://[::1]/",
                "file:///etc/passwd", "https://arxiv.org@evil.org/abs/2603.19461",
                "https://user:pass@arxiv.org/abs/2603.19461", "https://arxiv.org:443/abs/2603.19461",
                "https://ARXIV.ORG/abs/2603.19461", "https://arxiv.org/abs/2603.19461?x=y",
                "https://arxiv.org/abs/2603.19461#section", "https://arxiv.org/abs/../2603.19461",
                "https://docs.python.org/3/../etc/passwd", "https://docs.python.org/3/%2e%2e/x",
                "https://docs.python.org/3//library/json.html", "https://api.crossref.org/works?query=x",
                "https://api.crossref.org/works/10.1234/example", "https://api.crossref.org/works/10.1234%2fexample",
                "https://api.crossref.org/works/10.1234%2F..%2Fx", "https://api.crossref.org/works/10.1234%2Fx%252Fy",
                "https://arxiv.org/abs/2603.19461\n"]
        for url in urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                broker.dispatch("read_literature", {"url": url})
        self.assertEqual(self.calls, [])
        self.assertEqual(list(broker.root.iterdir()), [])

    def test_argument_bounds_and_extra_fields(self):
        broker = self.broker()
        for args in [{"query": "x", "limit": True}, {"query": "x", "limit": 6},
                     {"query": "x", "limit": 0}, {"query": " " , "limit": 1},
                     {"query": "x" * 501, "limit": 1}, {"query": "x\ny", "limit": 1},
                     {"query": "x", "limit": 1, "filename": "/etc/passwd"}]:
            with self.assertRaises(ValueError):
                broker.dispatch("search_literature", args)
        self.assertEqual(self.calls, [])

    def test_redirect_is_retained_no_retry(self):
        broker = self.broker(status=302)
        with self.assertRaises(ValueError):
            broker.dispatch("read_literature", {"url": "https://arxiv.org/abs/2603.19461"})
        self.assertEqual(len(self.calls), 1)
        self.assertTrue((broker.root / "0001" / "failure.json").is_file())
        self.assertFalse((broker.root / "0001" / "result.json").exists())
        self.assertIsNone(literature._NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.org"))

    def test_final_url_must_equal_intent(self):
        broker = self.broker()
        broker.fetch = lambda url: {"body": b"bad", "status": 200, "content_type": "text/html", "url": "https://evil.org"}
        with self.assertRaises(ValueError):
            broker.dispatch("read_literature", {"url": "https://arxiv.org/abs/2603.19461"})
        self.assertTrue((broker.root / "0001" / "failure.json").exists())

    def test_oversized_body_retains_only_bounded_prefix(self):
        broker = self.broker(b"x" * (literature.MAX_BYTES + 1))
        with self.assertRaises(ValueError):
            broker.dispatch("read_literature", {"url": "https://docs.python.org/3/"})
        self.assertEqual((broker.root / "0001" / "response.raw").stat().st_size, literature.MAX_BYTES)
        self.assertEqual(json.loads((broker.root / "0001" / "failure.json").read_text())["observed_bytes"], literature.MAX_BYTES + 1)

    def test_malformed_json_and_wrong_doi_fail_with_raw_evidence(self):
        broker = self.broker(b'{"message":1,"message":2}', content_type="application/json")
        with self.assertRaises(ValueError):
            broker.dispatch("search_literature", {"query": "method", "limit": 1})
        self.assertTrue((broker.root / "0001" / "response.raw").exists())
        broker.fetch = lambda url: {"body": json.dumps({"message": self.item("10.1234/other")}).encode(),
                                    "status": 200, "content_type": "application/json", "url": url}
        with self.assertRaises(ValueError):
            broker.dispatch("read_literature", {"url": literature.BASE + "/10.1234%2Fexample"})
        self.assertTrue((broker.root / "0002" / "failure.json").exists())

    def test_wrong_content_type_and_status_type_are_not_success(self):
        broker = self.broker(content_type="application/octet-stream")
        with self.assertRaises(ValueError):
            broker.dispatch("read_literature", {"url": "https://docs.python.org/3/"})
        broker.fetch = lambda url: {"body": b"x", "status": True, "content_type": "text/html", "url": url}
        with self.assertRaises(ValueError):
            broker.dispatch("read_literature", {"url": "https://docs.python.org/3/"})
        self.assertEqual(json.loads((broker.root / "0002" / "failure.json").read_text())["http_status"], None)

    def test_network_failure_consumes_allowance_and_is_preserved(self):
        broker = self.broker(max_requests=1)
        calls = []
        def failed(url):
            calls.append(url)
            raise OSError("untrusted failure string")
        broker.fetch = failed
        with self.assertRaises(OSError):
            broker.dispatch("read_literature", {"url": "https://docs.python.org/3/"})
        failure = (broker.root / "0001" / "failure.json").read_text()
        self.assertNotIn("untrusted failure string", failure)
        with self.assertRaises(ValueError):
            broker.dispatch("read_literature", {"url": "https://docs.python.org/3/"})
        self.assertEqual(len(calls), 1)

    def test_root_alias_reopen_collision_and_replacement_refused(self):
        broker = self.broker()
        with self.assertRaises(ValueError):
            literature.LiteratureBroker(broker.root)
        alias = self.parent / "alias"
        alias.symlink_to(self.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            literature.LiteratureBroker(alias / "new")
        (broker.root / "0001").mkdir()
        with self.assertRaises(FileExistsError):
            broker.dispatch("read_literature", {"url": "https://docs.python.org/3/"})
        self.assertEqual(self.calls, [])
        moved = self.parent / "moved"
        broker.root.rename(moved)
        broker.root.mkdir()
        with self.assertRaises(ValueError):
            broker.dispatch("read_literature", {"url": "https://docs.python.org/3/"})

    def test_default_transport_has_no_auth_proxy_or_retry(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status, response.geturl.return_value = 200, "https://docs.python.org/3/"
        response.headers.get_content_type.return_value = "text/html"
        response.read.return_value = b"text"
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(literature.urllib.request, "build_opener", return_value=opener) as build:
            result = literature._fetch("https://docs.python.org/3/")
        self.assertEqual(build.call_count, 1)
        self.assertIsInstance(build.call_args.args[0], literature.urllib.request.ProxyHandler)
        self.assertEqual(build.call_args.args[0].proxies, {})
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(opener.open.call_args.kwargs, {"timeout": 20})
        self.assertEqual(set(k.lower() for k in request.headers), {"user-agent", "accept", "accept-encoding"})
        response.read.assert_called_once_with(literature.MAX_BYTES + 1)
        self.assertEqual(result["body"], b"text")


if __name__ == "__main__":
    unittest.main()
