# PASS · trusted local-root receipt design

## Scope and decision

This document resolves only `trusted_local_root_receipt_design` in
`SUPERVISOR_P0_ADMISSION_INTEGRATION_2026-09-22-v5.json`.

**Verdict: PASS for implementation.** Replace the compiled-in personal roots
with one explicitly supplied, machine-local, candidate-only trust receipt. The
trusted outer Supervisor must supply both the receipt's absolute path and the
expected SHA-256 of its exact bytes. Neither value may be discovered from the
environment, current working directory, Git configuration, home-directory
expansion, a repository search, or a default path.

This design does not admit Train data and does not authorize a network call,
provider access, publication, rights claims, Dev/Final access, or an
improvement claim. The receipt and raw artifacts stay outside Git. Only this
schema and synthetic test fixtures may be repository content.

## Observed problem

The v4 consumer correctly retained descriptor chains and rejected the prior
authority and transient-ancestor attacks, but it compiled one operator's code
and artifact roots into reusable source and required literal equality. That
made a valid clone, Git worktree, CI checkout, or future open-source
installation fail solely because its absolute root differed.

The replacement must preserve two separate properties:

1. **configuration authenticity**: the trusted caller selected these exact
   receipt bytes; and
2. **pathname integrity**: the selected roots and files were opened without
   following symlinks or changing identity during the read.

A pathname check cannot authenticate the configuration that named the path,
and a digest inside the receipt cannot authenticate itself. The separately
supplied full-file digest is therefore mandatory.

## Trust model

Trusted:

- the outer Supervisor process and the two explicit arguments it supplies;
- the installed Python/runtime boundary already governed by the protocol
  release and runtime canaries;
- root-owned or current-effective-user-owned, non-group/world-writable path
  components opened by retained descriptors;
- an exact annotated release and controlled-source manifest independently
  checked before the Supervisor creates the local receipt.

Untrusted:

- process environment, current directory, shell aliases and implicit Git
  discovery;
- the receipt pathname by itself, receipt content by itself, repository
  content that tries to name a receipt, and all raw artifact pathnames;
- symlinks, hard links, mutable directory entries, alternate origins,
  uncommitted controlled source, malformed JSON and unknown fields;
- all data/provider/rights/timing/admission claims contained in artifacts.

If an attacker controls both explicit arguments, the caller trust boundary is
already lost. Even then, the consumer must still enforce its code-owned
standalone-origin, release, artifact, candidate-only and false-authority
constraints; receipt fields cannot relax them.

## Exact trusted-caller interface

The production API is keyword-only and has no defaults:

```python
integrate_candidate(
    *,
    trust_receipt_path: pathlib.Path,
    expected_trust_receipt_sha256: str,
) -> dict
```

The production CLI requires both flags:

```text
python3 -m supervisor_harness.p0_candidate_admission_integration \
  --trust-receipt /ABSOLUTE/MACHINE-LOCAL/PATH/receipt.json \
  --expected-trust-receipt-sha256 <64-lowercase-hex>
```

Rules:

- reject positional substitutes, omitted values, non-`Path` API paths,
  non-absolute paths, noncanonical lexical paths, `~`, `.` or `..` components,
  NULs, uppercase/short/all-zero digests, and paths longer than 4,096 bytes;
- do not read any environment variable and do not call `Path.cwd()`,
  `Path.home()`, `expanduser()`, repository search, or a default constructor;
- ignore unrelated attacker-set environment values and caller CWD;
- validate the expected raw receipt SHA-256 before parsing or using any field;
- do not echo absolute roots in the returned candidate receipt or normal logs.

The expected SHA-256 is an authenticity assertion from the trusted caller, not
a secret. An invocation record may retain it outside Git.

## Canonical receipt schema

The top-level object has exactly these keys:

```text
schema, config, config_sha256
```

