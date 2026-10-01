# Independent PMB exact-spec foundation review v4 — 2026-09-28

## Verdict

**PASS**

Fresh read-only exact-hash review found no P0 or P1. V4 closes the three v3
findings: module-owned validators no longer expose arbitrary value-accepting
receipt issuers; the foundation binder requires the exact sealed
`ExperimentSpec` type and reads the original commitment bytes/hash exactly
once; and every evidence role remains explicitly non-promotional. This PASS is
scoped only to the zero-provider local synthetic foundation.

## Exact identity

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

The reviewer independently reproduced the documented ordered aggregate
`6f52bef30165aaa4b2c804178bf910338a8b0223efbcf4742d4c2db525aa6b66`.
The integration receipt matched
`dd4b9f93e0fb3e2151539ab170bf507c1894cfdc182e0278d26989b116b4be91`.
The v4 plan as reviewed before recording this result matched
`95d0beca8ec512243a2e89d3f4cce7d78d9fb0ba72c7d5f1add08aeff80886ce`.

## Independent verification

- Complete PMB-focused discovery: **65/65 PASS**.
- Supervisor bottleneck-gate regression: **6/6 PASS**.
- In-memory syntax compilation of all ten reviewed Python constituents:
  **10/10 PASS**.
- Scoped `git diff --check`: **PASS**.
- AST/static capability scan: no network client, subprocess, Docker, provider,
  payment, training, evaluation, publication or release import/capability.
- Canonical adversarial probe: **PASS**, SHA-256
  `fa3c8078ac6a98b29e21cf89e1a3aefc1bf72466137f2399e961022d78a9253c`.

One initial reviewer-only descriptor probe stopped with `KeyError` because the
probe replaced the slot descriptors before saving the pre-existing fixture's
values. The corrected probe saved those values first and passed. No source
verdict used the failed invocation, no repository file was edited, and the
original descriptors were restored in `finally`.

## Canonical adversarial probe

- Enumerated module-owned callables accepting all caller-selected receipt
  fields. Accepted arbitrary issuer paths were empty for upstream, manifest and
  foundation receipts.
- Direct construction with each module-private issuance token still produced
  an unregistered receipt; all three authenticity gates rejected it. No
  module-private registry was edited.
- For upstream, manifest and foundation receipts, direct construction,
  private-token construction, copy, deepcopy, pickle, dataclass replacement,
  `object.__new__`, copied retargeting and mutation of the original authentic
  receipt all failed closed.
- `ExperimentSpec` was the exact base type; dynamic subclass construction was
  rejected. Arbitrary-hash `object.__new__` and `object.__setattr__` instances
  were rejected. A temporary descriptor/metaclass probe observed exactly one
  original `canonical_bytes` read and one original `sha256` read; the issued
  foundation hash equaled SHA-256 of the captured bytes.
- `promotion_eligible=false` was accepted and `true` was rejected for
  `public_diagnostic_train`, `train`, `hidden_dev` and `sealed_final`.
  True/false-like alternatives (`True`, `0`, `1`, `None`, string, list and
  object) were rejected. Every role's manifest-level promotion claim was
  false. A valid synthetic 20-date sealed-Final set bound only a zero-authority
  evidence receipt.
- Directly reconstructed, copy, deepcopy, pickle and `object.__new__` lease
  handles could not advance and produced zero additional writes. Original
  lifecycle-field, root-identity, store, registration-claim, same-store stale
  retarget and different-store stale retarget attacks likewise rejected with
  zero additional writes.
- Registration/lifecycle recovery stayed one-shot: an orphan blocked normal
  advancement and closed only as `unresolved`; a simulated crash after the
  terminal lease event but before registry closure reconciled the exact
  `closed_passed` outcome without reclassification or reopening.

## Findings and residual assumptions

No P0/P1 remains in the reviewed scope. The weak identity registries are
intentionally process-local authenticity boundaries: copied or restarted
receipts/handles do not authenticate. As with any in-process Python control,
code allowed to rewrite module globals is outside this probe; the review did
not edit those registries. None of these objects grants runtime, data,
execution or promotion authority.

## Residual gates

This PASS does not admit or fetch PMB/source/package bytes, open real episodes,
run Docker, call a provider, spend funds, access hidden Dev or sealed Final,
train, evaluate, release, commit, tag, push, sync or publish. Each remains
blocked behind its own reviewed gate and applicable authorization. V1-v3 remain
rejected historical evidence; only this exact v4 aggregate passed.

## Authority boundary

The review was read-only against the repository and used only automatically
removed temporary synthetic fixtures. No network, PMB/real episode bytes,
Docker, provider/payment, protected state, training/evaluation, release or Git
mutation occurred.
