# AGENT LOG — PMB synthetic foundation independent review — 2026-09-28

## Verdict

**REPLAN**

Fresh, independent, read-only adversarial review found **no P0** and **two P1
integrity failures**.  The snapshot does not grant runtime, data, provider,
payment, training, evaluation, release or execution authority, but it does not
yet satisfy its claimed fail-closed validation and one-shot restart contracts.
The reviewer edited no tracked file.

## Exact reviewed identity

Supervisor-supplied source/test aggregate:
`03c9648e308e9664bb36f45fb17a42ef909e77bb531c9d0a0ba5508f4d412eea`.
Every constituent listed in the integration receipt was independently
rehashed and matched, as did integration receipt SHA
`a9c9c4842908acb4af3583dfad008678ba2284744ba351d0043f43200d9afb4e`.

The aggregate recipe, later supplied by Supervisor, is the SHA-256 of the
ordered `shasum -a 256` output for the six package files followed by the four
focused test files in the same order used by the receipt.  Constituent hashes
are the authoritative identity.

## Replayed verification

- PMB focused discovery: **41/41 PASS**.
- Bottleneck-gate regression: **6/6 PASS**.
- `py_compile` and scoped `git diff --check`: **PASS**.
- Static scan: no subprocess, socket, requests, urllib, httpx, aiohttp,
  `Popen`, `os.system`, `exec` or `eval` capability.

Passing tests did not cover the two bypasses below.

## P1-1 — Public dataclass construction bypasses validation

The validators trust already-instantiated public dataclasses instead of
replaying the invariants enforced by `from_mapping`.

The reviewer directly constructed an `EpisodeManifest` for a known public
January 2026 ID with role `train`, invalid venue/domain and no files, then
passed it to `validate_episode_manifests`.  Observed:

```text
DIRECT_MANIFEST_ACCEPTED ('train',) 1
```

The reviewer also directly constructed an `UpstreamLock` with a non-official
URL, non-reviewed commit, proprietary license, missing license-tree relation
and an arbitrary one-file tree, then passed it to
`verify_prospective_upstream`.  Observed:

```text
DIRECT_UPSTREAM_ACCEPTED False 1 c7b559efdc2ae121434e343b915eb0d43b1b278931dee4e3467852054dfa8995
```

Freely constructed `ProspectiveUpstreamVerification` and
`ManifestSetValidation` summaries could also be bound as sealed Final:

```text
FORGED_FINAL_SUMMARIES_BOUND sealed_final False False False 34f27f3075d9dd88c626ff6fd393fddcf1dd0d700b58a01bd2d58b4b324e2890
```

All receipt authority bits remained false, so the bypass did not grant actual
authority.  It did permit false provenance and Final-eligibility commitments.

Required repair:

- Revalidate object instances through the exact mapping validator or prevent
  unchecked public construction.
- Do not treat freely constructible summary dataclasses as validation proof.
- Add negative tests for public-ID relabeling, official source/license drift,
  fabricated Final counts and forged summaries.

## P1-2 — A registered lease can be reconstructed and resumed

After `EpisodeLease.create` durably registered an active synthetic lease, the
reviewer called `EpisodeLease(store, id)` and successfully invoked
`capture_start_snapshot`.  Observed:

```text
REGISTERED_LEASE_REOPENED start_snapshotted
```

This did not launch a process, access PMB/episode bytes, call a provider or
grant execution authority.  It nevertheless violated the advertised
no-resume/one-shot contract and the persisted `mark_unresolved_only`
disposition.

Required repair:

- Prevent a directly reconstructed handle from invoking any live transition.
- Preserve terminal-unresolved-only recovery for the registration-only crash
  window.
- Add a regression for both rejection and valid unresolved recovery.

## Residual gates

Freeze a repaired source/test snapshot and obtain a new independent review.
Until then, do not sync v1 as accepted.  PMB clone/fetch/submodule/package
intake, episode acquisition/opening, Docker/runtime, provider/paid Controller,
hidden Dev, sealed Final, training, empirical evaluation, release, commit,
tag, push and publication remain separately blocked.
