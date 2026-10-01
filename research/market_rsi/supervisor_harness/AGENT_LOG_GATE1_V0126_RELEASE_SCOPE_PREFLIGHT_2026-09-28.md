# v0.1.26 release-scope preflight

## 2026-09-28T21:10:33Z — public allowlist, privacy and release-history audit

**Plan-step verdict: PASS only for an isolated clean worktree based on freshly verified `origin/main`; REPLAN / HOLD for direct publication from the current local `main`.** The reviewed 341-file candidate is suitable for a minimal public v0.1.26 release when exactly three source paths are transferred to that clean worktree. The current checkout and current `main` must not be committed or pushed as the release lineage.

This was a read-only audit. It made no implementation or documentation edit other than this preregistered log, and performed no commit, tag, ref update, push, fetch, provider/source contact or other network action.

### Repository and local release history

- Canonical checkout: `/Users/estelle/Developer/market-rsi`.
- Authorized standalone public origin configured locally: `https://github.com/Estelle-LH/market-rsi.git`.
- Current local branch/commit: `main` at `8e4a02b1bf619a9f6e4d09e415c3fcbac089ccca`.
- Current remote-tracking base: `origin/main` at `6403028a39eae77536e033eef6b505294f1699bb`; local `main` is ahead by one commit.
- Local annotated protocol-tag history ends at `market-rsi-protocol-v0.1.25`: tag object `67b8e4a88e22c1f00e60850f521b26282517d682`, peeled release commit `ed4048e55096b763ba763526e768057b5180cdeb`. Local tags v0.1.23, v0.1.24 and v0.1.25 are annotated tag objects. `market-rsi-protocol-v0.1.26` is absent from local refs.
- Remote freshness and remote absence of v0.1.26 were not asserted: proving them needs a network query, which this audit was forbidden to perform. The publication owner must recheck both immediately before creating/pushing the release.

### Blocking current-main ancestry

The unpublished HEAD-only commit `8e4a02b1bf619a9f6e4d09e415c3fcbac089ccca` is `docs: record v0.1.25 D0 preflight hold`. It contains eight operational files that are outside the public release allowlist:

- `research/market_rsi/supervisor_harness/AGENT_LOG_GATE1_V0125_D0_BUDGET_STATE_PREFLIGHT_2026-09-28.md`
- `research/market_rsi/supervisor_harness/AGENT_LOG_GATE1_V0125_D0_EXECUTION_2026-09-28.md`
- `research/market_rsi/supervisor_harness/AGENT_LOG_GATE1_V0125_D0_INDEPENDENT_REVIEW_2026-09-28.md`
- `research/market_rsi/supervisor_harness/AGENT_LOG_GATE1_V0125_D0_LAUNCH_BINDING_PREFLIGHT_2026-09-28.md`
- `research/market_rsi/supervisor_harness/AGENT_LOG_INDEX_2026-09-17.json`
- `research/market_rsi/supervisor_harness/HUMAN_PROGRESS.md`
- `research/market_rsi/supervisor_harness/SUPERVISOR_GATE1_V0125_D0_2026-09-28-v1.json`
- `research/market_rsi/supervisor_harness/SUPERVISOR_GATE1_V0125_D0_2026-09-28-v2.json`

Some contain budget balances, durable-state heads, run/claim identities, internal task routing and preflight receipts. Even staging only the three release files on current `main` would leave this commit in the pushed ancestry. Therefore a normal `git push origin main` from this lineage is prohibited by the requested privacy boundary. Do not force-push, reset away user work, move an old tag or rewrite the public history to work around this.

The current working tree also contains many tracked and untracked agent logs, orchestration plans, authorization/transfer records, dashboard state, progress/roadmap changes and run-specific reviews. None belongs in the v0.1.26 public commit or annotated-tag payload. They must remain preserved locally and unstaged.

### Exact minimal public allowlist

The v0.1.26 commit may contain exactly these three paths, with the reviewed bytes and hashes shown:

1. `research/market_rsi/supervisor_harness/p0_gate1_source_scope_request_plan.py` — SHA-256 `469d0f5e548ceb18d3e7aefdce1d8cf36558c1acbcfa110e9c319fe5eddfe9b2`.
2. `research/market_rsi/supervisor_harness/test_p0_gate1_source_scope_request_plan.py` — SHA-256 `271f817f34de7193763e1deac36ad2771ee85e1db610423b5377fab0b6081733`.
3. `research/market_rsi/supervisor_harness/protocol_source_release.py` — SHA-256 `cf65cee14a0304b8664b1c130e6d8966f746487ad88d581aa03a0e0e5c1aaac7`.

`protocol_source_release.source_hashes()` recomputed 341 controlled files and canonical digest `c80531648d07f83ff73c1c70c3a8c0d5fd5d02459bb1957c875959daa51faee2`, equal to the independently reviewed candidate. The two new source/test paths each occur exactly once in `PROTOCOL_FILES`.

The new bridge source contains only the exact reviewed D0 scientific choice/provenance commitments, public protocol release identifiers, code-owned public documentation URL, deterministic request plan, and all-false execution authority. Its cycle identifier and cryptographic commitments are necessary fail-closed inputs; they contain no credential, user filesystem path, budget journal, account identifier or protected data. The test source contains synthetic/in-memory fixtures and mutation cases only.

