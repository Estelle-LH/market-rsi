# Held-out Final recovery plan — no outcome exposure

## Scope and present boundary

- 2026-09-22 15:31 ET — Independent auditor prepared this recovery plan from existing local metadata only. It does not open prices, labels, trades, scores, game results or outcomes; fetch data; call a provider; purchase anything; change the reserved dates; or admit a Final.
- Existing candidate: `artifacts/p0-data-admission-gate0-20260918-01/prospective-2026-final-candidate.json`, SHA-256 `70be5d64c6e35a680107fed6569e8cfb62e2be917b29f17aec584518f35372cc`.
- Current result from `AGENT_LOG_FINAL_NONEXPOSURE_2026-09-22.md`: reservation was made before the window, but complete later access history, label non-exposure, market-data rights and same-mechanism 2026 coverage are not independently verified. The candidate remains unadmitted.
- Decision rule: the existing candidate becomes eligible for Supervisor admission review only if **every** gate below passes. `unknown` is not a pass. A definitive exposure, membership mutation or irrecoverable audit gap rejects this candidate for a formal Final while preserving it as historical evidence; it does not authorize choosing a more favorable replacement.

## Gate 1 — Freeze and authenticate the existing commitment

**Purpose:** prove what was selected and when, without inspecting outcomes.

1. Independently verify the candidate SHA-256 above, its schedule-source SHA-256, schema, selection rule, 20 distinct dates, 104 unique game IDs, and `formal_final_admitted=false`.
2. Link the candidate to a timestamped pre-window receipt. Current supporting record is `AGENT_LOG_P0_FINAL_METADATA_2026-09-18.md`, SHA-256 `ab6f581c218fcc80ca85a03f36c9989af9221d83a45d95e7daeb24821d7562f0`.
3. Inventory only candidate filename, size, hash, creation/commit receipt and filesystem/Git metadata. Do not open any market or outcome object.

**Pass evidence:** two independent recomputations match the candidate and schedule hashes; the precommit receipt predates the first reserved date; exact membership is unchanged.

**Fail evidence:** hash or membership mismatch, missing precommit timing, duplicate IDs, or any attempt to edit the candidate. A failure permanently prevents formal use of this exact candidate.

## Gate 2 — Recover complete access history and certify label non-exposure

**Purpose:** determine whether the already-started reserved window stayed unseen after reservation. `labels_read=false` inside the candidate is a claim, not proof.

1. Define the protected namespace without reading contents: the 104 game IDs, reserved dates, all known aliases, provider market IDs if available from metadata, evaluator paths, cache/object-store prefixes and any derived-label artifact names.
2. Enumerate every place and actor that could access those objects from the reservation receipt through the audit cutoff: canonical Mac checkout, iCloud/archive copy, local Docker volumes, temporary directories, provider/download caches, dashboards, automation tasks, Controller/Researcher tasks, evaluator accounts and human/manual access.
3. Recover append-only read/audit records for the **entire interval**, including rotation boundaries and clock provenance. Hash each log before review. Record start/end time, host/account/tool identity, sequence continuity, previous-head/next-head linkage, retention policy and any gap. Search only metadata fields such as path/object ID, operation, actor and timestamp. Do not render or copy protected payloads.
4. Reconcile the access log with artifact inventories and process/task journals. A protected object may be hashed by an isolated auditor, but its bytes must not be emitted. The auditor returns only object ID, size, hash, access classification and signed receipt.
5. Require a one-use evaluator boundary: protected raw objects/labels remain outside the Supervisor, Controller and Researcher; only opaque commitments exist before the final evaluation. Record key custody and deny/read-policy receipts.

**Minimum pass evidence:**

- the access record starts no later than the reservation timestamp and has no unexplained interval through the admission review;
- it covers every storage surface, credential and actor capable of reading the protected namespace;
- all log rotations/exports form a tamper-evident continuous chain;
- no read or derived-label operation exists outside the named sealed evaluator; and
- an independent auditor signs a per-candidate `verified_not_opened` receipt bound to the candidate hash and access-log head.

