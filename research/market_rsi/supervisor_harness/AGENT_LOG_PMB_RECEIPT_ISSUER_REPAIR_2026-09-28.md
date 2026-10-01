# PMB receipt issuer repair — 2026-09-28

## Scope and boundary

- Plan: `market-rsi-pmb-synthetic-foundation-repair-20260928-04`
- Step: `remove_arbitrary_receipt_issuers`
- Owner: `pmb_receipt_issuer_repair_20260928`
- Changed only the two receipt-producing modules, their focused test, and this log.
- Local source, synthetic temporary fixtures, Python standard library, and unittest only.
- No network, clone/fetch, package download, PMB or episode bytes, Docker, provider, payment, protected state/data, training, evaluation, release, commit, tag, or push.

## Repair

1. Removed `_issue_upstream_verification` and `_issue_manifest_set_validation` entirely. There is no general callable that accepts caller-selected receipt hashes, counts, or roles and inserts them into an authenticity registry.
2. Inlined exact receipt construction and registry insertion at the single successful exit of `verify_prospective_upstream` and `validate_episode_manifests`. Receipt fields come only from the validators' already-checked local variables.
3. Preserved exact-type, identity, issuance-token, and immutable-snapshot checks in both `require_validated_*` functions.
4. Changed `EpisodeManifest.promotion_eligible` to always return `False`. Its docstring states that a role, including `sealed_final`, is only a data commitment and never grants promotion authority.
5. Added a module-callable enumeration/reproduction. It exercises every module-defined callable whose signature accepts all caller-selected receipt fields and confirms that none can return an authentic registered receipt.
6. Added the exact v3 forged sealed-Final reproduction: the old issuer symbol is absent, no enumerated callable registers the chosen hash/count/role tuple, and an object-level forged receipt fails `require_validated_manifest_set`.
7. Added an all-role regression proving `public_diagnostic_train`, `train`, `hidden_dev`, and `sealed_final` manifests each report `promotion_eligible is False`.

## Verification

Focused test:

```text
python3 -m unittest research.market_rsi.tests.test_pmb_simple_lane_upstream_manifest
Ran 25 tests in 0.016s
OK
```

Combined PMB synthetic-lane discovery:

```text
python3 -m unittest discover -s research/market_rsi/tests -p 'test_pmb_simple_lane_*.py'
Ran 63 tests in 0.117s
OK
```

Additional checks:

```text
python3 -m py_compile research/market_rsi/pmb_simple_lane/upstream_lock.py research/market_rsi/pmb_simple_lane/episode_manifest.py research/market_rsi/tests/test_pmb_simple_lane_upstream_manifest.py
PASS

git diff --check -- research/market_rsi/pmb_simple_lane/upstream_lock.py research/market_rsi/pmb_simple_lane/episode_manifest.py research/market_rsi/tests/test_pmb_simple_lane_upstream_manifest.py
PASS

rg -n "^(async[[:space:]]+def|def)[[:space:]]+_?issue" research/market_rsi/pmb_simple_lane/upstream_lock.py research/market_rsi/pmb_simple_lane/episode_manifest.py
NO MATCHES

rg -n "requests|urllib|httpx|aiohttp|socket|subprocess|os\\.system|os\\.popen" research/market_rsi/pmb_simple_lane/upstream_lock.py research/market_rsi/pmb_simple_lane/episode_manifest.py
NO MATCHES
```

## Exact artifact hashes

```text
25eff878da6e1f7e4fe8ca13447289ca3fc5ade8da2912891a378f10b2400b91  research/market_rsi/pmb_simple_lane/upstream_lock.py
c49de561a397548c955d4a34ccda62e188b5b82d885fe9417c1bcf6ed7e0c16c  research/market_rsi/pmb_simple_lane/episode_manifest.py
c597ee8b272640d19037a7c95fe1bbb860bfe3fe03f4ff991d4e321259a982e2  research/market_rsi/tests/test_pmb_simple_lane_upstream_manifest.py
```

## Verdict

PASS for this scoped step. Receipt authenticity remains fail-closed, caller-selected issuance helpers are gone, the v3 forged sealed-Final case is rejected, and manifest roles confer no promotion authority. Integration and independent review remain separate downstream gates.