`schema` is exactly `market_rsi_trusted_local_root_receipt_v1`.
`config_sha256` is lowercase nonzero 64-hex and equals
`market_rsi.digest(config)`: SHA-256 of UTF-8 JSON serialized with sorted keys,
compact separators, ASCII escaping and non-finite values forbidden.

`config` has exactly these keys:

```text
receipt_id, purpose, repository, artifact_store,
candidate_contract, claim_boundaries
```

- `receipt_id`: 1-96 characters matching
  `[a-z0-9][a-z0-9._-]*`; it is an audit identity, not admission authority.
- `purpose`: exactly `p0_2024_train_candidate_read_only`.
- `repository`, `artifact_store`, `candidate_contract` and
  `claim_boundaries`: exact objects defined below; no additional members.

### `repository`

Exact keys and constraints:

| Key | Required value |
|---|---|
| `code_root` | Canonical absolute checkout/worktree path selected on this machine; no trailing slash except `/`, which is forbidden as a root. |
| `origin` | Exactly `https://github.com/Estelle-LH/market-rsi.git`. |
| `integration_source_relative` | Exactly `research/market_rsi/supervisor_harness/p0_candidate_admission_integration.py`. |
| `release_tag` | `market-rsi-protocol-v` followed by the existing lowercase tag grammar; maximum 96 characters. |
| `release_commit` | Exact nonzero 40-lowercase-hex commit named by the annotated tag. |
| `release_tag_object` | Exact nonzero 40-lowercase-hex annotated tag object. |
| `controlled_source_sha256` | Exact nonzero 64-lowercase-hex digest of `protocol_source_release.source_hashes()`. |
| `controlled_source_file_count` | Positive JSON integer, not Boolean, equal to the recomputed exact file count. |
| `publication_receipt_sha256` | Exact nonzero 64-lowercase-hex digest of the canonical `market_rsi_protocol_publication_v1` object independently returned when the Supervisor verified the published release. |

The receipt for v5 must name the future post-implementation release. The
reviewed v4 digest is historical evidence, not a releasable v5 identity, and
the earlier release tag cannot be relabelled or moved.

### `artifact_store`

Exact keys:

```text
artifact_root, role, artifacts
```

- `artifact_root` is a canonical absolute directory selected on this machine.
- `role` is exactly `read_only_pinned_candidate_bytes_only`.
- `artifacts` is an object with exactly `catalog`, `ledger`,
  `ledger_receipt`, and `mapping`; no array or extra artifact is accepted.
- Every artifact binding has exactly `relative_path`, `size_bytes`, and
  `sha256`. Relative paths use `/`, are nonempty, contain no empty, `.` or
  `..` components, and cannot be absolute.

The four code-owned bindings are:

| Name | Relative path | Exact bytes | SHA-256 |
|---|---|---:|---|
| `ledger` | `artifacts/nfl-2024-train-candidate-ledger-20260922-03/ledger.json` | 348282 | `1c12f53955d1b80a79896c845a563745c910a639036fa9c1ff280a0990c35819` |
| `ledger_receipt` | `artifacts/nfl-2024-train-candidate-ledger-20260922-03/receipt.json` | 370 | `245d70bbfbd0e7f4432829640e8da1eca1e620ce94dcbb0971b170cba9c2e38f` |
| `catalog` | `artifacts/nfl-2024-refresh-20260921-01/catalog/events.catalog.json` | 2491979 | `c89f097b6538ceee46bb7b2950c3fd9ab6971fc5a39ddf00da61e5f589a3c0eb` |
| `mapping` | `artifacts/nfl-2024-refresh-20260921-01/mapping/candidate_mapping.csv` | 105285 | `a8621f15ed703f01add64aaf4869b2ef262b4762d7bd241ba3168d040942008b` |

Receipt values must equal these code-owned bindings. The receipt may select an
artifact root but cannot select different relative files, sizes or hashes.
Existing hard maximums remain code-owned and must be at least the exact sizes;
the receipt cannot raise them.

