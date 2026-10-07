"""Synthetic original proposal transport only; no model/network/data/fits."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from supervisor_harness import coevo_pilot_transaction as p
from supervisor_harness import account_controller_feedback_consumer as c
from supervisor_harness.test_account_controller_feedback_consumer import Fixture, PARENT, OTHER


class Clock(datetime):
    @classmethod
    def now(cls, tz=None): return datetime(2026, 10, 6, 17, 36, tzinfo=timezone.utc)


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.f = Fixture(self.temp.name); self.root = self.f.root
        for mock in (patch.object(c, "CLI", self.f.cli), patch.object(c, "CLI_SHA", c.sha(self.f.cli)), patch.object(p, "datetime", Clock)):
            mock.start(); self.addCleanup(mock.stop)
        self.authorization = {"schema": "market_rsi_bounded_coevo_pilot_authorization_v1", "batch_id": p.BATCH,
            "granted": True, "limits": p.LIMITS, **p.TIMES,
            "account_transfer": {"approved": True, "destination": p.DESTINATION, "requested_model": c.MODEL,
                "serving_snapshot": "unknown", "raw_train_transfer": False, "tools_enabled": False, "automatic_retry": False},
            "closed": {key: True for key in ("Dev", "Final", "external_data", "external_literature", "paid_provider", "release", "push", "promotion")}}
        self.authorization_binding = self.write("authorization", self.authorization)
        self.packet = {"schema": "controller_coevolution_input_v1",
            "bindings": {"feedback": self.f.bindings["feedback"]}, "feedback": self.f.values["feedback"],
            "memory": self.f.values["memory"], "history": self.f.values["history"],
            "pool": self.f.values["pool"], "authority": self.authorization, "overhead": {},
            "provided_parents": [PARENT, OTHER], "provided_source_sha256": [OTHER]}
        self.ledger = {"schema": "market_rsi_coevo_pilot_ledger_v1", "batch_id": p.BATCH,
                       "controller_decisions": [], "attempts": [], "status": "open"}
        self.write("ledger", self.ledger); self.rebind(); self.calls = 0

    def write(self, name, value):
        path = self.root / (name + ".json"); path.write_text(json.dumps(value))
        return {"path": str(path), "sha256": c.sha(path)}

    def rebind(self):
        self.input_binding = self.write("packet", self.packet)
        self.review = {"passed": True, "authorization_sha256": self.authorization_binding["sha256"],
            "input_sha256": self.input_binding["sha256"], "transaction_source_sha256": c.sha(Path(p.__file__)),
            "consumer_source_sha256": c.sha(Path(c.__file__)), "cli_sha256": c.CLI_SHA, "requested_model": c.MODEL}
        self.review_binding = self.write("operation-review", self.review)

    def response(self, packet):
        change = {name: "synthetic nonexecutable hypothesis" for name in p.CHANGE["required"]}
        return {"schema": "controller_coevolution_proposal_v1", "input_sha256": c._digest(packet),
            "feedback_sha256": packet["bindings"]["feedback"]["sha256"], "requested_model": c.MODEL,
            "serving_snapshot": "unknown", "researcher_change": change, "harness_change": change,
            "candidate": self.f.decision(packet), "attribution": "proposal only, not proof"}

    def transport(self, directory, packet, timeout, *, mutate=None, extra_event=None):
        self.calls += 1; response = self.response(packet)
        self.assertLessEqual(timeout, self.authorization['account_transfer'].get('max_call_seconds', 120))
        if mutate: mutate(response)
        c.save(directory / "process.json", {"pid": 123, "command": c._command(directory),
            "cli_sha256": c.CLI_SHA, "input_sha256": c._digest(packet), **c._identity()})
        c.save(directory / "response.json", response)
        events = [{"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(response)}},
                  {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}]
        if extra_event: events.insert(0, extra_event)
        (directory / "events.jsonl").write_text("\n".join(json.dumps(item) for item in events))
        (directory / "stderr").write_bytes(b"")
        c.save(directory / "completion.json", {"exit_code": 0, "timed_out": False, **c._identity(),
            "hashes": {name: c.sha(directory / name) for name in
                ("process.json", "events.jsonl", "stderr", "schema.json", "input.json", "response.json")}})

    def call(self, transport=None):
        return p.call(self.root, self.input_binding, self.authorization_binding,
                      self.review_binding, self.f.repo, transport=transport or self.transport)

    def test_success_original_recovery_schema_and_usage(self):
        first = self.call(); self.assertEqual(self.call(), first); self.assertEqual(self.calls, 1)
        self.assertEqual(first["candidate"]["actual_parent_sha256"], PARENT)
        self.assertEqual(p._file(self.root / "ledger.json")["controller_decisions"][0]["status"], "completed")
        directory = next((self.root / "decisions").iterdir())
        self.assertEqual(p._file(directory / "ack.json")["usage"]["input_tokens"], 10)
        self.assertIn("wall_seconds", p._file(directory / "timing.json"))

    def test_completed_response_recovers_reserved_original_after_accounting_crash(self):
        self.call(); ledger = p._file(self.root / "ledger.json")
        ledger["controller_decisions"][0]["status"] = "reserved"; self.write("ledger", ledger)
        self.call(); self.assertEqual(self.calls, 1)
        self.assertEqual(p._file(self.root / "ledger.json")["controller_decisions"][0]["status"], "completed")

    def test_changed_packet_same_feedback_cannot_resample(self):
        self.call(); self.packet["memory"] = {"changed": True}; self.rebind()
        with self.assertRaisesRegex(ValueError, "claim/input/schema"): self.call()
        self.assertEqual(self.calls, 1)

    def test_cap_and_missing_review_reject_before_claim(self):
        self.ledger["controller_decisions"] = [{"feedback_sha256": str(number) * 64, "status": "completed"} for number in (8, 9)]
        self.write("ledger", self.ledger)
        with self.assertRaisesRegex(RuntimeError, "pilot cap"): self.call()
        self.assertEqual(self.calls, 0); self.assertFalse((self.root / "decisions").exists())

    def test_uncertain_original_never_retries(self):
        def interrupted(*_): self.calls += 1; raise KeyboardInterrupt("unknown completion")
        with self.assertRaises(KeyboardInterrupt): self.call(interrupted)
        with self.assertRaises(FileNotFoundError): self.call()
        self.assertEqual(self.calls, 1)

    def prospective_wait(self, value=300):
        self.authorization['account_transfer']['max_call_seconds'] = value
        self.authorization_binding = self.write('authorization', self.authorization)
        self.packet['authority'] = self.authorization
        self.rebind()

    def test_explicit_controller_wait_reaches_transport_and_cold_replay(self):
        self.prospective_wait(); waits = []
        def late(directory, packet, timeout):
            waits.append(timeout)
            if timeout < 180:
                raise TimeoutError('Virtual late completion, not actual model latency')
            self.transport(directory, packet, timeout)
        first = self.call(late)
        self.assertEqual(waits, [300]); self.assertEqual(self.call(), first)
        self.assertEqual(self.calls, 1)
        directory = next((self.root/'decisions').iterdir())
        self.assertEqual(p._file(directory/'claim.json')['allowed_timeout_seconds'], 300)
        self.assertEqual(p._file(directory/'timeout.json')['allowed_seconds'], 300)

    def test_invalid_controller_wait_rejected_before_original_claim(self):
        for value in (None, True, 0, -1, 301, 300., '300'):
            self.prospective_wait(value)
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Controller timeout'):
                self.call()
        self.assertEqual(self.calls, 0); self.assertFalse((self.root/'decisions').exists())
        self.assertEqual(p._file(self.root/'ledger.json')['controller_decisions'], [])

    def test_controller_wait_clips_to_fresh_deadline(self):
        self.prospective_wait(); deadline = c._time(p.TIMES['deadline_utc'])
        cutoff = datetime.fromtimestamp(deadline.timestamp()-1, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.authorization['selection_cutoff_utc'] = cutoff
        self.authorization_binding = self.write('authorization', self.authorization); self.rebind()
        waits = []
        def recorded(directory, packet, timeout):
            waits.append(timeout); self.transport(directory, packet, timeout)
        with patch.dict(p.TIMES, selection_cutoff_utc=cutoff), patch.object(p, 'datetime') as clock:
            clock.now.return_value = datetime.fromtimestamp(deadline.timestamp()-40, timezone.utc)
            self.call(recorded)
        self.assertEqual(waits, [40])

    def test_slow_review_crossing_cutoff_rejects_before_original_reservation(self):
        actual = p._review
        with patch.object(p, 'datetime') as clock:
            clock.now.return_value = Clock.now()
            def slow_review(*args, **kwargs):
                result = actual(*args, **kwargs)
                clock.now.return_value = c._time(p.TIMES['selection_cutoff_utc'])
                return result
            with patch.object(p, '_review', side_effect=slow_review), \
                    self.assertRaisesRegex(ValueError, 'selection window closed'):
                self.call()
        self.assertEqual(self.calls, 0)
        self.assertEqual(p._file(self.root/'ledger.json')['controller_decisions'], [])
        self.assertFalse((self.root/'decisions').exists())

    def test_deadline_crossed_after_claim_stays_reserved_without_process_or_retry(self):
        self.prospective_wait(); deadline = c._time(p.TIMES['deadline_utc'])
        cutoff = datetime.fromtimestamp(deadline.timestamp()-1, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.authorization['selection_cutoff_utc'] = cutoff
        self.authorization_binding = self.write('authorization', self.authorization); self.rebind()
        with patch.dict(p.TIMES, selection_cutoff_utc=cutoff), patch.object(p, 'datetime') as clock:
            clock.now.side_effect = [datetime.fromtimestamp(deadline.timestamp()-2, timezone.utc), deadline]
            with self.assertRaisesRegex(TimeoutError, 'before original Controller process'):
                self.call()
        self.assertEqual(self.calls, 0)
        self.assertEqual(p._file(self.root/'ledger.json')['controller_decisions'][0]['status'], 'reserved')
        with self.assertRaises(FileNotFoundError): self.call()
        self.assertEqual(self.calls, 0)

    def test_strict_r_h_fields_and_unknown_events_fail_without_second_call(self):
        with self.assertRaisesRegex(ValueError, "strict response fields"):
            self.call(lambda *args: self.transport(*args, mutate=lambda response: response["researcher_change"].update(extra=True)))
        with self.assertRaises(ValueError): self.call()
        self.assertEqual(self.calls, 1)

    def test_unprovided_parent_and_tool_events_rejected(self):
        with self.assertRaisesRegex(ValueError, "unprovided"):
            self.call(lambda *args: self.transport(*args, mutate=lambda response: response["candidate"].update(actual_parent_sha256="f" * 64)))
        self.assertEqual(self.calls, 1)

    def test_tool_event_rejected(self):
        with self.assertRaisesRegex(ValueError, "tools or failed"):
            self.call(lambda *args: self.transport(*args, extra_event={"type": "item.completed", "item": {"type": "command_execution"}}))

    def test_compact_cap_review_and_destination_bindings(self):
        self.review["passed"] = False; self.review_binding = self.write("operation-review", self.review)
        with self.assertRaisesRegex(ValueError, "review drift"): self.call()
        self.rebind(); self.packet["memory"] = "x" * 32768; self.rebind()
        with self.assertRaisesRegex(ValueError, "compact reviewed"): self.call()
        self.assertEqual(self.calls, 0)

    def test_explicit_larger_controller_budget_and_original_replay(self):
        self.authorization['account_transfer']['max_input_bytes'] = 262144
        self.authorization_binding = self.write('authorization', self.authorization)
        self.packet['authority'] = self.authorization
        self.packet['memory'] = 'synthetic aggregate memory ' + 'x' * 40000
        self.rebind()
        first = self.call(); second = self.call()
        self.assertEqual(first, second); self.assertEqual(self.calls, 1)
        self.assertEqual(len(p._file(self.root / 'ledger.json')['controller_decisions']), 1)

    def test_input_budget_requires_positive_integer_and_modern_explicit_value(self):
        for value in (None, True, 0, -1, '65536', 65536.):
            grant = {'account_transfer': {'max_input_bytes': value}}
            with self.subTest(value=value), self.assertRaises(ValueError): p.input_limit(grant)
        with self.assertRaises(ValueError): p.input_limit({'account_transfer': {}})
        self.assertEqual(p.input_limit({'account_transfer': {}}, legacy=True), 32768)
        self.assertEqual(p.input_limit({'account_transfer': {'max_input_bytes': 65536}}), 65536)

    def test_wrong_destination_tools_or_original_window_denied(self):
        original = deepcopy(self.authorization)
        for key, value in (("destination", "different account"), ("tools_enabled", True),
                           ("automatic_retry", True), ("raw_train_transfer", True)):
            self.authorization = deepcopy(original); self.authorization["account_transfer"][key] = value
            self.authorization_binding = self.write("authorization", self.authorization)
            self.packet["authority"] = self.authorization; self.rebind()
            with self.assertRaisesRegex(ValueError, "exact user grant"): self.call()
        self.authorization = original; self.authorization_binding = self.write("authorization", original)
        self.packet["authority"] = original; self.rebind()
        class ClosedClock(datetime):
            @classmethod
            def now(cls, tz=None): return datetime(2026, 10, 6, 18, 12, tzinfo=timezone.utc)
        with patch.object(p, "datetime", ClosedClock):
            with self.assertRaisesRegex(ValueError, "selection window"): self.call()
        self.assertEqual(self.calls, 0)


class TypedActionTests(unittest.TestCase):
    """Actual once-only transaction, synthetic decisions only; no source/fits."""
    def setUp(self):
        from supervisor_harness.test_coevo_pilot_configuration import ConfigurationTests
        self.h = ConfigurationTests(); self.h.setUp(); self.addCleanup(self.h.doCleanups)
        self.legacy = deepcopy(self.h.packet)
        self.packet = self.h.packet
        self.packet['schema'] = 'controller_price_feedback_input_v2'
        self.packet['action_context'] = {'schema': 'price_controller_action_context_v1',
            'available_actions': ['prediction', 'researcher', 'harness', 'request_closed_authority'],
            'identity_configuration': {'pair': {'harness_sha256': 'b' * 64, 'researcher_sha256': 'c' * 64},
                'fixed_context': {'model_sha256': '1' * 64, 'data_scope_sha256': '2' * 64,
                    'evaluation_sha256': '3' * 64, 'authority_sha256': self.h.authorization_binding['sha256'],
                    'resource_policy_sha256': self.h.configuration_binding['sha256']},
                'allowed_write_paths': {'researcher': ['research_capacities/r1.py', 'research_capacities/r2.py'],
                    'harness': ['research_capacities/h1.py', 'research_capacities/h2.py']},
                'protected_paths': ['experiments/nfl_ingame_price_score.py', 'supervisor_harness/paid_budget.py'],
                'reviewer_id': 'synthetic-independent-reviewer'}}
        self.action = 'researcher'
        self.h.response = self.response
        self.bind()

    def bind(self):
        self.h.rebind_config()
        self.h.review.update(action_context_sha256=c._digest(self.packet['action_context']),
            decision_schema_sha256=c._digest(p.SCHEMA_V2))
        self.h.review_binding = self.h.write('operation-review', self.h.review)

    def response(self, packet):
        candidate = self.h.f.decision(packet) if self.action == 'prediction' else None
        capacity = None
        if self.action in {'researcher', 'harness'}:
            config = packet['action_context']['identity_configuration']
            capacity = {'change_id': 'SYNTHETIC-policy-v2', 'axis': self.action,
                'component': 'research_policy' if self.action == 'researcher' else 'feedback_delivery',
                'parent_pair_sha256': c._digest(config['pair']),
                'problem': 'Synthetic repeated finding; not actual research evidence.',
                'proposal': 'Keep a verified negative lesson available to the next decision.',
                'expected_effect': 'Avoid repeating this exact synthetic failed hypothesis.',
                'matched_test': 'Compare parent/new behavior on identical supplied aggregate cases.',
                'downstream_use': 'Next input/decision; proposal alone is not activation.',
                'write_paths': [config['allowed_write_paths'][self.action][-1]],
                'evidence_used': [{'sha256': packet['bindings']['feedback']['sha256'],
                    'finding': 'synthetic finding', 'choice_consequence': 'test a memory policy'}],
                'resources': {'fits': 0, 'seconds': 30, 'threads': 1, 'rss_bytes': 1073741824, 'provider_calls': 0}}
        return {'schema': 'controller_coevolution_action_v2', 'input_sha256': c._digest(packet),
            'feedback_sha256': packet['bindings']['feedback']['sha256'], 'requested_model': c.MODEL,
            'serving_snapshot': 'unknown', 'action': self.action, 'candidate': candidate, 'capacity': capacity,
            'authority_request': 'Specific additional data permission would be required; not granted.'
                if self.action == 'request_closed_authority' else None,
            'attribution': 'Synthetic fixture decision, not live authorship or implemented capacity.'}

    def test_researcher_only_original_and_replay_need_no_dummy_candidate(self):
        first = self.h.call(); second = self.h.call()
        self.assertEqual(first, second); self.assertEqual(self.h.calls, 1)
        self.assertIsNone(first['candidate'])
        self.assertEqual(first['capacity']['resources']['fits'], 0)
        ledger = p._file(self.h.root / 'ledger.json')
        self.assertEqual(len(ledger['controller_decisions']), 1); self.assertEqual(ledger['attempts'], [])
        directory = next((self.h.root / 'decisions').iterdir())
        self.assertEqual(p._file(directory / 'schema.json'), p.SCHEMA_V2)
        self.assertEqual(p._file(directory / 'claim.json')['schema_sha256'], c._digest(p.SCHEMA_V2))

    def test_harness_only_and_prediction_are_distinct_valid_operations(self):
        for action in ('harness', 'prediction', 'request_closed_authority'):
            self.action = action
            response = self.response(self.packet)
            self.assertEqual(p.validate_response(response, self.packet), response)
        self.action = 'harness'
        self.assertEqual(self.h.call()['capacity']['axis'], 'harness')
        self.assertEqual(self.h.calls, 1)

    def test_unreviewed_v2_context_and_schema_deny_before_original_claim(self):
        for field in ('action_context_sha256', 'decision_schema_sha256'):
            self.bind(); self.h.review.pop(field)
            self.h.review_binding = self.h.write('operation-review', self.h.review)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'review drift'): self.h.call()
        self.assertEqual(self.h.calls, 0)
        self.assertFalse((self.h.root / 'decisions').exists())

    def test_protected_context_and_authority_drift_deny_before_original(self):
        config = self.packet['action_context']['identity_configuration']
        config['allowed_write_paths']['researcher'] = ['experiments/nfl_ingame_price_score.py']
        self.bind()
        with self.assertRaisesRegex(ValueError, 'protected'): self.h.call()
        config['allowed_write_paths']['researcher'] = ['research_capacities/r2.py']
        config['fixed_context']['authority_sha256'] = 'f' * 64; self.bind()
        with self.assertRaisesRegex(ValueError, 'authority/resource'): self.h.call()
        self.assertEqual(self.h.calls, 0)

    def test_composite_stale_scope_fake_evidence_and_numeric_resources_rejected(self):
        original = self.response(self.packet)
        mutations = [lambda v: v.update(candidate=self.h.f.decision(self.packet)),
            lambda v: v['capacity'].update(parent_pair_sha256='f' * 64),
            lambda v: v['capacity'].update(write_paths=['../kernel.py']),
            lambda v: v['capacity'].update(write_paths=['experiments/nfl_ingame_price_score.py']),
            lambda v: v['capacity']['evidence_used'][0].update(sha256='f' * 64),
            lambda v: v['capacity']['resources'].update(seconds=True),
            lambda v: v['capacity']['resources'].update(fits=4),
            lambda v: v['capacity'].update(extra='unrecognized scope')]
        for mutate in mutations:
            response = deepcopy(original); mutate(response)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError): p.validate_response(response, self.packet)
        self.packet['action_context']['available_actions'] = ['prediction']
        fresh = self.response(self.packet)  # New input hash; test enablement rather than stale input.
        with self.assertRaisesRegex(ValueError, 'enabled'): p.validate_response(fresh, self.packet)

    def test_failed_original_v2_is_preserved_and_never_resampled(self):
        original = self.h.response
        def invalid(packet):
            response = original(packet); response['capacity']['resources']['fits'] = 4; return response
        self.h.response = invalid
        with self.assertRaises(ValueError): self.h.call()
        with self.assertRaises(ValueError): self.h.call()
        self.assertEqual(self.h.calls, 1)
        self.assertEqual(p._file(self.h.root / 'ledger.json')['controller_decisions'][0]['status'], 'reserved')

    def test_prompt_opt_in_and_legacy_schema_are_separate(self):
        modern = c._prompt(self.packet); legacy = c._prompt(self.legacy)
        self.assertIn('Do not force an R/H mutation', modern)
        self.assertIn('only the field for your selected action is non-null', modern)
        self.assertIn('small actual prediction hypothesis', legacy)
        self.assertNotIn('controller_coevolution_action_v2', legacy)
        self.assertIs(p.response_schema(self.legacy), p.SCHEMA)
        drift = deepcopy(self.legacy); drift['action_context'] = self.packet['action_context']
        with self.assertRaisesRegex(ValueError, 'explicit v2'): p.response_schema(drift)


if __name__ == "__main__": unittest.main()
