# PMB receipt identity snapshot repair — 2026-09-28

## Scope and authority

Executed v3 step `repair_receipt_identity_snapshots` from
`SUPERVISOR_PMB_SYNTHETIC_FOUNDATION_2026-09-28-v3.json`.

The change is confined to the assigned upstream-lock receipt, manifest-set
receipt and their focused test module. It used local synthetic fixtures and
Python standard-library tests only. No network, clone/fetch, PMB or episode
data, provider, payment, Docker, protected state, training, evaluation,
release or Git mutation occurred.

## Repair

- Both validator receipt dataclasses now use identity equality (`eq=False`),
  retaining object identity hashing required by weak-key registries.
- Each module owns a `weakref.WeakKeyDictionary` outside the receipt object.
  A validator records the exact issued identity only after construction.
- The external snapshot contains every public receipt field plus the internal
  issuance token. Public authenticity checks require the exact registered
  object, revalidate fail-closed field semantics, compare every current field
  with its issuance snapshot and compare the token by identity.
- Constructors do not self-register. Possession or copying of a token cannot
  register a fabricated receipt.

This closes the v2 P1-1 reproductions in the assigned scope: unrelated hashes
on copied receipts, coherent public-diagnostic-to-sealed-Final retargeting,
`object.__new__` plus a copied token, authority-bit expansion, shallow/deep
copies, pickle round trips, `dataclasses.replace`, and field mutation of an
authentic original all fail. The exact unchanged validator-issued identity
continues to authenticate deterministically.

## Verification

- Focused module: `python3 -m unittest -v research.market_rsi.tests.test_pmb_simple_lane_upstream_manifest` — **22/22 PASS**.
- Combined PMB discovery: `python3 -m unittest discover -v -s research/market_rsi/tests -p 'test_pmb_simple_lane_*.py'` — **53/53 PASS**.
- `python3 -m py_compile` over the two source modules and focused test — **PASS**.
- `git diff --check` over the assigned paths — **PASS** (the files are new/untracked in this worktree, so no tracked diff was emitted).
- Static capability scan found only domain vocabulary and explicit comments
  stating that git/network are not invoked; no network/process/provider/
  payment/Docker/training/evaluation/publication capability was added.

## Exact implementation identity

- `research/market_rsi/pmb_simple_lane/upstream_lock.py`
  SHA-256 `951e814affda41dbcb8834823eae6b4e5c4944eee246d0a0dfa0e7d81612e1b6`
- `research/market_rsi/pmb_simple_lane/episode_manifest.py`
  SHA-256 `acac8ecc1a56ab43e421381bb3791ef6ca239325a8e2cd683b8a23f09d7bb7e0`
- `research/market_rsi/tests/test_pmb_simple_lane_upstream_manifest.py`
  SHA-256 `1219e05a9c45a4e1b03577a49ea49622932d97356ccadef5a614f48908fcba5c`

## Result

**PASS for v3 worker step `repair_receipt_identity_snapshots`.** This is a
zero-authority local integrity repair, not PMB runtime admission, data
admission, experiment evidence or release approval. Supervisor integration
and independent review remain required.