**Fail evidence:** any unauthorized read, derived label, displayed result, candidate-specific outcome query, or mutated access log. **Unknown/reject-for-formal evidence:** missing host/account coverage, logs beginning after 2026-09-18, retention gaps, untracked manual access, unverifiable caches or absence of a trustworthy log. Absence of an event in an incomplete log is never proof of non-exposure.

## Gate 3 — Verify source and research-use rights without market values

**Purpose:** establish permission for the exact 2026 market source and intended research outputs, separately from nflverse schedule permission.

1. Identify the exact market-data provider/source, endpoint or archive revision, account tier and mechanism from catalog/contract metadata only.
2. Preserve a dated terms/licence/contract snapshot and hash. Record permitted acquisition, local storage, research/model training, derived features/labels, publication of aggregate results, retention, attribution, redistribution restrictions, geography and account/team constraints.
3. Bind the rights receipt to the exact source revision and proposed use. A public endpoint, publisher marketing page, or historical `CC-BY-4.0` claim for a different archive is not sufficient.
4. Obtain explicit owner/legal or other authorized human determination where terms are ambiguous. Store the decision and supporting document hashes, not credentials.

**Pass evidence:** an authorized, dated rights decision explicitly permits the exact source and all intended research uses, with document/version hashes and required controls.

**Fail evidence:** terms prohibit an intended use, permission is denied, or account access would violate provider rules. **Unknown:** no exact licence/contract, ambiguous scope, or only a third-party/unverified publisher claim. Unknown keeps the candidate unadmitted.

## Gate 4 — Verify same-mechanism market coverage without exposing values

**Purpose:** prove that the frozen 104-game denominator corresponds to the same market mechanism as the research cohort. Market existence is not the same as usable label support.

1. Freeze the mechanism definition before checking coverage: provider, venue, AMM versus CLOB, moneyline contract type, home/away orientation, timestamp semantics and source revision. It must match the mechanism used by the benchmark cohort; do not silently combine venues.
2. Use provider catalog headers, signed listings, object manifests or an isolated metadata broker to map **all 104 games** to market IDs. Allowed output fields are candidate game ID, opaque market ID/commitment, mechanism/type, creation/close timestamps, object existence, source revision and missing reason. Exclude prices, sizes, sides, settlement, winner/outcome and trade rows.
3. If confirming that protected source objects exist requires opening them, a sealed independent verifier may read them and emit only per-object hash/byte count/schema commitment and a boolean mechanism/field-presence result. Supervisor, Controller and Researcher receive no rows or values. Code and output schema must be frozen first and independently reviewed.
4. Reconcile the denominator exactly: `mapped + missing = 104`, all 20 dates retained, every duplicate/ambiguous mapping named. Missing games remain missing; they are not dropped or replaced.
5. Keep two conclusions separate: (a) **catalog/mechanism coverage**, which this gate can prove without values; and (b) **eligible 60-second labels**, which must stay sealed until the one-use evaluator runs. Catalog coverage alone cannot claim executable trades or statistical power.

**Pass evidence:** a signed, hash-bound 104-row metadata/commitment manifest with exact denominator reconciliation, one frozen mechanism, source revision, no protected fields, and independent schema review. The sealed evaluator separately commits that the frozen target can be computed, without revealing counts or scores before final use.

**Fail evidence:** mixed mechanisms, post-outcome mapping choices, missing dates removed from the denominator, or protected values leaked. **Unknown:** catalog/manifests cannot establish exact mappings or source-object availability. Unknown keeps the candidate unadmitted.

## Gate 5 — Independent admission or rejection of the existing candidate

The independent reviewer receives only the Gate 1–4 receipts and hashes, not protected values.

| Requirement | Pass | Fail / unresolved action |
| --- | --- | --- |
| Exact precommitted membership | Gate 1 pass | Reject exact candidate if mutation/timing fails. |
| Complete non-exposure history | Gate 2 pass | Exposure = reject; incomplete history = formally unusable/unknown. |
| Exact-source research rights | Gate 3 pass | Denied = reject; ambiguity = keep blocked. |
| Same-mechanism 104-game coverage | Gate 4 pass | Wrong mechanism/leak = reject; incomplete metadata = keep blocked. |
| Outcome boundary | No protected values reached Supervisor/Controller/Researcher | Any leak rejects formal independence. |

