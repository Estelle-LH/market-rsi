# In-game Discovery v3 batch — final independent state review — 2026-09-29

## Verdict

**PASS.** Zero P0 and zero P1 findings. The append-only journal independently
replays to the published final snapshot with exact head
`8b2339a8dcaad1d1fffd86d1dd2a228a8fe370a7ec31048719e8cb584c17845e`
and state SHA-256
`3204552e723db4d45d680d61b21d16d8dca656d0aa48fc4178de06f2bd8ed7c3`.
The batch is terminal because all four permitted attempts were claimed, not
because of a scientific success claim or an expanded authority boundary.

This review was read-only. It did not append a journal record, rewrite
`batch.json`, claim an attempt, execute or score a runner, change research
credit, or mutate an incumbent.

## Reviewed state

Batch root:
`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/continuous-discovery-batch-20260929-02`.

- snapshot file SHA-256:
  `da36054d8e294faa52f7ce276c60370e95226747e5a8d90e55dbfa9480ae75a7`;
- journal records: `27`;
- terminal journal head:
  `8b2339a8dcaad1d1fffd86d1dd2a228a8fe370a7ec31048719e8cb584c17845e`;
- replayed state SHA-256:
  `3204552e723db4d45d680d61b21d16d8dca656d0aa48fc4178de06f2bd8ed7c3`;
- ordered event-hash ledger digest:
  `9a7ae26e158139f1e8952d760f18d82a9e25b228cd38b012f9e34660e4174e93`.

All 27 files are canonical sorted compact JSON with their required trailing
newline. Sequence numbers are contiguous `1..27`; every `previous_sha256`
matches the prior record; every independently recomputed `event_sha256`
matches. There are no pending journal temporaries, symlinks, hard-linked
journal entries, or group/world-writable state files.

The event inventory is exact:

| Event | Count |
| --- | ---: |
| `initialize_v2` | 1 |
| `controller_pool_selected` | 2 |
| `implementation_ready` | 4 |
| `execution_claimed` | 4 |
| `execution_terminal` | 4 |
| `result_reviewed` | 4 |
| `research_credit_recorded` | 4 |
| `controller_feedback_ready` | 4 |

Replaying those records through the scheduler transition function produces
byte-for-byte the same logical state as `batch.json`. Independently hashing
the canonical state after removing its `state_sha256` field reproduces the
published state hash above.

## Terminal budget and branch state

The final state has `attempts_claimed=4`, `max_attempts=4`, no active attempt,
and `stopped_reason=max_attempts_reached`. The stop reason is deterministically
derived by replay when the fourth claim exhausts the cap; a redundant explicit
`batch_stopped` record is neither present nor required.

Allocation accounting is balanced and exact: two exploration attempts and two
exploitation attempts. Three executions succeeded and one failed, matching
`failed_attempts=1`. Every branch is independently reviewed and ends at
`controller_feedback_ready`:

| Attempt | Allocation | Execution | Credit / outcome / route | Feedback SHA |
| --- | --- | --- | --- | --- |
| `attempt-01` | exploration | succeeded | `1 / inconclusive / bounded_followup` | `eab1cdbb1d42267ce6693a9f2d779e4855c22491582a2df3f1bfe372bc149ffe` |
| `attempt-02` | exploitation | failed | `0 / invalid / cooldown` | `384ba846a3da122f075904dcccb56c4d964986c900175562f3bdcbd17384d120` |
| `attempt-03` | exploitation | succeeded | `1 / inconclusive / bounded_followup` | `ddd177366bca0eb5aef59add451a2be9fda26fe36c5cb8d17bb3cfed613ab7ff` |
| `attempt-04` | exploration | succeeded | `1 / inconclusive / bounded_followup` | `165af1136ca7ecb19d39acac232edfc17b125319757ede7721b9af45cea0795e` |

The branch credit vector is therefore exactly `[1, 0, 1, 1]`. The four credit
records have four distinct canonical question digests and four distinct
evidence-bundle hashes. Positive credit appears only on succeeded,
independently reviewed executions. The one failed execution is correctly
classified as invalid, receives zero credit, and is cooled down rather than
used as scientific performance evidence.

## Research parent versus comparison incumbent

The comparison incumbent remains the batch-start raw market at SHA-256
`89a8ef92c9cf4844b99e0136c51a1f8b896cdd66afcd23e8b8a23499859ffc7f`.
`incumbent_history` contains exactly that single entry and
`updated_by_attempt_id` remains null. Every feedback packet records the same
incumbent before and after its attempt.

Research lineage is separately preserved:

- attempts 01, 02 and 04 parent the archived v0 negative state branch
  `c40b1df57588b296e72ffe5b220c91aa0dd16d31ef1c573bdb4b0e7c0d72f79d`;
- attempt 03 parents the valid credit-1 attempt-01 runner
  `a612371ae77a78441c2d9416d6edc035a916879057fed9ef731de46476a07bcb`.

Both research-parent identities differ from the raw-market comparison
incumbent. The attempt-01 bounded-followup allowance is consumed only by
attempt 03; the parent is not promoted or substituted for the comparison
incumbent.

## Boundary replay

Initialization and final state contain the same exact boundary map:

- resident opened Train only: true;
- scheduler executes runners or scores results: false;
- opens data or grants authority: false;
- network, external acquisition and paid provider: false;
- protected Dev/Final, publication and promotion: false.

Every branch resource hint and every final feedback packet also records
`authority_granted=false`. Replay accepted no event that expanded these flags.

## Final interpretation

The state is operationally complete and internally consistent, so no scheduler
repair or REPLAN is warranted. `PASS` here means only that orchestration,
provenance, credit accounting and authority boundaries replay correctly. The
scientific record remains three valid inconclusive audits plus one invalid
failed attempt; the batch has not changed the raw-market incumbent and does not
support promotion, publication, protected evaluation, paid access or a claim
that the research hypothesis succeeded.
