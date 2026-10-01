# AGENT LOG — PMB commitment-construction repair — 2026-09-28

## Verdict

**PASS for `repair_commitment_construction`.**

The exact P1-1 direct-construction bypass reproduced by the independent v1
review is closed within this worker's scope. Already-instantiated source and
episode dataclasses are now serialized and replayed through the same canonical
mapping validators as untrusted mappings. Validation summaries are
verifier-issued receipts: their public constructors fail closed, and public
authenticity checks reject dataclass-shaped objects without the module-private
issuance token.

This result grants no PMB/source/episode/provider/payment/runtime/training/
evaluation/release authority.

## Implementation

- `verify_prospective_upstream` no longer trusts an `UpstreamLock` instance.
  It canonically serializes the instance and calls `UpstreamLock.from_mapping`
  before inspecting any checkout evidence.
- `validate_episode_manifests` and `verify_materialized_episode_files` no
  longer trust an `EpisodeManifest` instance. `_coerce_manifest` canonically
  serializes and revalidates it. Direct `ExposureRecord` instances receive the
  equivalent treatment.
- `ProspectiveUpstreamVerification` can only be issued by
  `verify_prospective_upstream`; `require_validated_upstream_verification`
  verifies exact type, issuance token, zero authority, scope, digest and
  positive counts.
- `ManifestSetValidation` can only be issued by
  `validate_episode_manifests`; `require_validated_manifest_set` verifies exact
  type, issuance token, zero authority, role/count coherence and the sealed
  Final minimum-date rule.
- The canonical result fields and deterministic hashes for valid inputs remain
  unchanged.

## Exact P1 regressions

The focused suite now includes and passes all of the following direct probes:

1. A directly relabeled public January 2026 `EpisodeManifest` is rejected as
   permanently diagnostic.
2. A directly constructed episode instance with invalid venue/domain and an
   empty file set is rejected by canonical validation.
3. Direct `UpstreamLock` instances with a non-official source URL or a
   non-MIT license are rejected before a verification receipt is returned.
4. Direct construction of both validation-summary classes is rejected.
5. `object.__new__` dataclass-shaped upstream and fabricated sealed-Final
   summaries are rejected by the new public authenticity checks.
6. Authentic receipts produced by the two validators pass those checks.

## Verification

- Focused command:
  `python3 -m unittest -v research.market_rsi.tests.test_pmb_simple_lane_upstream_manifest`
  — **17/17 PASS**.
- Compile command:
  `python3 -m py_compile` over both owned source modules and the focused test
  module — **PASS**.
- Whitespace check: `git diff --no-index --check /dev/null <file>` for each
  owned untracked source/test file produced **0 diagnostic bytes**. Exit 1 is
  the expected no-index "files differ" status, not a whitespace failure.
- Static capability scan over both source modules found no `subprocess`,
  `socket`, `requests`, `urllib`, `httpx`, `aiohttp`, `Popen`, `os.system`,
  `exec` or `eval` occurrence.

## Exact source/test identity

- `research/market_rsi/pmb_simple_lane/upstream_lock.py`
  `ff655ca583816596d1603958e1ec1fd2d8aa2613fc6cec8061433f85c5c87e2e`
- `research/market_rsi/pmb_simple_lane/episode_manifest.py`
  `5039a3a6fd1eed1cac188a3e45fb35697d0c0ca44aac1f97116b427023690ba6`
- `research/market_rsi/tests/test_pmb_simple_lane_upstream_manifest.py`
  `8730f9ef5b76ad5d008b1b1755e66cf3ee6fcd3900e1783eb1cd18afa7a24e74`

## Supervisor integration requirement

`bind_synthetic_foundation` must call
`require_validated_upstream_verification` and
`require_validated_manifest_set` before consuming summary fields. Its valid
fixture must obtain the upstream receipt through `verify_prospective_upstream`
instead of constructing `ProspectiveUpstreamVerification` directly. This
worker did not edit the package binder or integration test because those paths
belong exclusively to the Supervisor integration step.

All network, clone/fetch/submodule/package intake, PMB/episode bytes, Docker,
provider/payment, protected state, training/evaluation, release, commit, tag
and push actions remained absent.