### `candidate_contract`

Exact keys and values:

```json
{
  "candidate_rows": 285,
  "mapped_rows": 284,
  "mapping_resolved": false,
  "missing_rows": 1,
  "orientation_resolved": false,
  "season": 2024,
  "unresolved_event_id": "17330",
  "unresolved_event_slug": "nfl-kc-phi-2025-02-09",
  "unresolved_reason": "moneyline_missing_or_ambiguous",
  "unresolved_schedule_game_id": "2024_22_KC_PHI"
}
```

### `claim_boundaries`

Exact keys and values:

```json
{
  "candidate_only": true,
  "dev_data_read": false,
  "final_data_read": false,
  "formal_train_admitted": false,
  "network_execution_authorized": false,
  "prediction_improvement_proven": false,
  "provider_origin_authenticated": false,
  "source_rights_verified": false
}
```

The existing recursive false-authority check remains mandatory for the parsed
receipt, all four artifacts, every intermediate object and final output.
Dev/Final fields remain forbidden in ledger content even when false.

## Exact receipt serialization and creation

The full file is UTF-8 without BOM and is exactly:

```python
(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True,
            allow_nan=False) + "\n").encode("ascii")
```

Reject duplicate names at every depth, invalid UTF-8, floats, non-finite
constants, trailing bytes, alternate whitespace, unsorted members and unknown
members. Booleans do not satisfy integer fields.

The Supervisor creates the file outside both roots using a private parent
directory, `O_CREAT|O_EXCL`, mode `0600`, write/fsync, same-directory atomic
rename and parent-directory fsync. It then reads the final file by the same
bounded descriptor procedure, computes the full-file SHA-256, and passes that
digest explicitly. The consumer never creates, rewrites or deletes a receipt.

## Bounded descriptor and ownership protocol

Receipt maximum size is 65,536 bytes. Production support is POSIX only. If
`O_NOFOLLOW`, directory file descriptors, `dir_fd`, or the required stat data
are unavailable, fail closed; do not silently use `resolve()` plus `open()`.

For the receipt path, code root, artifact root, loaded source modules and each
artifact:

1. Open `/` as a directory, then every component with `openat`/`dir_fd`,
   `O_CLOEXEC|O_NOFOLLOW`; directory components also require `O_DIRECTORY`.
2. Retain the complete descriptor chain until all bytes, hashes, identities and
   semantic checks for that object are complete.
3. Before and after reading, compare `fstat` identity
   `(st_dev, st_ino, st_mode, st_size, st_mtime_ns, st_ctime_ns)` with the
   corresponding no-follow directory entry reached through its retained parent.
4. Require every directory component to be a directory, owned by root or the
   current effective UID, with no group/other write bits and no set-ID bits.
5. Require the receipt leaf to be a regular file owned by the effective UID,
   exact mode `0600`, link count one, nonempty and within 65,536 bytes.
6. Require loaded source and artifact leaves to be regular, owned by root or
   the effective UID, not group/other writable, link count one, nonempty and
   within their code-owned byte bounds.
7. Read each leaf exactly once from its descriptor, reject growth past the
   bound, check exact size and SHA-256, and pass only retained immutable bytes
   to validators. Never reopen a validated pathname.
8. Recheck every retained ancestor descriptor and parent entry before close.
   A transient rename/symlink/hardlink attack must either be irrelevant because
   retained descriptors and bytes are used, or produce an identity/ctime/link
   mismatch and fail. No same-inode hardlink is accepted because leaf link
   count must be one.

The receipt file itself must be outside the code root and artifact root. The
code root and artifact root must be unequal and neither may contain the other,
checked both lexically on canonical component lists and by retained directory
identities. Artifacts cannot be in Git because the artifact root is outside the
code root; source/artifact leaf link count one prevents a hard-linked alias.

## Repository and loaded-source checks

