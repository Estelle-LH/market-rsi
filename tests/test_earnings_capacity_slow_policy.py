"""Explicit foreground override on actual capacity forecast; scripted HTTPS."""
import unittest
from unittest.mock import patch
from copy import deepcopy
from pathlib import Path

import earnings_entry as entry
import earnings_clock as clock
import test_earnings_capacity_forecast as f


class CapacitySlowPolicyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = f._ForecastFixture(self)

    def policy(self, **changes):
        value = {"schema": "edgar_foreground_slow_call_policy_v1",
            "source_commit": self.fixture.context['source_commit'],
            "original_runtime_request_timeout_seconds": self.fixture.runtime['request_timeout_seconds'],
            "effective_socket_timeout_seconds": 600,
            "role_and_global_deadlines_unchanged": True, "retry_allowed": False}
        value.update(changes)
        return f._save(self.fixture.root/'transport-policy.json', value)

    def test_original_default_timeout_unchanged(self):
        before = deepcopy(self.fixture.runtime)
        self.assertEqual(self.fixture.service().socket_timeout(), before['request_timeout_seconds'])
        self.assertEqual(self.fixture.runtime, before)

    def test_real_capacity_forecast_https_receives600_not180(self):
        bound = self.policy()
        service = self.fixture.service(transport_policy_binding=bound)
        self.fixture.http.timeout = 600
        before = self.fixture.prior_path.read_bytes()
        worker = self.fixture.worker()
        output = self.fixture.invoke(worker, replies=[self.fixture.final()], service=service)
        self.assertEqual(entry.strict_json(entry.checked(output['result']).decode())['status'], 'COMPLETED_SCORED')
        self.assertTrue(self.fixture.connections)
        self.assertTrue(all(180 < c.timeout <= 600 for c in self.fixture.connections))
        self.assertEqual(self.fixture.prior_path.read_bytes(), before)

    def test_policy_drift_fails_before_provider(self):
        bound = self.policy()
        service = self.fixture.service(transport_policy_binding=bound)
        Path(bound['path']).write_text('{}')
        with patch.object(clock, 'boot_id', return_value=f.BOOT), self.assertRaises(ValueError):
            service.forecast(self.fixture.worker(), self.fixture.slots[0])
        self.fixture.factory.assert_not_called()

    def test_source_types_limits_deadline_retry_and_extra_fields_rejected(self):
        invalid = [dict(source_commit='b'*40), dict(effective_socket_timeout_seconds=601),
            dict(effective_socket_timeout_seconds=600.0), dict(role_and_global_deadlines_unchanged=1),
            dict(retry_allowed=True), dict(original_runtime_request_timeout_seconds=181), dict(extra=True)]
        for changes in invalid:
            path = self.fixture.root/'transport-policy.json'
            if path.exists(): path.unlink()
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.fixture.service(transport_policy_binding=self.policy(**changes))
        self.fixture.factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
