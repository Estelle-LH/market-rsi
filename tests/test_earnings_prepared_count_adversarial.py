"""Independent exact-count handoff adversaries; no real provider/ledger data.

Pack, ReceiptHTTP, retry-free raw persistence, budgeted_response and temporary
SQLite reserve/settle are real. Only HTTPS connection/response bytes are fake.
No production ledger, original company, credentials, candidate or Docker used.
"""
from copy import deepcopy
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from edgar_forecast_budget import BudgetStop
from edgar_forecast_openai import budgeted_response
import earnings_entry as entry
from earnings_http import RawOpenAIHTTP
from earnings_night_budget import DeadlineHTTP, history_snapshot
from earnings_open_context import pack
import test_earnings_capacity_controller_transport as transport


class PreparedCountAdversarial(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='prepared-count-independent-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.f = transport._TransportFixture(self, self.root/'owned')
        self.slot = Path(self.f.slots[0]); self.slot.mkdir(parents=True)
        self.turn = 1
        self.request = {'model': transport.MODEL, 'reasoning': {'effort': 'xhigh'},
            'instructions': 'Use only this invented public fixture.',
            'parallel_tool_calls': False, 'tools': [], 'tool_choice': 'none',
            'input': [{'role': 'user', 'content': 'invented evidence '*1600}]}
        self.count_value = {'object': 'response.input_tokens', 'input_tokens': 20,
                            'retained_extra_field': 'whole_original_response'}
        self.count_error = None
        self.calls = []
        raw = RawOpenAIHTTP('', 30)
        self.client = entry.ReceiptHTTP(DeadlineHTTP(raw, deadline_utc='2099-01-01T00:00:00Z',
            rollout_seconds=120), self.slot)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        owner = self
        class Connection:
            def __init__(self, host, timeout):
                if host != 'api.openai.com':
                    raise AssertionError('Synthetic HTTP only')
                self.timeout = timeout
            def request(self, method, endpoint, body, headers):
                if method != 'POST' or endpoint not in ('/v1/responses/input_tokens','/v1/responses'):
                    raise AssertionError('Unexpected transport method/endpoint')
                self.endpoint = endpoint
                owner.calls.append((endpoint, json.loads(body)))
            def getresponse(self):
                if self.endpoint.endswith('/input_tokens'):
                    if owner.count_error is not None:
                        raise owner.count_error
                    value = owner.count_value
                else:
                    value = owner.f.response()
                raw_bytes = transport._wire(value)
                return Mock(status=200, getheader=Mock(return_value='req_independent_count_fixture'),
                            read=Mock(side_effect=lambda maximum: raw_bytes[:maximum]))
            def close(self):
                pass
        self.stack.enter_context(patch('earnings_http.http.client.HTTPSConnection', Connection))

    def prepared(self):
        return pack(self.client, deepcopy(self.request), self.f.limits, self.slot, self.turn,
                    prepared_count_context=self.f.context_binding)

    def consume(self, packed, prepared, **changes):
        values = dict(client=self.client, request=packed, rates=self.f.rates, config=self.f.limits,
                      budget=self.f.budget, output=self.slot, turn=self.turn, prepared_count=prepared)
        values.update(changes)
        return budgeted_response(**values)

    def assert_refused_before_reserve(self, packed, prepared, **changes):
        before = history_snapshot(self.f.budget.db)
        call_count = len(self.calls)
        with patch.object(self.f.budget, 'reserve', wraps=self.f.budget.reserve) as reserve:
            with self.assertRaises((ValueError, BudgetStop)):
                self.consume(packed, prepared, **changes)
            reserve.assert_not_called()
        self.assertEqual(history_snapshot(self.f.budget.db), before)
        self.assertEqual(len(self.calls), call_count)

    def test_exact_handoff_keeps_original_wire_and_single_actual_count(self):
        packed, prepared = self.prepared()
        self.assertIsNotNone(prepared)
        self.assertEqual(self.calls[0], ('/v1/responses/input_tokens', packed))
        count_file = self.slot/'01-context-01-count.json'
        source_count_bytes = count_file.read_bytes()
        response = self.consume(packed, prepared)
        self.assertEqual(response['status'], 'completed')
        self.assertEqual([path for path, _ in self.calls], ['/v1/responses/input_tokens','/v1/responses'])
        self.assertEqual(count_file.read_bytes(), source_count_bytes)
        self.assertEqual(json.loads((self.slot/'01-count.json').read_bytes()), json.loads(source_count_bytes))
        self.assertEqual(self.f.budget.db.execute(
            "SELECT charged,status FROM requests WHERE id!='fixture-prior'").fetchall(), [(92800,'settled')])
        intents = [json.loads(p.read_bytes()) for p in self.slot.glob('http-*.intent.json')]
        self.assertEqual(sum(v['endpoint'].endswith('/input_tokens') for v in intents), 1)
        self.assertEqual(len(list(self.slot.glob('http-*.raw.bin'))), 2)
        reuse = json.loads((self.slot/'01-prepared-count-reuse.json').read_bytes())
        self.assertTrue(reuse['reused_original_provider_count'])
        self.assertFalse(reuse['new_count_http_request'])
        self.assertEqual(reuse['count_response_sha256'], hashlib.sha256(
            json.dumps(json.loads(source_count_bytes), sort_keys=True,
                       ensure_ascii=False, allow_nan=False).encode()).hexdigest())

    def test_payload_drift_refused_before_reservation(self):
        packed, prepared = self.prepared()
        changed = deepcopy(packed); changed['input'][0]['content'] += 'x'
        self.assert_refused_before_reserve(changed, prepared)

    def test_model_drift_refused_before_reservation(self):
        packed, prepared = self.prepared()
        self.assert_refused_before_reserve(dict(packed, model='gpt-5.5-2026-04-23'), prepared)

    def test_rates_model_drift_refused_before_reservation(self):
        packed, prepared = self.prepared()
        self.assert_refused_before_reserve(packed, prepared,
            rates=dict(self.f.rates, api_model='gpt-5.5-2026-04-23'))

    def test_slot_drift_refused_before_reservation(self):
        packed, prepared = self.prepared()
        other = Path(self.f.slots[1]); other.mkdir()
        self.assert_refused_before_reserve(packed, prepared, output=other)

    def test_turn_drift_refused_before_reservation(self):
        packed, prepared = self.prepared()
        self.assert_refused_before_reserve(packed, prepared, turn=2)

    def test_boolean_turn_cannot_equal_integer_turn(self):
        packed, prepared = self.prepared()
        self.assert_refused_before_reserve(packed, prepared, turn=True)

    def test_smaller_current_limit_refused_before_reservation(self):
        packed, prepared = self.prepared()
        self.assert_refused_before_reserve(packed, prepared,
            config=dict(self.f.limits, max_input_tokens=19))

    def test_caller_supplied_count_dictionary_is_not_a_prepared_handle(self):
        self.assert_refused_before_reserve(self.request, {'input_tokens': 20})

    def test_single_use_second_send_refused_before_second_reservation(self):
        packed, prepared = self.prepared()
        self.consume(packed, prepared)
        self.assert_refused_before_reserve(packed, prepared)

    def test_failed_binding_attempt_burns_handle(self):
        packed, prepared = self.prepared()
        changed = deepcopy(packed); changed['input'][0]['content'] += 'x'
        self.assert_refused_before_reserve(changed, prepared)
        marker = json.loads((self.slot/'01-prepared-count-consumed.json').read_bytes())
        self.assertEqual(marker['schema'], 'earnings_prepared_count_consumed_v1')
        self.assertFalse(marker['reservation_or_generation_started'])
        self.assert_refused_before_reserve(packed, prepared)

    def test_reservation_failure_leaves_handoff_consumed_without_send(self):
        packed, prepared = self.prepared()
        before = history_snapshot(self.f.budget.db)
        with patch.object(self.f.budget, 'reserve', side_effect=BudgetStop('Invented reserve boundary')):
            with self.assertRaises(BudgetStop):
                self.consume(packed, prepared)
        self.assertEqual(history_snapshot(self.f.budget.db), before)
        self.assertEqual([endpoint for endpoint,_ in self.calls], ['/v1/responses/input_tokens'])
        self.assert_refused_before_reserve(packed, prepared)

    def same_size_tamper(self, path, before, after):
        original = path.read_bytes(); metadata = path.stat()
        changed = original.replace(before, after, 1)
        self.assertNotEqual(changed, original)
        self.assertEqual(len(changed), len(original))
        path.write_bytes(changed)
        os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
        self.assertEqual(path.stat().st_size, metadata.st_size)
        self.assertEqual(path.stat().st_mtime_ns, metadata.st_mtime_ns)

    def test_same_size_mtime_restored_count_receipt_tamper_refused(self):
        packed, prepared = self.prepared()
        self.same_size_tamper(self.slot/'01-context-01-count.json', b'20', b'21')
        self.assert_refused_before_reserve(packed, prepared)

    def test_same_size_mtime_restored_role_context_tamper_refused(self):
        packed, prepared = self.prepared()
        self.same_size_tamper(Path(self.f.context_binding['path']),
            transport.SOURCE_COMMIT.encode(), b'e'*40)
        self.assert_refused_before_reserve(packed, prepared)

    def test_same_size_mtime_restored_preparation_context_tamper_refused(self):
        packed, prepared = self.prepared()
        path = self.slot/'01-context-01.json'
        token = json.loads(path.read_bytes())['effective_request_sha256']
        self.same_size_tamper(path, token.encode(), b'f'*64)
        self.assert_refused_before_reserve(packed, prepared)

    def test_same_size_mtime_restored_original_count_raw_tamper_refused(self):
        packed, prepared = self.prepared()
        intent = next(p for p in self.slot.glob('http-*.intent.json')
                      if json.loads(p.read_bytes())['endpoint'].endswith('/input_tokens'))
        raw = intent.with_name(intent.name.removesuffix('.intent.json')+'.raw.bin')
        self.same_size_tamper(raw, b'20', b'21')
        self.assert_refused_before_reserve(packed, prepared)

    def test_count_context_symlink_tamper_refused(self):
        packed, prepared = self.prepared()
        path = self.slot/'01-context-01-count.json'
        target = self.slot/'same-count-content.json'; target.write_bytes(path.read_bytes())
        path.unlink(); path.symlink_to(target)
        self.assert_refused_before_reserve(packed, prepared)

    def test_count_context_hardlink_tamper_refused(self):
        packed, prepared = self.prepared()
        path = self.slot/'01-context-01-count.json'
        os.link(path, self.slot/'count-hardlink-alias.json')
        self.assert_refused_before_reserve(packed, prepared)

    def test_same_size_original_decoded_count_response_tamper_refused(self):
        packed, prepared = self.prepared()
        intent = next(p for p in self.slot.glob('http-*.intent.json')
                      if json.loads(p.read_bytes())['endpoint'].endswith('/input_tokens'))
        path = intent.with_name(intent.name.removesuffix('.intent.json')+'.response.json')
        self.same_size_tamper(path, b'20', b'21')
        self.assert_refused_before_reserve(packed, prepared)

    def test_new_failure_receipt_invalidates_original_success_before_reservation(self):
        packed, prepared = self.prepared()
        intent = next(p for p in self.slot.glob('http-*.intent.json')
                      if json.loads(p.read_bytes())['endpoint'].endswith('/input_tokens'))
        path = intent.with_name(intent.name.removesuffix('.intent.json')+'.failed.json')
        entry.durable_json(path, {'exception_type': 'SyntheticLateCountFailure', 'retry_allowed': False})
        self.assert_refused_before_reserve(packed, prepared)

    def test_invalid_boolean_count_propagates_before_any_reservation(self):
        self.count_value['input_tokens'] = True
        with patch.object(self.f.budget, 'reserve', wraps=self.f.budget.reserve) as reserve:
            with self.assertRaises(ValueError):
                self.prepared()
            reserve.assert_not_called()
        self.assertEqual(len(self.calls), 1)

    def test_invalid_negative_count_propagates_before_any_reservation(self):
        self.count_value['input_tokens'] = -1
        with self.assertRaises(ValueError):
            self.prepared()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(history_snapshot(self.f.budget.db), self.f.baseline)

    def test_invalid_string_count_propagates_before_any_reservation(self):
        self.count_value['input_tokens'] = '20'
        with self.assertRaises(ValueError):
            self.prepared()
        self.assertEqual(history_snapshot(self.f.budget.db), self.f.baseline)

    def test_missing_count_field_propagates_before_any_reservation(self):
        del self.count_value['input_tokens']
        with self.assertRaises((KeyError, ValueError)):
            self.prepared()
        self.assertEqual(history_snapshot(self.f.budget.db), self.f.baseline)

    def test_count_overflow_never_mints_a_winning_handoff_or_reserves(self):
        self.count_value['input_tokens'] = self.f.limits['max_input_tokens']+1
        with self.assertRaises(BudgetStop):
            self.prepared()
        self.assertEqual([endpoint for endpoint,_ in self.calls], ['/v1/responses/input_tokens'])
        self.assertEqual(history_snapshot(self.f.budget.db), self.f.baseline)

    def test_original_provider_count_failure_is_not_caught_or_retried(self):
        error = RuntimeError('Invented original count failure')
        self.count_error = error
        with self.assertRaises(RuntimeError) as caught:
            self.prepared()
        self.assertIs(caught.exception, error)
        self.assertEqual([endpoint for endpoint,_ in self.calls], ['/v1/responses/input_tokens'])
        self.assertEqual(history_snapshot(self.f.budget.db), self.f.baseline)
        self.assertEqual(len(list(self.slot.glob('http-*.failed.json'))), 1)

    def test_small_optin_packet_still_counts_in_original_receiver(self):
        self.request['input'][0]['content'] = 'small invented evidence'
        packed, prepared = self.prepared()
        self.assertIsNone(prepared)
        self.assertEqual(self.calls, [])
        self.consume(packed, prepared)
        self.assertEqual([endpoint for endpoint,_ in self.calls], ['/v1/responses/input_tokens','/v1/responses'])

    def test_small_default_pack_retains_dictionary_api_and_stock_count(self):
        self.request['input'][0]['content'] = 'small invented evidence'
        packed = pack(self.client, self.request, self.f.limits, self.slot, self.turn)
        self.assertIs(type(packed), dict)
        self.assertEqual(self.calls, [])
        self.consume(packed, None)
        self.assertEqual([endpoint for endpoint,_ in self.calls], ['/v1/responses/input_tokens','/v1/responses'])

    def test_large_default_pack_retains_independent_receiver_count(self):
        packed = pack(self.client, self.request, self.f.limits, self.slot, self.turn)
        self.assertIs(type(packed), dict)
        self.consume(packed, None)
        self.assertEqual([endpoint for endpoint,_ in self.calls], [
            '/v1/responses/input_tokens','/v1/responses/input_tokens','/v1/responses'])


if __name__ == '__main__':
    unittest.main()
