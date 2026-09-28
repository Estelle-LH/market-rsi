# Gate 1 v0.1.25 schema-visibility repair — 2026-09-28

Status: local implementation, Supervisor tests and independent review pass. No release, push, canary, provider call, fetch, data admission or training is authorized by this document.

## Observed problem

Paid D0 run `market-rsi-v0124-gate1-controller-d0-20260928-01` returned one syntactically parsed tool call, then failed the local semantic validator:

`DecisionValidationError: bounded_investigation: canary proposal modes require max_documents_proposed == 0`

The model selected `bounded_response_canary_proposal` and supplied `max_documents_proposed=1`. The authoritative validator contained the mode-dependent rule, but the model-visible tool JSON Schema exposed only the independent mode enum and integer range `0..5`. The frozen packet and prompt did not state the cross-field table.

The response was terminal, used exactly one provider sample and cost `$0.02746872` by returned-token metering. It produced no valid decision, task, proposal or compiled plan and performed no fetch, sealed-data read, data admission or training. The old ID is permanently non-reusable.

## Causal layer and alternatives

The changed layer is only model-visible tool-schema guidance.

Considered alternatives:

1. Silently normalize `1` to `0`: rejected because trusted code would rewrite a Controller-owned scientific object.
2. Weaken the validator: rejected because the existing rule is the fail-closed authority boundary.
3. Add JSON Schema `if`/`then`: rejected as the primary repair because the pinned route does not provide constrained decoding and provider adherence to conditional schema keywords is not an enforcement boundary.
4. Add prompt prose only: weaker than locating the rule on the exact nested object the model must fill.
5. Add one exact `description` to `bounded_investigation`: selected as the smallest model-visible repair; the local validator remains the authority.

## Exact change

`p0_gate1_controller_adapter._submission_parameters()` now describes the complete mode table on the `bounded_investigation` object:

- `bounded_metadata_canary_proposal` and `bounded_response_canary_proposal`: `max_documents_proposed=0`;
- `first_party_document_review_only`: documents at least 1, provider requests 0 and raw bytes 0;
- `synthetic_contract_fixture_only`: documents, provider requests and raw bytes all 0.

The frozen packet, semantic validator, `_scope_submission`, parser/normalization, provider call, budget, fetch, admission and training code are unchanged.

## Supervisor verification

- Focused adapter plus decision-validator suite: 48/48 passed.
- Regression: canary mode plus `max_documents_proposed=1` still raises the exact `DecisionValidationError`; the submitted object remains unchanged.
- Positive fixture: changing only `max_documents_proposed` to `0` produces a valid scope-only decision.
- Complete mode-table tests cover both canary modes, document review and synthetic fixture acceptance/rejection.
- Pinned tokenizer: 4,020 input tokens, 1,600 maximum output tokens, description occurs once.
- Frozen-rate no-cache upper: `$0.0389772`, below the `$0.05` hard ceiling.
- Repository discovery: 516/516 tests passed; 2 documented environment skips.
- Independent review: PASS with no blocking code finding; tracked pre-bookkeeping patch SHA-256 `04318f4b49cbebe7848b76cd3223e1685ef33d161a5b0b62cd4fd53c726cbb59`.
- `git diff --check`: PASS.

## Remaining gates

Before calling this v0.1.25:

1. independent reviewer must give PASS on exact bytes;
2. local changes must be committed and release scope verified;
3. publishing/pushing an annotated v0.1.25 tag requires separate authorization;
4. the published exact source needs a fresh zero-provider production-CLI canary under a new ID and separate authorization;
5. any new paid D0 requires a fresh permanent ID and separate explicit authorization, including outbound packet disclosure;
6. any fetch remains separately unauthorized.
