EDGAR25 saved-result replay (Python 3.12 standard library only)

This is NOT an experiment runner. No production module, model client, scorer,
Native/Docker worker, subprocess or writable ledger is used by replay.py.
The command installs a runtime audit hook refusing network, child processes,
writes and reads outside the supplied bundle, replay code and Python stdlib.

GET THE TWO SEPARATE DELIVERABLES
1. The specified replay-code Git commit (or its offline Git bundle/archive).
2. The versioned PRIVATE authorized training evidence archive and the release
   record containing its SHA256 and manifest SHA256. Verify both hashes against
   that separately trusted release record BEFORE extracting the archive.
Do not trust a replacement hash supplied only by the evidence archive itself.

No evidence data is uploaded to GitHub by this tooling. The package contains
original training request/response material and historical paths: share only
through an owner-approved access-controlled channel. Local directory mode0700,
archive mode0600. No passwords, tokens, credentials or heldout bodies belong in
the package. The exporter fails rather than redact credential-shaped bytes.

OFFLINE COMMAND (run from any fresh directory; no old workspace needed)
  python3 -I -B /checkout/repro/edgar25/replay.py \
    --bundle /fresh/extracted/evidence \
    --manifest-sha256 THE_HASH_FROM_THE_GIT_RELEASE_RECORD

The command prints JSON. Exit0 means the evidence and reported saved-result
replay matched, NOT that a pending round completed or a candidate was adopted.
Exit2 means missing/corrupt/unverifiable evidence. Inspect state, coverage,
company_equal_mean, selection and unverifiable for each logical trajectory.

Historical absolute paths are preserved inside original bytes. Resolution is
exclusively through SHA256 content-addressed package files and independent
original-path mappings. No original /Users/... path is opened. Source identity
is verified using original Git commit/tree/blob bytes and their Git object
hashes, without requiring Git or the original checkout during replay.

ROUND BOUNDARIES
- Round0 is the ordinary25-company baseline,125 targets and mean3.0/5. Its597
  generations include the two retained failed partial attempts; costs are not
  dropped. Per-target awards and saved predictions are replayed, not rescored.
- Clean slate is an attempted logical round1, not physical run50 or inherited
  R09/old control. This package includes the normally exited but REJECTED
  proposal:24 settled C/A/Review generations,0/25 candidate scores, no frozen
  candidate and no selection. Actual C/A HTTP inputs are joined to complete125
  feedback. Review rejection is not a forecast score or a completed round.
  Later changes require a NEW immutable package; never overwrite old evidence.
- Legacy experiments, including old47's UNKNOWN exit, remain archive-only and
  explicitly not included as new25-company panel results. Full legacy replay
  is a remaining gap, not silently claimed complete.

FEES AND FALLBACKS
The exporter reads selected columns of an existing historical ledger prefix
with SQLite mode=ro and BEGIN. It never copies a live DB or writes SQL. Replay
recomputes every packaged generation's conservative nano-dollar charge from
saved model usage/rates, checks UUID/reservation/settled ledger row, then joins
window and round totals. This is not provider invoice verification. Normal
historical upper bounds outside Round0 remain in the prefix, not refunded.
Early finalization receipts are reported individually; they are not forecast
reruns or invented score fallbacks. Missing raw protected score/answer bodies
are intentionally declared restricted; public award replay remains possible.

EXPORT AT A SAFE SNAPSHOT BOUNDARY (authorized operator only)
  python3 -B repro/edgar25/build_bundle.py \
    --repo /original/source-checkout --artifacts /original/owned-artifacts \
    --output /private/versioned-evidence-directory \
    --code-commit THE_REPLAY_CODE_COMMIT
The destination must not exist. This explicit exporter uses local read-only
Git operations and a read-only ledger, not experiment imports or API calls.
It is outside the frozen experiment source set. Do not change production HEAD,
frozen files or active inputs merely to add replay tooling. Publish only the
isolated replay-code/release branch after explicit publication authority; do
not push private research checkpoint ancestry.

LIMITS
Saved-result replay is not a second model run, a protected-scorer reexecution,
an independent ground-truth audit, a measurement-truth certificate or a promise
that a future API call will return identical text/scores. Missing original
execution/exit evidence stays missing. Current snapshot status is not a lease
on a still-running owner. Never use replay to create spending authority.
