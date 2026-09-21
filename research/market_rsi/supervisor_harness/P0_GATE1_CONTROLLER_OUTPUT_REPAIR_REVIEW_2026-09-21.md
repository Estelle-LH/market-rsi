# P0 Gate 1 Controller output repair review — 2026-09-21

## Observed failure

The only authorized v0.1.13 live Controller call returned exactly 2,048 output
tokens with `finish_reason=length`.  Its preserved response contained analysis
but no final JSON decision, so the adapter produced neither `decision.json` nor
`task.json`.  The permanent run ID is closed and was not retried.

This evidence identifies an output-protocol failure.  It does not show that the
Controller selected a bad investigation, and it is not a prediction result.

## Alternatives considered

1. **Only increase the timeout.** Rejected as the causal repair. The provider
   returned before the timeout with a length stop; more wall time would not
   create the missing final decision.
2. **Only increase the free-text token limit.** Rejected. It leaves the same
   failure mode: analysis can consume the whole allowance before the answer.
3. **Infer a plan from the preserved analysis.** Rejected. That would make
   trusted code rewrite scientific content and would not be the model's exact
   submitted decision.
4. **Expose one terminal structured submission tool.** Selected. It reuses the
   already-tested terminal-submission pattern in `codex_glm_provider.py`, but
   keeps this Gate 1 path single-sample and plan-only.

No new external literature search was needed for this operational repair. The
reused evidence is the repository's existing terminal-submission implementation
and its tests. Applicability was checked against the exact pinned GLM chat
template and Gate 1 decision contract.

## Implemented contract

- The Controller sees exactly one non-operational tool:
  `submit_gate1_decision`.
- The tool schema contains every required decision field and the frozen enums
  and numeric ceilings from the Gate 1 packet.
- The reasoning setting is `low` for this small bounded choice. The generic
  Controller backend still defaults to `high` for other sessions.
- A response is valid only when it contains exactly one complete terminal tool
  call. Narrative-only output, multiple calls, an unfinished extra call,
  trailing narrative, missing/extra fields, forbidden authority and a length
  stop all fail without repair or resampling.
- The tool records a plan only. It has no network, file, shell, purchase, data
  admission, Dev or Final capability.
- The adapter remains one sample, fixed seed 23, no automatic retry.

The output allowance is 3,072 tokens and the sample deadline is 90 seconds.
The outer Supervisor deadline remains derived from the adapter deadline, so it
does not terminate a still-valid sample first.

## Cost check

The real pinned tokenizer rendered the new low-effort, one-tool request as
1,393 input tokens. At the frozen rates, 1,393 input tokens plus the full 3,072
output-token allowance has a `$0.04409478` upper bound. This is below the fixed
`$0.05` per-attempt cap. It is a preflight upper bound, not a provider invoice.

## Validation completed before publication

- 34 focused adapter/outer/provider tests passed.
- 44 Gate 1 tests passed in the pinned runtime.
- The adversarial checks cover narrative-only output, malformed data, extra
  URL authority, one valid plus one incomplete call, multiple complete calls,
  trailing narrative, the captured 2,048-token length-stop shape, permanent ID
  reuse, budget reconciliation and no-resample behavior.
- Fresh zero-provider adapter and outer canaries passed in `/private/tmp`.
  Provider calls: 0. Provider cost: `$0`. Public fetch: false. Formal data
  admission: false.
- The repository-wide suite ran 516 tests: 514 passed. The two failures are
  outside this change: one existing memory artifact no longer matches its
  frozen source hash, and one trainer test is blocked by the restricted test
  environment's denial of `ps`. All Gate 1 tests passed separately.

## Claim boundary and next gate

This repairs and validates the output contract offline. It does not prove that
GLM will submit a valid plan live, does not admit prediction data, and does not
authorize another paid sample. The next safe sequence is: exact diff review,
new immutable commit/tag on the user's fork, post-publication zero-provider
production-path canary, protected decision-state revision, then a separate
explicit decision about one fresh paid ID.
