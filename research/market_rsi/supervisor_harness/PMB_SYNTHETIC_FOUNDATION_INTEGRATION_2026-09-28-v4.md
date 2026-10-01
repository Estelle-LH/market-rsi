# PMB synthetic foundation integration receipt v4 — 2026-09-28

## Verdict

Supervisor integration is **PASS, pending fresh independent review** for the
zero-provider foundation. V1–v3 remain rejected and unsynced. V4 removes the
last three P1 paths reported by the v3 reviewer while preserving the previously
verified identity-bound receipt and lease protections.

## V4 closures

- There is no generalized value-accepting receipt issuer. Upstream and
  manifest receipts are constructed and registered inline only after their
  full validators succeed, using validator-derived local values.
- `ExperimentSpec` is sealed against subclassing. The binder requires exact
  base type, captures `canonical_bytes` and declared hash once, computes the
  actual hash once, creates a local exact base object, validates only those
  locals, and writes only the computed hash into the receipt.
- Every accepted experiment spec requires `promotion_eligible is False` for
  every evidence role. Evidence validation never grants an action or promotion
  decision; sealed Final is terminal evidence. Individual episode manifests
  likewise always report no promotion authority.

All previously added external identity/issuance snapshots and exact
store/claim/lifecycle lease ownership checks remain in force. Every foundation
authority bit remains exactly false.

## Exact v4 identity

| Path | SHA-256 |
|---|---|
| `pmb_simple_lane/__init__.py` | `7b055a01b4cdce675a1d834f9b7c67a9ec2e2ee93da1f9e4065aa4fccb9abf37` |
| `pmb_simple_lane/artifact_store.py` | `51434782911cefa261d125ec4d1d978ac6dea7a4e923b8b4b78765d91ecc90de` |
| `pmb_simple_lane/episode_lease.py` | `2f98d86d71856096d9cfe1b3a6209a222ce723c3da2e2bfdd0004c5f8440c51f` |
| `pmb_simple_lane/episode_manifest.py` | `c49de561a397548c955d4a34ccda62e188b5b82d885fe9417c1bcf6ed7e0c16c` |
| `pmb_simple_lane/experiment_spec.py` | `36b1b9c57bf9be835f2bdfc3fe34be6393c198cb3ee3b85e1705c0851025671c` |
| `pmb_simple_lane/upstream_lock.py` | `25eff878da6e1f7e4fe8ca13447289ca3fc5ade8da2912891a378f10b2400b91` |
| `tests/test_pmb_simple_lane_integration.py` | `209eea49783fc85c957d5b5bd9ee20443d906aa06c4e74c130ef50f63d664ace` |
| `tests/test_pmb_simple_lane_episode_lease.py` | `c59bfddc45da559998ea49367659b2d70fab5fd048543422380596734b5489fa` |
| `tests/test_pmb_simple_lane_experiment_spec.py` | `8f2aa4e6c9cdef36e28fe378f91f38bfd2e21fd7dc6bff9e85b6159f8d049c12` |
| `tests/test_pmb_simple_lane_upstream_manifest.py` | `c597ee8b272640d19037a7c95fe1bbb860bfe3fe03f4ff991d4e321259a982e2` |

The ordered aggregate is
`6f52bef30165aaa4b2c804178bf910338a8b0223efbcf4742d4c2db525aa6b66`.
From repo root it is the SHA-256 of the textual `shasum -a 256` output for the
ten `research/market_rsi/...` paths in table order: package `__init__`,
`artifact_store`, `episode_lease`, `episode_manifest`, `experiment_spec`,
`upstream_lock`; then tests `integration`, `episode_lease`, `experiment_spec`,
`upstream_manifest`.

The prospective PMB commit remains
`611d66941717310858683278940df21c33c406f2`; no clone or fetch occurred.

## Verification

- Exact v3 issuer/polymorphism/promotion selection: **6/6 PASS**.
- Complete PMB-focused discovery: **65/65 PASS**.
- `py_compile` over package and focused tests: **PASS**.
- Supervisor bottleneck-gate regression: **6/6 PASS**.
- Scoped diff/whitespace checks: **PASS**.
- Static scan: no network, subprocess, dynamic execution, Docker, provider,
  payment, training, evaluation, publication or release capability.

An initial selector-only command guessed five stale unittest method names and
returned five loader `AttributeError`s while the correctly named binder probe
passed. No code verdict used that command. Current names were enumerated from
source; the exact six-test selection and full 65-test discovery then passed.

## Residual gates

Fresh independent review must recompute the exact hashes, replay the complete
v1–v3 canonical attack set, and probe for equivalent issuer, polymorphism,
promotion, identity and lease paths. Until PASS, v4 remains unsynced. Even
after PASS, PMB/source/package intake, real episode acquisition/opening,
Docker/runtime, paid Controller/provider use, hidden Dev, sealed Final,
training, empirical evaluation, release, commit, tag, push and publication
remain separately blocked and require their own gates and applicable
authorization.
