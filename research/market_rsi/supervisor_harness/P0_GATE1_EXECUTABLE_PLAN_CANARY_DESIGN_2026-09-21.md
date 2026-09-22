# Gate 1 zero-provider executable-plan canary design

Date: 2026-09-21  
Status: fixture and test design implemented.  The integrated compiler now
accepts the exact frozen fixture and its deterministic hashes, but the dedicated
runner, complete adversarial execution and stable-byte independent review are
still pending.  This document is not a network, provider, fetch, release, or
data-admission authorization.

## Question and pass boundary

The canary tests one narrow statement: the exact synthetic Controller decision
can compile, without a model call or any I/O, through

`decision -> trusted broker task -> frozen Train materialization -> exact request manifest -> execution receipt contract`.

A pass means only that trusted local code can produce one deterministic,
hash-bound, non-executing plan and reject every declared adversarial mutation.
It does not establish current provider semantics, source rights, trade
availability, response quality, real model authorship, public fetching, formal
data admission, or prediction improvement.

The canary must finish with all of these exact assertions:

```json
{
  "provider_calls": 0,
  "provider_cost_usd": "0",
  "network_requests_made": 0,
  "bytes_fetched": 0,
  "public_fetch_performed": false,
  "dev_data_read": false,
  "final_data_read": false,
  "formal_data_admitted": false
}
```

No offline fake should be counted as a provider.  This canary bypasses the
Controller adapter entirely and starts from the frozen synthetic decision.

## Frozen valid case

The authority is
`p0_gate1_executable_plan_canary_fixtures.py`:

- exact sample prose: `Select the first, middle, and last games by game_date
  and game_id from the frozen public Train catalog.`
- exact operation: `fetch_fixed_public_sample`;
- bounds: 6 requests, 2,000,000 response bytes, 15 minutes, source/provider
  cost `0`;
- catalog commitment ID: `gate1_synthetic_train_catalog_v1`;
- catalog SHA-256:
  `33722e897d13213298c00009511e962cfae3b72464cc053345e183dc21a02068`;
- selected IDs: `train-game-001`, `train-game-003`,
  `train-game-005`;
- exact paging: limit `100`, offsets `[0, 100]`, hence six GET requests.

The commitment registry must label this catalog `synthetic_canary_only`.  It
must never serve as a production catalog admission.  A future real catalog
needs a separately reviewed trusted commitment ID and must not reuse this ID.

## Compiler contract and actual integration points

The Wave 2 compiler module is
`supervisor_harness/p0_gate1_plan_compiler.py`.  Its pure entry point should
accept the decision, exact packet, catalog bytes, and a trusted catalog
commitment ID.  It must resolve the expected SHA from an internal immutable
registry.  It must not accept a caller-supplied hash as authority.  The agreed
result schema is `market_p0_gate1_compiled_plan_bundle_v1`, containing:

- `schema`;
- `broker_task` and `broker_task_canonical_sha256`;
- `materialization` and `materialization_canonical_file_sha256`;
- `exact_request_manifest` and
  `exact_request_manifest_canonical_sha256`;
- `execution_receipt_contract` and
  `execution_receipt_contract_canonical_sha256`;
- `claim_boundaries`.

The inner manifest schema is
`market_p0_gate1_exact_request_manifest_v1`.  It binds the trusted handler
chain, task hash, catalog commitment, materialization hashes,
`request_plan_inputs_sha256`, exact sample IDs, raw trade-builder manifest
hash, request URLs/queries, and hard budget.  Source mapping from Controller
source `polymarket_official_trades` to execution source
`polymarket_public_trades_v1` is trusted registry data, never Controller text.

The compiler must perform these checks in order:

1. Require the exact `expected_packet()` value and immutable trusted constants,
   not merely a packet that validates against its own altered hard limits.
2. Compile the decision with `validate_and_compile`; require the exact
   source/operation/rule capability and the registered handler chain.
3. Resolve `catalog_commitment_id` to the trusted synthetic hash and verify the
   exact catalog bytes before parsing.
4. Run `p0_gate1_sample_materializer.materialize` with the registered rule ID.
5. Recompute each selected full-row digest from the frozen catalog and compare
   it with every `request_plan_inputs[*].input_sha256`; do not accept an
   arbitrary well-formed 64-hex digest.
6. Build the trade envelope from trusted mappings only.  Require limit exactly
   `100`, offsets exactly `[0, 100]`, six requests, 2,000,000 bytes and 900
   seconds.  Do not copy URL, host, path, query, limit, offsets, headers,
   method, retry, redirect, auth, paid, or write settings from the decision.
7. Run `p0_gate1_trade_query.build_bundle`, wrap the raw builder manifest in
   the exact manifest, and bind every intermediate canonical hash.
8. Recompute the complete bundle once more before returning it.

The standalone runner should be
`supervisor_harness/run_p0_gate1_executable_plan_canary.py::execute(output)`.
It uses only the frozen fixture and compiler, creates a fresh output directory,
writes canonical artifacts with exclusive creation, runs the valid case and all
adversarial vectors, then writes its result last.  It must not import or invoke
`TinkerGLMBackend`, `OfflineGate1ProviderFake`, the public fetcher, watched
fetcher, or any network transport.