A targeted scan of the three allowlisted files found no `/Users/...` or `Library/Application Support` path, API/access/private key, bearer token, account email, durable budget/state root, run receipt, metered-cost record or personal metadata. The only lexical `password` hit was the existing `urlsplit(...).password` rejection in `protocol_source_release.py`, not a credential. The fixed official documentation URL and generic `MarketRSI-Public-Research/1.0` user agent are intentional public protocol constants.

### ARCHITECTURE decision

The current `research/market_rsi/ARCHITECTURE.md` diff should remain uncommitted for this minimal release. It contains no discovered secret or absolute local path, but it does include unnecessary operational details: exact canary and D0 IDs, 4,020/511/0 token counts, `$0.02574585` metering, request-manifest hash, test receipt counts, and pre-publication wording. Those details are not needed to reproduce or audit the 341-file protocol source and conflict with the instruction to exclude run/budget metadata from the open-source release.

If public architecture documentation is desired later, use a separately reviewed sanitized commit that says only that v0.1.26 adds a deterministic plan-only offline D0-to-official-document bridge and grants no fetch, retention, data admission, Train/Dev/Final, training or evaluation authority. Do not reuse the current operational-status diff verbatim.

### Excluded current dirty paths and classes

In addition to `ARCHITECTURE.md`, exclude every current modification or untracked file in these classes:

- every `AGENT_LOG_GATE1_V0125_*` and `AGENT_LOG_GATE1_V0126_*` audit/execution/review log, including this local preflight log;
- `AGENT_LOG_INDEX_2026-09-17.json`, `BOTTLENECK_STATE_2026-09-18.json`, `HUMAN_PROGRESS.md` and `SUPERVISOR_ROADMAP_2026-09-21.md`;
- `GATE1_V0125_D0_AUTHORIZATION_AND_TRANSFER_2026-09-28.md`;
- `SUPERVISOR_GATE1_V0125_D0_2026-09-28-v3.json` and `SUPERVISOR_GATE1_V0125_D0_TO_REQUEST_BRIDGE_2026-09-28-v1.json`;
- all budget/global-state journals, run roots, provider/source receipts, local runtime/tokenizer paths, credential metadata, and future canary/fetch artifacts, whether or not currently under the repository.

The exact three-file allowlist, rather than a broad directory add or `git add -A`, is the release boundary.

### Fresh release identity and required order

Proposed fresh annotated tag: `market-rsi-protocol-v0.1.26`. It must be newly created and never moved or reused. The public-safe tag annotation should contain only: release purpose (deterministic offline D0-to-document request-plan bridge), the three-file scope, focused/full test totals, independent PASS, 341-file digest, and the no-fetch/no-data/no-training authority boundary. It should not list agent-log paths, local roots, budget/state values, provider receipts or personal metadata.

Required sequence:

1. Without changing the current dirty checkout, perform an isolated, credential-free remote-ref check against the literal authorized origin. Require remote `main` to equal the expected base or consciously rebase the release on a freshly reviewed newer public base, and require both `refs/tags/market-rsi-protocol-v0.1.26` and its peeled form to be absent. Stop if the remote moved or the tag exists.
2. Create a separate worktree/branch such as `codex/v0126-d0-document-bridge` from that exact clean remote-main commit. Do not use current `main`, merge the HEAD-only operational commit, or copy any dirty directory wholesale.
3. Transfer only the three allowlisted file versions. Verify their exact SHA-256 values, `git status`, complete diff and absence of every excluded path.
4. Run `git diff --check`, the targeted secret/privacy/path scan, the focused 12/12 suite, and the pinned-runtime full 516/516 suite with the two already documented environment skips. Recompute `source_hashes()` twice and require exactly 341 paths and digest `c80531648d07f83ff73c1c70c3a8c0d5fd5d02459bb1957c875959daa51faee2`.
5. Commit exactly the three allowlisted paths on the clean release branch. Record the full commit ID. Inspect the committed tree/archive, not just the index or working tree.
6. Create annotated tag `market-rsi-protocol-v0.1.26` at that exact commit. Verify locally that the ref object type is `tag`, the peeled commit is the release commit, the old tags are unchanged, and the tagged 341 controlled files byte-match the current clean worktree.
7. Prefer one atomic, fast-forward-only push of the clean release commit to `refs/heads/main` and the new annotated tag. If the remote does not support the atomic update, stop and replan rather than publishing a tag/branch partially or force-updating anything.
8. From the clean release worktree, run `verify_published(tag="market-rsi-protocol-v0.1.26", expected_source_sha256="c80531648d07f83ff73c1c70c3a8c0d5fd5d02459bb1957c875959daa51faee2")`. Independently confirm the remote tag object, peeled commit and public main commit, and preserve that local verification without adding it to the public release commit.
9. Only after publication verification may the separately authorized fresh zero-provider canary run against the exact v0.1.26 commit/tag/digest. Only after that canary passes and is independently reviewed may the separately authorized fresh-ID one-shot watched documentation fetch be considered. Neither later action is part of this release-scope PASS.

### Final boundary

PASS means only that the reviewed candidate can be published safely through the isolated clean-base, exact-three-file procedure above. Direct publication from the current branch remains **REPLAN / HOLD**. This audit grants no permission to publish internal logs or receipts, read credentials, call a provider, fetch a document or API/market data, retain external bytes, access or admit Train/Dev/Final, train, evaluate or score a model, or reuse/retry any prior ID.
