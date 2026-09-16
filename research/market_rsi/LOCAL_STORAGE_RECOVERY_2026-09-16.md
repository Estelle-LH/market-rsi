# Local execution after iCloud eviction (2026-09-16)

## What failed

The paid full-cohort aggregate-only controller attempt
`artifacts/nfl-full-cohort-controller-20260916-01` stopped without a valid
decision. During its 21 Tinker turns, frozen source/workspace files in the
iCloud-backed project became `compressed,dataless`; the residency guard correctly
rejected them. The failure is an execution/storage failure, not a prediction
result. Do not reuse this attempt ID, resample its decision, or count it as a
completed research round. Its incremental effective budget cost was
`$1.213125012`; no model candidate, Dev, or Final evaluation ran.

A free canary with only its output moved to `/private/tmp` also failed: its
imports and source snapshot still came from iCloud. At diagnosis, 180 files in
the relevant source directories and 6,091 files in the Python runtime were
`dataless`. Finder displayed: “Unable to complete iCloud Drive sync. Repair
permissions to finish syncing.” This is evidence of a sync problem, not proof
of its sole cause. Available disk space was about 13 GiB on a 926 GiB volume.
Repeated hydration is not the recovery plan. Do not delete or move the iCloud
originals, turn off iCloud, or click account-wide Repair without user approval.

## Local-only execution proof

An independent clone of the *published user fork*, not a copy of the troubled
iCloud Git object store, is at:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local`

Its branch is `codex/market-rsi-round1-v2`, exact commit
`1de56266d6162b74870a3bb48edfed24098b198d`, and `origin` is only
`https://github.com/Estelle-LH/RSIBench-Data.git`. A separate Python 3.12
environment is at `/Users/estelle/Library/Application Support/MarketRSI/runtime-py312`.
The CPU dependencies were installed at the exact versions in
`data_scientist_harness/requirements-cpu.txt`, with a persistent *local* pip
cache under `MarketRSI/pip-cache`. No source or package in this local execution
path was `dataless` at verification.

The zero-cost scripted controller canary
`/Users/estelle/Library/Application Support/MarketRSI/runs/local-runtime-canary-20260916-01`
passed with the actual Codex CLI, 18 successful tool calls, four synthetic CPU
fits, one live public read and one live metadata search; it made zero Tinker
calls and zero market-performance claims. Result SHA256:
`97ece94e2cb03366953eef6caed14453719b687f7d1aa93695db22baaf695959`.
This validates the local execution path only. It does **not** validate a paid
release: the published v1.6.18 release receipt binds the old Python path.

## Budget authority is not yet moved

The original `$200` ledger remains under
`artifacts/kalshi-research-glm53-20260907-01/budget`. A byte-identical,
non-authoritative snapshot (1,905 files; `diff -qr` matched) is at
`/Users/estelle/Library/Application Support/MarketRSI/budget-snapshot-20260916-01`.
Both copies' `journal.jsonl` SHA256 was
`4589c3d6f8bcc0a1770dd32337fd492f3c1f6e554cb48b816500b63dfdcaf84f`.
The copied ledger passed its append-only integrity check. Its snapshot reports
`$85.044572612` provider-metered, `$89.903153492` effective cost,
`$2.30` still reserved, and `$107.796846508` globally available. Of the 23
old unresolved dispatched holds, 22 are setup and one is learning; these
remain charged against the cap at their upper bounds. Do not call them spent or
clear them without terminal evidence. No experiment process was using the
original ledger during copying. The copy must not be used for payment until a
single authoritative ledger location and migration invariant are established.

## Gate before any further paid experiment

1. Run active code, Python dependencies, frozen workspace, and required input
   receipts from a persistent non-iCloud location. Keep iCloud as an untouched
   archive. Verify no `dataless` files and stable hashes before and after a
   zero-cost canary. Do not use `/private/tmp` as the sole persistent copy.
2. Because the runtime identity changed, publish a fresh harness version,
   same-source/runtime canary, Git commit, annotated tag, and release receipt
   to the user's fork. Never rewrite v1.6.18 or its failed attempt.
3. Migrate the *one* original budget authority with an audited single-writer
   handoff. Verify the entire journal/receipt set, all outstanding holds, the
   `$200` cap, and absence of active processes. A copied snapshot alone is not
   permission to spend from a second ledger.
4. Materialize only the exact aggregate receipts needed by a fresh run, with
   source/destination hashes and no benchmark or sealed Dev/Final data. Use a
   fresh run ID. Continue only if all gates pass; a storage failure is never a
   score-targeted retry.

Apple documents Finder's “Keep Downloaded” for individual iCloud Drive files
or folders. It may help the archival side, but the tested fix for execution is
the independent local code/runtime. The Finder Repair prompt remains a separate
account-wide decision for the user.