After the standalone canary passes, the production wiring point is
`p0_gate1_controller_adapter.run`, immediately after the existing
`validate_and_compile(decision, packet)` call.  The adapter should save the
compiled artifacts before declaring `valid_plan_only_decision`.  Its caller
must supply only a supervisor-selected trusted catalog commitment, not catalog
authority from model output.  `p0_gate1_controller_outer._adapter_success`
must independently recompile and byte/hash-compare every added artifact.
`p0_gate1_controller_outer.REQUIRED_SOURCE_FILES` and the release manifest must
then include the compiler, materializer, trade builder, and production canary
runner.  These production changes are outside this design task.

## Artifact layout

The standalone runner uses a fresh directory and writes:

| Artifact | Schema or content | Required binding |
|---|---|---|
| `decision.json` | `market_p0_gate1_controller_decision_v2` | canonical decision hash |
| `catalog.json` | `market_p0_gate1_train_catalog_v1` | exact-byte trusted commitment |
| `broker-task.json` | contract task schema | recomputation from decision + packet |
| `materialization.json` | `market_p0_gate1_fixed_sample_materialization_v1` | body commitment, full canonical and file hashes |
| `exact-request-manifest.json` | `market_p0_gate1_exact_request_manifest_v1` | task/materialization/input/raw-manifest hashes |
| `execution-receipt-contract.json` | `market_p0_gate1_trade_receipt_contract_v1` | exact manifest hash and zero-risk constraints |
| `compiled-bundle.json` | `market_p0_gate1_compiled_plan_bundle_v1` | all preceding canonical hashes |
| `adversarial-receipt.json` | `market_p0_gate1_executable_plan_adversarial_receipt_v1` | every case rejected before its declared artifact boundary |
| `canary-result.json` | `market_p0_gate1_executable_plan_canary_v1` | all files, tests, counts, and zero-side-effect assertions |

The result schema is:

```text
schema: market_p0_gate1_executable_plan_canary_v1
passed: boolean
fixture_schema: market_p0_gate1_executable_plan_canary_fixture_v1
fixture_source_sha256: sha256(file bytes)
catalog_commitment_id: exact ID
decision_canonical_sha256: sha256(canonical decision)
artifact_sha256: exact map of artifact filename -> file sha256
compiled_bundle_canonical_sha256: sha256(canonical bundle)
sample_ids: exact ordered three-item list
requests_planned: 6
adversarial_case_count: integer
adversarial_cases_rejected: integer
adversarial_receipt_sha256: file sha256
provider_calls: 0
provider_cost_usd: "0"
network_requests_made: 0
bytes_fetched: 0
public_fetch_performed: false
dev_data_read: false
final_data_read: false
formal_data_admitted: false
synthetic_only: true
network_execution_authorized: false
```

`passed` is true only when the valid compiled bundle equals an immediate
independent recomputation, every listed hash matches, all adversarial cases are
rejected before their declared boundary, and every zero-side-effect value is
exact.  A skip, expected failure, or known gap cannot count as a pass.

The adversarial receipt records only `case_id`, stage, expected boundary,
`rejected`, exception type and SHA-256 of the exception text.  It must not store
credentials or model prose.  It has the same zero-side-effect fields as the
main result.

## Adversarial suite

The declarative vector list covers:

- hash tampering at catalog, materialization, selected-input, manifest and
  compiled-bundle layers;
- model-supplied URL, handler and other authority;
- unknown operation and unknown query parameter;
- Dev/Final text, row role and catalog scope;
- request, byte and time budget expansion;
- duplicate fields in decision, catalog and builder JSON;
- duplicate or insufficient samples;
- retry, redirect, authentication, paid-access and write attempts;
- weakening the emitted execution policy after compilation.

It also preserves the Wave 1 audit blockers as mandatory regression cases:

1. shallow alias mutation of `SOURCE_REGISTRY` or `RIGHTS_POLICY` after packet
   construction;
2. a modified catalog accompanied by a caller-self-computed matching hash;
3. an arbitrary syntactically valid selected-row `input_sha256`;
4. limit `50` with offsets `[0, 100]`, which leaves a pagination gap;
5. packet hard-limit mutation paired with oversized decision bounds;
6. missing materialization or request-input commitments;
7. scientific-source to execution-source mapping substitution;
8. relabelling the offline request builder as a network executor.

These cases are release blockers until the integrated compiler rejects them.
The current Wave 1 modules alone must not be described as having closed them.

## What can run now and what is deferred

Immediately runnable, offline:

- `test_p0_gate1_executable_plan_canary_fixtures.py` validates the frozen
  catalog, literal hashes, selected rows, six exact raw trade requests,
  receipt contract, threat coverage, duplicate parsers and current direct
  authority/scope denials.  It now also compiles the exact complete
  decision-to-manifest bundle twice and compares every canonical/file hash to
  literals; this focused test passes locally.
- Existing focused tests for the research contract, materializer and trade
  builder can run beside it.

Deferred until integration:

- execution of every declarative adversarial vector through one dedicated
  canary runner, including missing commitments, mapping substitution and
  offline-builder/executor confusion;
- the limit-50 regression at the direct builder boundary (the integrated
  compiler currently supplies fixed limit 100, but the lower-level builder's
  acceptance surface still needs stable review);
- post-compilation tamper detection;
- writing and validating the complete canary/adversarial receipts;
- adapter/outer-runner artifact and release-manifest wiring.

No provider, network, public data fetch, Dev/Final access, formal admission,
commit, push, or publication is part of either the current fixture tests or the
future standalone compiler canary.
