# v0.1.25 D0-to-request bridge tests

- 2026-09-28 — Registered and waiting for one stable integration snapshot. Offline tests only; no provider, network, protected data, release or fetch.

## 2026-09-28 — stable-candidate verification

**Verdict: PASS on the pinned project runtime.**

Focused command:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/market_rsi python3 -m unittest -v supervisor_harness.test_p0_gate1_source_scope_request_plan supervisor_harness.test_protocol_source_release.ProtocolReleaseConfigurationTests
```

Result: 12/12 passed. The tests cover deterministic double compilation, a fixed canonical plan hash, exact URL/method/empty query/body, all-false operational authority, separate future admission, registry/capability/envelope mutation, source/packet/provenance mismatch, caller-supplied URL/extra argument rejection, validator-acceptable ID reassignment, role mutation and internally consistent horizon mutation, release-file inclusion, and absence of direct network/filesystem/process/provider/budget imports.

The first repository discovery was intentionally preserved as environment evidence: bare system Python ran 309 tests and failed with 45 import errors plus one dependent failure because `scikit-learn` was absent. It was not treated as a code result and no package was installed.

Corrected full command using the existing durable pinned runtime:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/market_rsi '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' -m unittest discover -s research/market_rsi -p 'test*.py'
```

Result: 516/516 passed in 62.733 seconds with the same two documented environment skips. `git diff --check` passed. A source-only secret scan over the three changed controlled files found no access-key, private-key, API-key or bearer-token pattern.

Stable exact commitments:

- request-plan canonical SHA-256 `34b45266df887dbf308b196eac865bfc5a3a6b65257c667849605e5a8b9b812c`;
- bridge source SHA-256 `469d0f5e548ceb18d3e7aefdce1d8cf36558c1acbcfa110e9c319fe5eddfe9b2`;
- bridge test SHA-256 `271f817f34de7193763e1deac36ad2771ee85e1db610423b5377fab0b6081733`;
- release manifest module SHA-256 `cf65cee14a0304b8664b1c130e6d8966f746487ad88d581aa03a0e0e5c1aaac7`;
- 341-file local candidate controlled-source digest `c80531648d07f83ff73c1c70c3a8c0d5fd5d02459bb1957c875959daa51faee2`.

No test contacted a provider or source, loaded credentials, fetched bytes, opened catalog/Train/Dev/Final, admitted data, trained/scored a model, or performed a repository publication action.
