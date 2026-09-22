# Gate 1 capability contract — agent work log

- 2026-09-21 14:33 EDT — Started bounded offline work. Owner: `capability_contract`.
- Scope: add a trusted source/operation capability contract and fail closed when a Controller plan asks for a combination the broker cannot execute.
- File boundary: `p0_gate1_research_contract.py` and direct tests only.
- Current truth: the existing broker supports one fixed official-document GET; multi-market trade queries are not yet executable.
- Hard boundaries: no provider call, network request, data fetch, Dev/Final access, commit or push.
- Pass condition: supported combinations compile with trusted executability evidence; unsupported combinations fail closed; focused tests pass.
- Status: running. Result not yet claimed.
- 2026-09-21 14:42 EDT — Implemented the offline contract change in
  `supervisor_harness/p0_gate1_research_contract.py` and its direct test file.
  The Controller-facing `OPERATIONS` set is now derived only from registered,
  executable capabilities; the remaining historical operation names are kept
  separately as known-but-not-executable and fail closed.
- Added the trusted `CAPABILITY_REGISTRY`, keyed by source and operation.  The
  only registered handler is the already-existing one-document snapshot path,
  `p0_gate1_public_fetch.fetch_snapshot:v1`.  Its source-specific exact sample
  prose maps to a trusted `single_registry_document_v1` contract, requires one
  request and zero source/provider cost, and emits explicit capability and
  handler evidence in broker task schema v3.
- Bound the packet's source/question registry and Controller field set to the
  trusted constants.  Added explicit field-authority metadata separating
  Controller scientific fields, Controller execution requests and trusted
  protocol/source/capability/policy/boundary fields.  Trusted nested records are
  copied into the task rather than shared with caller-owned objects.
- Preserved and expanded fail-closed regressions: the historical multi-week
  documentation+metadata plan, every known unimplemented operation, wrong
  source/sample pairing, multi-request and nonzero-cost requests, registry URL
  rewriting, trusted-schema reclassification, authority injection, hard-cap
  violations, forbidden text and duplicate JSON fields all remain rejected.
- Verification: `git diff --check -- supervisor_harness/p0_gate1_research_contract.py supervisor_harness/test_p0_gate1_research_contract.py` passed.
  `python -m unittest supervisor_harness.test_p0_gate1_research_contract supervisor_harness.test_p0_gate1_controller_adapter supervisor_harness.test_p0_gate1_controller_outer supervisor_harness.test_p0_gate1_public_fetch supervisor_harness.test_p0_gate1_watched_fetch supervisor_harness.test_p0_gate1_controller_live_entry supervisor_harness.test_p0_gate1_controller_supervisor_parent`
  passed 55/55 tests in 0.091s.
- No provider call, network access, source fetch, Dev/Final access, commit or push
  occurred.  No runtime failure remains in this bounded task.
- Remaining integration: after the separate trade-query runner and fixed-sample
  materializer pass their own tests, the main coordinator must explicitly add
  their exact source/operation entry, trusted handler ID and strict prose-to-rule
  mapping to `CAPABILITY_REGISTRY`; until then they remain unselectable.  The
  materializer owner reports rule ID
  `first_middle_last_by_game_date_game_id_v1`, catalog schema
  `market_p0_gate1_train_catalog_v1`, and output schema
  `market_p0_gate1_fixed_sample_materialization_v1`; none is pre-registered here.
- Status: complete for the bounded capability-contract task; integration and a
  fresh canary/source commitment remain with the main coordinator.