All Git calls use `git -C <explicit-code-root>` with prompts disabled and with
Git directory/worktree override variables removed from the subprocess
environment. No call uses caller CWD. The consumer must verify:

- `git rev-parse --show-toplevel` names the exact receipt code root;
- origin is the exact standalone URL above;
- the local tag ref is an annotated `tag` object with the receipt's exact tag
  object and peels to the receipt's exact release commit;
- all controlled paths are clean, exist as canonical regular files and match
  the tag archive;
- recomputed controlled hashes, file count and digest equal the receipt;
- the locally reconstructed publication object hashes to
  `publication_receipt_sha256`.

Remote publication is checked independently by the Supervisor before receipt
creation. The zero-network consumer verifies the sealed local identity; it
does not convert local tag presence into a fresh claim about remote state.

The integration module and these imported critical modules must each have an
exact expected relative source path below the receipt code root, no symlink
component, and matching device/inode when opened through the retained root:

```text
supervisor_harness/p0_candidate_admission_integration.py
supervisor_harness/build_2024_train_candidate_ledger.py
supervisor_harness/formal_train_admission.py
supervisor_harness/p0_2024_outcome_orientation.py
supervisor_harness/p0_polymarket_v2_cursor_acquisition.py
supervisor_harness/protocol_source_release.py
```

Their normalized `__file__` values must equal the receipt-root-derived paths.
Mixed imports from a second checkout fail. This is a source-containment check;
the existing runtime canary remains responsible for interpreter/runtime
identity.

## Returned candidate receipt

The integration result keeps all existing candidate-only fields and adds only
non-authorizing bindings:

- `trusted_local_root_receipt_sha256`: the expected and observed full-file
  digest;
- `trusted_local_root_config_sha256`: the verified config digest;
- `trusted_local_root_receipt_id`: the audit ID;
- repository origin, release tag, release commit, tag object, controlled-source
  digest and publication-receipt digest;
- the four relative artifact path/size/hash bindings.

Do not emit absolute code, artifact or receipt paths. The result remains
`285=284+1`, event `17330` remains explicitly unresolved, and every existing
rights/provider/network/formal-admission/Dev/Final/improvement field remains
false.

## Mutation and replay policy

- Any byte mutation, reformatting, member reorder, appended newline, or
  substitution fails the caller-supplied full-file digest before parsing.
- A semantic edit with a recomputed internal `config_sha256` still fails the
  original caller-supplied full-file digest.
- A trusted caller may deliberately issue new bytes and a new expected digest;
  all code-owned schema, release, root, artifact and false-authority checks
  still apply.
- Exact replay of the same receipt is allowed and must be idempotent because
  this consumer is read-only and grants no admission or execution authority.
  It must yield the same candidate output digest while all bound bytes remain
  unchanged.
- Replay in another clone/worktree fails because `code_root` and loaded-source
  containment differ. The Supervisor must issue a distinct receipt ID and
  digest for that root.
- Reusing a receipt ID with different bytes is rejected within one process or
  canary batch. Cross-process global one-time-use state is deliberately not
  added: one-time semantics belong to paid/admission gates, not this read-only
  candidate configuration.
- Moving an otherwise identical receipt file is permitted only when the
  trusted caller explicitly supplies the new absolute path and same expected
  hash; receipt location itself grants no authority.

## Required tests

### Portable synthetic unit tests

These use temporary, non-personal roots, a tiny synthetic controlled-source
manifest, a local bare Git remote or patched local Git reader, synthetic
artifact bytes and receipts created by one test-only helper. They never depend
on production paths, raw data, network access or a caller CWD.

Required positive cases:

- valid receipt and explicit digest pass in two differently named clones;
- a valid Git worktree passes with its own root-specific receipt;
- exact receipt replay is deterministic;
- unrelated environment and CWD changes do not affect results.

Required negative groups:

| Group | Must fail |
|---|---|
| Caller | missing/default/path string API, relative/noncanonical path, malformed/all-zero digest, env-only or CWD-only discovery |
| Receipt bytes | wrong expected hash, mutation, reordered/reformatted JSON, duplicate/unknown/nested member, BOM/trailing bytes, oversize, wrong internal config digest |
| Ownership/mode | wrong owner, group/world-writable ancestor/file, receipt mode other than `0600`, special bits, hard-linked receipt/source/artifact |
| Path race | receipt/root/file symlink, parent symlink, path substitution, file mutation, ancestor rename, transient ancestor symlink plus same-inode hardlink |
| Separation | equal or nested roots, receipt inside either root, artifact under Git root, source/artifact inode alias |
| Repository | wrong/old origin, lightweight/missing/moved tag, wrong commit/tag object, dirty controlled file, wrong count/digest, tag/current-source mismatch, wrong publication-receipt digest |
| Loaded source | integration module outside root, one critical module from another checkout, symlinked source |
| Artifacts | each wrong relative path, size or hash; missing/extra artifact; artifact substitution during read |
| Semantics | all prior authority aliases; any Dev/Final field; denominator drift; event `17330` inferred, mapped, oriented or removed |
| Replay | clone-A receipt used in clone B; reused ID with changed bytes in one batch |

### Exact local canary

After implementation bytes are independently reviewed, committed, given a new
annotated release tag and verified on the standalone origin, the Supervisor
creates one external mode-`0600` receipt for the real checkout and preserved
artifact store. Run the CLI with the two explicit arguments and no mocks. It
must be zero-network and produce candidate-only `285=284+1`, event `17330`
unresolved, all authority false, and exact receipt/config/release/artifact
digests. The actual receipt, invocation record and raw artifacts remain outside
Git. No such canary can pass before the future release identity exists.

### Verified clone and worktree canaries

Create or reuse an alternate clone and a Git worktree containing the exact
annotated release and controlled bytes. Do not copy raw artifacts into either.
Give each checkout a distinct external receipt naming its absolute code root
and the same external artifact root. Each must pass the local release,
loaded-source and artifact checks. Cross-use of the other checkout's receipt
must fail. These canaries prove path portability; synthetic unit tests alone
do not prove the real release/artifact binding, and the exact local canary alone
does not prove portability.

## Migration and implementation write set

Implementation should make one causal change: replace
`CANONICAL_CODE_CHECKOUT`, `PRESERVED_ARTIFACT_ROOT`, the module-level trusted
contract and implicit `main()` call with the explicit receipt interface above.
Reuse the existing retained-byte semantic validators and false-authority
checks. Do not weaken or rewrite the 2024 candidate semantics.

The implementation worker's complete allowed write set is:

```text
research/market_rsi/supervisor_harness/p0_candidate_admission_integration.py
research/market_rsi/supervisor_harness/test_p0_candidate_admission_integration.py
research/market_rsi/supervisor_harness/test_p0_2024_outcome_orientation.py
research/market_rsi/supervisor_harness/AGENT_LOG_P0_TRUSTED_LOCAL_ROOT_RECEIPT_IMPLEMENTATION_2026-09-22.md
```

No release-helper change, raw artifact, machine-local receipt, personal path,
secret, provider call, admission artifact or protected-split content belongs in
that write set.

## Explicit unresolved items

- The future v5 release tag, release commit, annotated tag object, controlled
  file count/digest and publication-receipt digest do not exist yet. They must
  be filled only after implementation review and a separately authorized
  release; do not reuse or move an old tag.
- Windows is not supported by this descriptor protocol. Supporting it would
  require a separately reviewed native handle/reparse-point design.
- External rights and historical provider/local-receipt timing remain separate
  unresolved evidence gates. A correct local-root receipt cannot satisfy them.
- Event `17330` remains missing/unresolved unless separately verified evidence
  changes the scientific source record; this implementation may not infer it.
