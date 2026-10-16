import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from earnings_http import RawOpenAIHTTP
from edgar_forecast_openai import ProviderHTTPError, budgeted_response
from edgar_forecast_budget import PilotBudget, BudgetStop
from earnings_entry import durable_json


class RawHTTPTests(unittest.TestCase):
    def test_reflected_request_id_dropped_on_success_and_error_both_endpoints(self):
        for index, (endpoint, status) in enumerate((
                ("/v1/responses/input_tokens", 200), ("/v1/responses", 200),
                ("/v1/responses/input_tokens", 429), ("/v1/responses", 429))):
            with self.subTest(endpoint=endpoint, status=status):
                prefix = self.prefix.with_name("request-id-" + str(index))
                durable_json(prefix.with_suffix(".intent.json"), {"fixture": True})
                self.client.record_prefix = prefix
                response = Mock(status=status)
                response.getheader.return_value = "req_" + self.client.key
                response.read.return_value = b'{"input_tokens":10}' if status == 200 else b'{"error":{"code":"rate_limit_exceeded"}}'
                with patch("earnings_http.http.client.HTTPSConnection") as connection:
                    connection.return_value.getresponse.return_value = response
                    if status == 200:
                        result = self.client.post(endpoint, {})
                        self.assertIsNone(result["_request_id"])
                        self.assertNotIn(self.client.key, json.dumps(result))
                    else:
                        with self.assertRaises(ProviderHTTPError) as caught:
                            self.client.post(endpoint, {})
                        self.assertIsNone(caught.exception.detail["request_id"])
                        self.assertNotIn(self.client.key, json.dumps(caught.exception.detail))
                    connection.return_value.request.assert_called_once()
                for path in prefix.parent.glob(prefix.name + ".*"):
                    self.assertNotIn(self.client.key.encode(), path.read_bytes())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prefix = Path(self.tmp.name).resolve() / "http-test"
        durable_json(self.prefix.with_suffix(".intent.json"), {"intent": "synthetic"})
        self.client = RawOpenAIHTTP("synthetic-key", 1200)
        self.client.record_prefix = self.prefix

    def test_original_bytes_saved_before_parsing_and_no_retry(self):
        raw = b'{  "status": "completed", "output": [] }\n'
        response = Mock(status=200)
        response.read.return_value = raw
        response.getheader.return_value = "req_synthetic"
        with patch("earnings_http.http.client.HTTPSConnection") as connection:
            connection.return_value.getresponse.return_value = response
            result = self.client.post("/v1/responses", {"input": "public"})
            connection.assert_called_once_with("api.openai.com", timeout=1200)
            connection.return_value.request.assert_called_once()
            connection.return_value.close.assert_called_once()
        self.assertEqual(self.prefix.with_suffix(".raw.bin").read_bytes(), raw)
        self.assertEqual(result["_request_id"], "req_synthetic")

    def test_missing_intent_refuses_before_connection(self):
        self.client.record_prefix = None
        with patch("earnings_http.http.client.HTTPSConnection") as connection:
            with self.assertRaises(ValueError):
                self.client.post("/v1/responses", {})
            connection.assert_not_called()

    def test_reflected_secret_never_persisted(self):
        response = Mock(status=200)
        response.read.return_value = b'{"echo":"synthetic-key"}'
        with patch("earnings_http.http.client.HTTPSConnection") as connection:
            connection.return_value.getresponse.return_value = response
            with self.assertRaises(ValueError):
                self.client.post("/v1/responses", {})
        self.assertFalse(self.prefix.with_suffix(".raw.bin").exists())

    def test_escaped_reflection_refuses_before_any_response_persistence(self):
        escaped = b'synthetic-\\u006bey'
        cases = (
            b'{"echo":"' + escaped + b'"}',
            b'{"echo":"' + escaped + b'","echo":"public"}',
            b'{"echo":"public","echo":"' + escaped + b'"}',
            b'{"echo":"' + escaped + b'",broken}',
            b'{"echo":"' + escaped,
            b'{"echo":"bad\\q ' + escaped + b'"}',
            b'broken response: ' + escaped,
            b'{"' + escaped + b'":1}',
            b'{"echo":"\\u0073\\u0079\\u006e\\u0074\\u0068\\u0065\\u0074\\u0069\\u0063\\u002d\\u006b\\u0065\\u0079"}',
            ('{"echo":"synthetic-\\u006bey"}').encode("utf-16"),
            ('{"echo":"synthetic-\\u006bey"}').encode("utf-32"),
        )
        for index, raw in enumerate(cases):
            with self.subTest(index=index):
                prefix = self.prefix.with_name("escaped-" + str(index))
                durable_json(prefix.with_suffix(".intent.json"), {"intent": "synthetic"})
                self.client.record_prefix = prefix
                response = Mock(status=200)
                response.read.return_value = raw
                response.getheader.return_value = "req_synthetic"
                with patch("earnings_http.http.client.HTTPSConnection") as connection:
                    connection.return_value.getresponse.return_value = response
                    with self.assertRaisesRegex(ValueError, "Credential reflected"):
                        self.client.post("/v1/responses", {})
                    connection.return_value.request.assert_called_once()
                    connection.return_value.close.assert_called_once()
                self.assertFalse(prefix.with_suffix(".raw.bin").exists())
                self.assertFalse(prefix.with_suffix(".response.json").exists())

    def test_nonsecret_literal_unicode_escape_keeps_exact_raw_bytes(self):
        raw = b'{"echo":"synthetic-\\\\u006bey"}'
        response = Mock(status=200)
        response.read.return_value = raw
        response.getheader.return_value = "req_synthetic"
        with patch("earnings_http.http.client.HTTPSConnection") as connection:
            connection.return_value.getresponse.return_value = response
            result = self.client.post("/v1/responses", {})
        self.assertEqual(result["echo"], "synthetic-\\u006bey")
        self.assertEqual(self.prefix.with_suffix(".raw.bin").read_bytes(), raw)

    def test_nonsecret_malformed_escaped_string_keeps_exact_raw_bytes(self):
        raw = b'{"echo":"public\\q\\u0074ext"}'
        response = Mock(status=200)
        response.read.return_value = raw
        with patch("earnings_http.http.client.HTTPSConnection") as connection:
            connection.return_value.getresponse.return_value = response
            with self.assertRaises(ValueError):
                self.client.post("/v1/responses", {})
            connection.return_value.request.assert_called_once()
        self.assertEqual(self.prefix.with_suffix(".raw.bin").read_bytes(), raw)

    def test_escaped_generation_reflection_keeps_uncertain_liability_no_retry(self):
        output = Path(self.tmp.name).resolve()
        budget = PilotBudget(output / "synthetic-only.sqlite3")
        self.addCleanup(budget.close)
        responses = [Mock(status=200), Mock(status=200)]
        responses[0].read.return_value = b'{"input_tokens":10}'
        responses[1].read.return_value = b'{"echo":"synthetic-\\u006bey"}'
        for response in responses:
            response.getheader.return_value = "req_synthetic"
        posted = []
        def recorded_post(endpoint, payload):
            prefix = output / ("reflection-http-" + str(len(posted)))
            durable_json(prefix.with_suffix(".intent.json"), {"endpoint": endpoint})
            self.client.record_prefix = prefix
            posted.append(endpoint)
            return self.client.post(endpoint, payload)
        client = Mock()
        client.post.side_effect = recorded_post
        rates = {"api_model": "gpt-6.1-sol", "input": "2", "cached": "0.5", "write": None, "output": "8"}
        config = {"max_input_tokens": 100, "max_output_tokens": 20}
        with patch("earnings_http.http.client.HTTPSConnection") as connection:
            connection.return_value.getresponse.side_effect = responses
            with self.assertRaisesRegex(ValueError, "Credential reflected"):
                budgeted_response(client, {"model": "gpt-6.1-sol"}, rates, config, budget, output, 1)
            with self.assertRaises(BudgetStop):
                budgeted_response(client, {"model": "gpt-6.1-sol"}, rates, config, budget, output, 2)
            self.assertEqual(connection.return_value.request.call_count, 2)
        self.assertEqual(budget.db.execute("SELECT reserved, charged, status FROM requests").fetchall(),
                         [(180000, 0, "uncertain")])
        self.assertEqual(budget.db.execute("SELECT blocked FROM config").fetchone(), (1,))
        self.assertEqual(posted, ["/v1/responses/input_tokens", "/v1/responses"])
        self.assertFalse((output / "reflection-http-1.raw.bin").exists())
        self.assertFalse((output / "01-response.json").exists())

    def test_error_retains_curated_code_not_raw_message(self):
        response = Mock(status=429)
        response.read.return_value = json.dumps({"error": {"code": "insufficient_quota", "message": "synthetic-key"}}).encode()
        response.getheader.return_value = "req_synthetic"
        with patch("earnings_http.http.client.HTTPSConnection") as connection:
            connection.return_value.getresponse.return_value = response
            with self.assertRaises(ProviderHTTPError) as caught:
                self.client.post("/v1/responses", {})
            self.assertEqual(connection.return_value.request.call_count, 1)
        self.assertEqual(caught.exception.detail["provider_code"], "insufficient_quota")
        self.assertNotIn("synthetic-key", str(caught.exception) + json.dumps(caught.exception.detail))
        self.assertFalse(self.prefix.with_suffix(".raw.bin").exists())

    def test_invalid_json_raw_body_remains_preserved(self):
        response = Mock(status=200)
        response.read.return_value = b'not JSON'
        response.getheader.return_value = "req_synthetic"
        with patch("earnings_http.http.client.HTTPSConnection") as connection:
            connection.return_value.getresponse.return_value = response
            with self.assertRaises(ValueError):
                self.client.post("/v1/responses", {})
        self.assertEqual(self.prefix.with_suffix(".raw.bin").read_bytes(), b'not JSON')

    def test_duplicate_keys_at_all_depths_reject_after_raw_persistence(self):
        cases = (
            ("/v1/responses", b'{"usage":{"input_tokens":10},"usage":{"input_tokens":0}}'),
            ("/v1/responses", b'{"usage":{"input_tokens_details":{"cached_tokens":1,"cached_tokens":0}}}'),
            ("/v1/responses", b'{"usage":{"input_tokens_details":{"cached_tokens":1},"input_tokens_details":{"cached_tokens":0}}}'),
            ("/v1/responses", b'{"output":[{"content":[{"text":"first","text":"last"}]}]}'),
            ("/v1/responses/input_tokens", b'{"input_tokens":10,"input_tokens":0}'),
        )
        for index, (endpoint, raw) in enumerate(cases):
            with self.subTest(index=index):
                prefix = self.prefix.with_name("duplicate-" + str(index))
                durable_json(prefix.with_suffix(".intent.json"), {"intent": "synthetic"})
                self.client.record_prefix = prefix
                response = Mock(status=200)
                response.read.return_value = raw
                with patch("earnings_http.http.client.HTTPSConnection") as connection:
                    connection.return_value.getresponse.return_value = response
                    with self.assertRaisesRegex(ValueError, "Duplicate JSON object key"):
                        self.client.post(endpoint, {})
                    connection.return_value.request.assert_called_once()
                    connection.return_value.close.assert_called_once()
                self.assertEqual(prefix.with_suffix(".raw.bin").read_bytes(), raw)

    def test_nonfinite_constants_reject_at_nested_depth_after_persistence(self):
        for constant in (b'NaN', b'Infinity', b'-Infinity'):
            with self.subTest(constant=constant):
                prefix = self.prefix.with_name("nonfinite-" + constant.decode())
                durable_json(prefix.with_suffix(".intent.json"), {"intent": "synthetic"})
                self.client.record_prefix = prefix
                raw = b'{"usage":{"details":[' + constant + b']}}'
                response = Mock(status=200)
                response.read.return_value = raw
                with patch("earnings_http.http.client.HTTPSConnection") as connection:
                    connection.return_value.getresponse.return_value = response
                    with self.assertRaisesRegex(ValueError, "Nonfinite JSON constant"):
                        self.client.post("/v1/responses", {})
                    connection.return_value.request.assert_called_once()
                self.assertEqual(prefix.with_suffix(".raw.bin").read_bytes(), raw)

    def test_unique_nested_objects_and_count_keep_original_values(self):
        raw = b'{"input_tokens":10,"details":{"input_tokens":3},"items":[{"input_tokens":2}]}'
        response = Mock(status=200)
        response.read.return_value = raw
        response.getheader.return_value = "invalid request-id"
        with patch("earnings_http.http.client.HTTPSConnection") as connection:
            connection.return_value.getresponse.return_value = response
            result = self.client.post("/v1/responses/input_tokens", {"input": "public"})
            connection.return_value.request.assert_called_once_with(
                "POST", "/v1/responses/input_tokens", json.dumps({"input": "public"}),
                {"Authorization": "Bearer synthetic-key", "Content-Type": "application/json"})
        self.assertEqual(result, dict(json.loads(raw), _request_id=None))
        self.assertEqual(self.prefix.with_suffix(".raw.bin").read_bytes(), raw)

    def test_duplicate_count_refuses_before_reservation_or_generation(self):
        output = Path(self.tmp.name).resolve()
        budget = PilotBudget(output / "synthetic-only.sqlite3")
        self.addCleanup(budget.close)
        raw = b'{"input_tokens":10,"input_tokens":0}'
        response = Mock(status=200)
        response.read.return_value = raw
        response.getheader.return_value = "req_synthetic"
        rates = {"api_model": "gpt-6.1-sol", "input": "2", "cached": "0.5", "write": None, "output": "8"}
        with patch("earnings_http.http.client.HTTPSConnection") as connection:
            connection.return_value.getresponse.return_value = response
            with self.assertRaisesRegex(ValueError, "Duplicate JSON object key"):
                budgeted_response(self.client, {}, rates,
                                  {"max_input_tokens": 100, "max_output_tokens": 20}, budget, output, 1)
            connection.return_value.request.assert_called_once()
        self.assertEqual(budget.db.execute("SELECT COUNT(*) FROM requests").fetchone(), (0,))
        self.assertEqual(budget.db.execute("SELECT blocked FROM config").fetchone(), (0,))
        self.assertEqual(self.prefix.with_suffix(".raw.bin").read_bytes(), raw)

    def test_ambiguous_error_body_keeps_curated_failure_without_raw_persistence(self):
        response = Mock(status=429)
        response.read.return_value = b'{"error":{"code":"invalid_api_key","code":"insufficient_quota"}}'
        response.getheader.return_value = "req_synthetic"
        with patch("earnings_http.http.client.HTTPSConnection") as connection:
            connection.return_value.getresponse.return_value = response
            with self.assertRaises(ProviderHTTPError) as caught:
                self.client.post("/v1/responses", {})
            connection.return_value.request.assert_called_once()
        self.assertEqual(caught.exception.detail,
                         {"http_status": 429, "provider_code": None, "request_id": "req_synthetic"})
        self.assertFalse(self.prefix.with_suffix(".raw.bin").exists())

    def test_duplicate_generation_usage_keeps_blocking_liability_no_retry(self):
        output = Path(self.tmp.name).resolve()
        budget = PilotBudget(output / "synthetic-only.sqlite3")
        self.addCleanup(budget.close)
        raw = (b'{"model":"gpt-6.1-sol","service_tier":"default","status":"completed","output":[], '
               b'"usage":{"input_tokens":10,"output_tokens":2,"total_tokens":12,"input_tokens_details":{"cached_tokens":0}}, '
               b'"usage":{"input_tokens":0,"output_tokens":0,"total_tokens":0,"input_tokens_details":{"cached_tokens":0}}}')
        responses = [Mock(status=200), Mock(status=200)]
        responses[0].read.return_value = b'{"input_tokens":10}'
        responses[1].read.return_value = raw
        for response in responses:
            response.getheader.return_value = "req_synthetic"
        posted = []
        def recorded_post(endpoint, payload):
            prefix = output / ("synthetic-http-" + str(len(posted)))
            durable_json(prefix.with_suffix(".intent.json"), {"endpoint": endpoint})
            self.client.record_prefix = prefix
            posted.append(endpoint)
            return self.client.post(endpoint, payload)
        client = Mock()
        client.post.side_effect = recorded_post
        rates = {"api_model": "gpt-6.1-sol", "input": "2", "cached": "0.5", "write": None, "output": "8"}
        config = {"max_input_tokens": 100, "max_output_tokens": 20}
        with patch("earnings_http.http.client.HTTPSConnection") as connection:
            connection.return_value.getresponse.side_effect = responses
            with self.assertRaisesRegex(ValueError, "Duplicate JSON object key"):
                budgeted_response(client, {"model": "gpt-6.1-sol"}, rates, config, budget, output, 1)
            self.assertEqual(connection.return_value.request.call_count, 2)
            with self.assertRaises(BudgetStop):
                budgeted_response(client, {"model": "gpt-6.1-sol"}, rates, config, budget, output, 2)
            self.assertEqual(connection.return_value.request.call_count, 2)
        self.assertEqual(posted, ["/v1/responses/input_tokens", "/v1/responses"])
        self.assertEqual(budget.db.execute("SELECT reserved, charged, status FROM requests").fetchall(),
                         [(180000, 0, "uncertain")])
        self.assertEqual(budget.db.execute("SELECT blocked FROM config").fetchone(), (1,))
        self.assertEqual((output / "synthetic-http-1.raw.bin").read_bytes(), raw)
        self.assertFalse((output / "01-response.json").exists())


if __name__ == "__main__":
    unittest.main()