**Admission evidence:** one immutable decision receipt containing candidate hash, all four gate-receipt hashes, reviewer identity/runtime, decision timestamp and `formal_final_admitted=true`; candidate file itself remains unchanged. Admission still does not authorize opening the Final—the one-use evaluator opens it only after the final model and analysis are frozen.

**Rejection evidence:** one receipt naming the exact failed/unknown gate and preserving the candidate hash. Do not rewrite history to `labels_read=true` without evidence of an actual read; distinguish `exposed`, `not provable`, and `rights/coverage failure`.

## Gate 6 — Deterministic future-window fallback, only if recovery fails

This is a **conditional protocol proposal**, not an executed selection and not permission to change the current candidate. It requires a separate Supervisor/human scope decision, a new version, fresh ID and fresh artifact. The existing candidate remains immutable.

### Trigger

Use the fallback only after Gate 5 records the existing candidate as formally unusable because access history cannot be certified, exposure occurred, rights fail, or same-mechanism coverage cannot be established. Do not trigger it based on prediction scores, market movement, team identity or observed outcomes.

### Predeclared deterministic rule

1. At a signed commitment time `T0`, freeze a **schedule-only** source/version/hash and a mechanism/source definition already permitted by Gate 3. Install and canary the append-only access monitor **before** selection.
2. Define `eligible_date` as a regular-season scheduled game date strictly later than `T0 + 7 full calendar days`. The seven-day lead is operational time to prove logging and custody before the first event; changing it requires a new protocol before selection.
3. In the earliest schedule season that contains at least 20 such distinct dates, select the lexicographically earliest 20 distinct eligible dates and **all** scheduled games on those dates. Sort by `(game_date, game_id)`. Use no market availability, team, price, result or label information in membership selection.
4. If the frozen schedule has fewer than 20 eligible dates, produce `insufficient_future_dates` and wait for the next independently published pinned schedule; do not shorten the floor or combine a favorable historical block.
5. Immediately write a new immutable schedule-only candidate containing the rule, `T0`, source hash, dates/game IDs, count, access-log genesis hash and all admission flags false. Two independent implementations must reproduce the same membership/hash before reservation is accepted.
6. Start continuous access accounting at genesis and keep every game in the denominator. Later missing markets or labels remain explicit failures/missingness; they do not cause reselection. Gates 2–5 then run on this new candidate.

**Fallback pass evidence:** protocol/version was frozen before `T0`; monitor canary and genesis receipt precede selection and all selected dates; independent selectors agree; membership uses schedule fields only; candidate has at least 20 dates and all admission flags false.

**Fallback fail evidence:** monitor starts late, rule changes after dates resolve, membership uses market/label/outcome availability, fewer than 20 dates, selector disagreement, or any protected value is opened. Failure produces no replacement candidate.

**Implementation warning:** `reserve_prospective_final_candidate.py` accepts an `after_date` argument but writes a hard-coded `2026-09-18` selection-rule string. It must not be reused for a fallback without a separately reviewed/versioned correction and tests proving the serialized rule matches the actual parameter. No correction was made in this assignment.

## Minimum next actions for the Supervisor

1. Independently recheck the hashes and the four unknown findings in `AGENT_LOG_FINAL_NONEXPOSURE_2026-09-22.md`.
2. Ask whether a complete, tamper-evident access record existed from 2026-09-18 across **all** storage/actors. If not, Gate 2 cannot pass retrospectively; record “not provable,” not “not exposed.”
3. In parallel, request metadata-only exact-source rights and 104-game same-mechanism coverage receipts. These can clarify why the candidate is unusable but cannot repair a failed access-history gate.
4. Run Gate 5 once. If any gate remains unknown, keep the candidate unadmitted and seek the separate scope decision for Gate 6. Do not instantiate fallback dates in this recovery review.

No empirical result or Final admission is claimed here.
