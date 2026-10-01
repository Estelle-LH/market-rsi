# PMB synthetic foundation integration receipt v3 — 2026-09-28

## Verdict

Supervisor integration is **PASS, pending fresh independent review** for the
identity-bound zero-provider synthetic foundation. V1 and v2 remain rejected
and unsynced. V3 closes the receipt-mutation and stale-lease-retarget P1s
reported by the v2 reviewer without adding external authority.

## Identity-bound repair

- Upstream and manifest validator receipts use object identity semantics.
  Each module holds a weak registry keyed by the exact issued object and stores
  a complete field snapshot outside that object. Authentication requires the
  same registered identity, unchanged fields and original token identity.
- The foundation binder applies the same design to its receipt. Public
  construction, shallow/deep copies, pickle, `dataclasses.replace`,
  `object.__new__` with a copied token, and mutation of a copy or the authentic
  original all fail authentication.
- A live episode lease is externally bound to the exact `ArtifactStore`
  object, root path/device/inode, lease ID, journal name, registration-claim
  receipt, state, journal head, next slot and early-stop flag. Every transition
  checks that snapshot before writing, updates it only after replaying the
  appended journal, and revokes ownership after terminal close or recovery.
- Fresh constructors, copied/pickled/object-new handles, lifecycle-field
  mutation, claim drift and stale authentic handles retargeted to same- or
  different-store claims all fail before a transition write.

The foundation receipt continues to expose no path, data bytes, runner or
provider token. `runtime_admitted`, `data_admitted` and
`execution_authorized` remain exactly `false`.

## Exact v3 identity

| Path | SHA-256 |
|---|---|
| `pmb_simple_lane/__init__.py` | `ab7d4c2ae710cf89348b0cd715c3a51d1fe7598d7fa99ccc6c20074349d48afb` |
| `pmb_simple_lane/artifact_store.py` | `51434782911cefa261d125ec4d1d978ac6dea7a4e923b8b4b78765d91ecc90de` |
| `pmb_simple_lane/episode_lease.py` | `2f98d86d71856096d9cfe1b3a6209a222ce723c3da2e2bfdd0004c5f8440c51f` |
| `pmb_simple_lane/episode_manifest.py` | `acac8ecc1a56ab43e421381bb3791ef6ca239325a8e2cd683b8a23f09d7bb7e0` |
| `pmb_simple_lane/experiment_spec.py` | `cd71a67345d58fd343f5620696b417a31f884a3d96c40af3a87826caa70dacb2` |
| `pmb_simple_lane/upstream_lock.py` | `951e814affda41dbcb8834823eae6b4e5c4944eee246d0a0dfa0e7d81612e1b6` |
| `tests/test_pmb_simple_lane_integration.py` | `cb1044308ff3d9f65342cd5225ee429f13aea4c34b69623668f634ad1887901a` |
| `tests/test_pmb_simple_lane_episode_lease.py` | `c59bfddc45da559998ea49367659b2d70fab5fd048543422380596734b5489fa` |
| `tests/test_pmb_simple_lane_experiment_spec.py` | `94a7df9ab52b25df2ea522664a21f09bce5cec6ddb88c35c690e9499479d32ed` |
| `tests/test_pmb_simple_lane_upstream_manifest.py` | `1219e05a9c45a4e1b03577a49ea49622932d97356ccadef5a614f48908fcba5c` |

The exact aggregate is
`96369948b1323a25805d9a1b9d4d48a77b2eb650b614a1da06499d2489fdfa5a`.
From repo root, it is the SHA-256 of the textual `shasum -a 256` output
for the ten `research/market_rsi/...` paths in table order, using this package
order: `__init__`, `artifact_store`, `episode_lease`, `episode_manifest`,
`experiment_spec`, `upstream_lock`; and test order: `integration`,
`episode_lease`, `experiment_spec`, `upstream_manifest`.

The prospective PMB commit identity remains
`611d66941717310858683278940df21c33c406f2`. No clone or fetch occurred.

## Verification

- Exact v2 receipt/retarget adversarial selection: **8/8 PASS**.
- Complete PMB-focused discovery: **58/58 PASS**.
- `py_compile` over every package and focused test file: **PASS**.
- Supervisor bottleneck-gate regression: **6/6 PASS**.
- Scoped diff/whitespace checks: **PASS**.
- Static scan: no subprocess, socket, HTTP client, dynamic execution,
  provider, Docker, training, evaluation, publication or release capability.

One initial selector-only command guessed two stale test names and returned two
`AttributeError` loader errors while five correctly named probes passed. No
code verdict was taken from that command. The current names were enumerated
from source; the exact eight-test selection then passed, followed by complete
58-test discovery.

## Residual gates

A new independent reviewer must rehash this exact v3 snapshot, replay every
v1/v2 reproduction and seek equivalent identity-registry or lifecycle attacks.
Until that review passes, v3 is not accepted or synced. Regardless of its
outcome, PMB/source/package intake, real episode acquisition or opening,
Docker/runtime construction, paid Controller/provider use, hidden Dev, sealed
Final, training, empirical evaluation, release, commit, tag, push and
publication remain separately blocked and require their own gates and
applicable authorization.
