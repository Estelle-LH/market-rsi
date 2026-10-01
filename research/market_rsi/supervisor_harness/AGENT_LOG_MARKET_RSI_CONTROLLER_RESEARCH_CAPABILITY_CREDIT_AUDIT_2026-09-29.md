# Market RSI Controller research capability and next-batch credit audit — 2026-09-29

Audit time: `2026-09-29T20:21:13Z`

Verdict: **PASS for adopting the bounded next-batch research-credit policy below; HOLD any claim that the current continuous-Discovery Controller can perform live literature search or original-source reading.** The current Controller/Supervisor loop demonstrably supports local evidence review and Supervisor-mediated small experiments on the already-opened Train material. The separate Data Scientist Harness contains live Crossref and bounded public-page readers, but no current continuous-batch workspace, current authorization snapshot, or live Controller-to-tool receipt admits those network functions. A fresh current-source, current-workspace, zero-paid canary is required before they can enter the active pool.

This was an independent, read-only capability audit plus offline tests. It did not access Dev or Final, perform a public fetch, call a provider, spend money, run a real experiment, change the incumbent, modify the continuous batch, or rewrite historical scores. The only repository write is this audit log.

## Scope and inspected evidence

The audit inspected the current canonical checkout `/Users/estelle/Developer/market-rsi`, its local configuration and the read-only continuous-Discovery state under `/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/continuous-discovery-batch-20260929-01`.

Key source/evidence hashes at review time:

| Evidence | SHA-256 |
| --- | --- |
| `research/market_rsi/AGENTS.md` | `5107e4b4362da42b42d3374fc083c9e706d543b824597cf1e2b068ceb296394e` |
| `data_scientist_harness/broker.py` | `c936e935f6aa2355f12013317a26ca1c47a63c547a14d1aab954c3f67809da38` |
| `data_scientist_harness/literature.py` | `cfe1211daea8eee51ede2b8cafe73faa8af66299e2e9b399f68027f00ac5e15f` |
| `data_scientist_harness/public_budget.py` | `14060a70f1f98be66e3f8bd0642bc9f1564c031ffcb55962289ad9caabffb56e` |
| `data_scientist_harness/store.py` | `79ba2ff3b94cb5c553a1d9c5e01485a111802164ec270c2c0adb626b899fb06d` |
| `data_scientist_harness/profiles.py` | `8c48eaad1e46ff98817f0ab9f8f59d17f8c2ecedcfe3fef3e4e0b3488ac1f4b5` |
| `data_scientist_harness/run_controller.py` | `e77876f74b8bddb8b8d153139db5498e9f673238a45e09562cd65599507a9d20` |
| `data_scientist_harness/archive_reader.py` | `1823e6b6f009682b30361e53344534508833360b57ab3930193081b17bbf8e16` |
| `supervisor_harness/controller_tool_adapter.py` | `2961c115d2506cc731031a99d4c1cc0358b98c9f53c0470717296ae474f31ffe` |
| `supervisor_harness/continuous_discovery_batch.py` | `6d29d59d531c0c8c4cee9d598144fdb4369bb59e38d3cbcade0403136f0add11` |
| `supervisor_harness/DISCOVERY_BATCH_2026-09-29.md` | `f46bffce5607f93751c99c13007e1940fa52e9adc756391f28cd9f02325dbd8a` |
| `supervisor_harness/CONTINUOUS_DISCOVERY_BATCH1_DETAILED_REPORT_2026-09-29.md` | `cdc5ccfc9e9c15c903984ae986bc57aa2c7816baf1feb8509013cda4f9ed4b8b` |
| `supervisor_harness/AGENT_LOG_DISCOVERY_ATTEMPT5_CONTROLLER_2026-09-29.md` | `29bd05297afca88a6949aa1e75241cf88da458be7018862317deb74618758436` |
| `literature_catalog.py` | `1c2eb180d04ed20608dbc37e698bb5bcebc2efa1b96a1ce44e2a32249827997a` |
| `DAILY_LOG_2026-09-17.md` | `67b5c7aa147ffc6e573636737be2186b2285d9d730f614878936af5750d592b5` |
| `CONTROLLER_RESEARCHER_SUPERVISOR_CONTRACT_2026-09-17.md` | `84ecf329dc7fd4f9b5c8b9b17232b8cf25a9c65ba969d1608c99cb86b2bc61f0` |
| current continuous batch `batch.json` | `95ee26f83cd9c727a1b19782a787aeae93e363727238ed58737e01fb988cb847` |

The current continuous state has five claimed attempts, five succeeded execution terminals and five independent reviews, then `batch_stopped`; four decisions are `REVERT` and attempt 3 is `KEEP`. Its exact boundary flags remain `resident_opened_train_only=true` and false for opening data, executing runners, scoring results, granting authority, protected Dev/Final, external acquisition, network, paid provider, publication, promotion. This proves an orchestrated evidence chain; it also proves that the state recorder itself is not a runner, scorer, data opener, network client or authority.

## Actual capability verdict

| Capability | Current Controller verdict | Exact boundary |
| --- | --- | --- |
| Analyze authorized data/evidence | **Available, bounded.** The completed batch demonstrates that Controller decisions can consume local, hash-bound prior artifacts and opened-Train discovery evidence. The Data Scientist Harness also implements raw-series, candidate-feature and feature-set diagnostics against exact admitted `allowed_train_dates`. | The continuous recorder does not open data. Raw profiling requires a separately admitted, input-present workspace and exact Train dates; aggregate-only workspaces cannot profile raw data or fit. Reused opened Train is discovery evidence, not out-of-sample evidence. |
| Run small experiments | **Available through the Supervisor chain, not as a direct Controller power.** Five batch candidates were implemented, executed and independently reviewed. The Harness has bounded `train_candidate` CPU children, a maximum of 8 trials, semantic-plan deduplication, a 60-second worker limit, no automatic retry and zero provider cost for local CPU fits. | A real run still requires source/runtime/release, quality, input, claim, watchdog and independent-review gates. The Controller does not own the runner or scorer. No Dev/Final or formal evaluation is allowed. |
| Live literature discovery | **Code-ready, historically canaried, but not currently admitted.** `search_literature_live` queries Crossref and returns bibliographic metadata. `controller_tool_adapter.py` restricts the bridge to a host-observed Controller sandbox and the three literature operations. | Crossref output is `metadata_only` and explicitly not a paper read. The present continuous batch has `network_allowed=false`; no current live Controller workspace or bridge receipt was found. Offline fake-transport tests are not a live capability receipt. |
| Read an original public source | **Code-ready, but not currently admitted to this Controller.** `read_public_source` can deliver a bounded range of public HTTPS HTML, XHTML, plain text or XML, with final-URL, content and byte receipts. | It rejects credentials, local/private addresses, PDFs, unsupported types and non-identity content encoding. It returns a delivered text range, not proof of understanding and not necessarily a full paper. Discovered links are not read automatically. Current batch network authority is false. |
| Read local frozen notes/history | **Available as local historical context when explicitly surfaced.** `read_archive` pages frozen prior-round JSON; legacy `search_public_literature` searches a frozen catalog. | `read_archive` says `history_not_current_qa=true`. `literature_catalog.py` labels its abstracts `Runner-authored synopsis`. Neither is a fresh search, publisher text, full paper or validation on current data. A synopsis must never be credited or cited as full text. |

Only four `data_scientist_workspace_v1` files were found under the local MarketRSI runs root. All are historical `local-runtime-canary-20260916-{01,02}` workspaces or their aggregate adapters. The two canary workspaces have `inputs_present=true`, `public_network_enabled=true`, `formal_evaluation_allowed=false`, `paid_execution_tools=false`, two synthetic allowed dates and no release; hashes are `fc61c90e465e0a77112248d939d1ead1a65c20517b6de5a5fbca3a63d02a0008` and `fe9d6dacf3096a7b1e6102773c4a711bf944c3661d83a2cb139b9f8a71dd770d`. The aggregate adapters have both inputs and network disabled; hashes are `8251a97a4d29f0264513883747ad715afedc584f98d4c86a18f7798d70799394` and `a891e2dcac01b89eaa68a607ee0101a47238777fa3eb579078c8dc0decdc6e15`. These are historical mechanics evidence, not authority for the next batch.

## Network, permission and failure boundaries

- The current continuous batch authorizes neither network nor paid providers. The audit made no exception and performed no fetch.
- A Broker workspace with `public_network_enabled=false` rejects live search/read before transport. Invalid URLs are rejected before a byte reservation or dispatch.
- Crossref search is metadata discovery. DOI, title, publisher URL and links do not establish that a source was opened or read. `record_research` rejects metadata-only record IDs.
- The public reader permits HTTPS port 443 only, revalidates DNS and every redirect against private/local addresses, strips ambient credentials/proxies by using a minimal child environment, has no retry, and applies 25-second child/30-second parent bounds.
- One public response is capped at 2,000,000 bytes plus a one-byte oversize probe; extracted text is capped at 100,000 characters and each returned range at 12,000 characters. PDFs are not admitted. Paywalls, unsupported content, compression, HTTP errors, unsafe redirect/DNS, timeout, excessive size and malformed receipts terminate the attempt.
- `PublicBudget` has a 10,000,000-byte workspace body cap in the inspected configs. It reserves 2,000,001 bytes before each fetch. Timeout, kill, HTTP failure or invalid receipt leaves the full reservation charged; there is no implicit expansion or silent replay.
- Local raw analysis rejects missing inputs, aggregate-only workspaces and dates outside exact opened Train. Small experiments reject failed quality, unpublished source where publication is required, absent inputs, a stale/missing research chain, a semantically duplicate plan, exhausted trial count, wrong runtime/date/seed, timeout or mutated receipts. Failed scientific plans are preserved and not silently restarted.
- The Controller literature adapter and mailbox are offline-tested identity/binding components. The architecture record explicitly says they have not proven a current GLM/E2B guest tool call or actual public fetch. That unclosed integration boundary is why live research remains HOLD.
- Formal evaluation, sealed Dev/Final, acquisition, publication, promotion and protected scoring remain out of scope regardless of research credit.

## Minimal preflight for each next-batch research question

The unit of credit is one predeclared **research question**, not a paper, tool call, token count, trial, or favorable score. Before scheduling, require one canonical record with:

1. `question_id` and a semantic `question_digest` over the normalized question, causal/availability boundary, changed layer, parent route/candidate, evidence scope, comparison, and `support_if`, `refute_if`, `stop_if` rules.
2. A duplicate search over prior questions, controller decisions, source records, experiment specs and stopped routes. Repeating the same question/evidence earns no new credit. A follow-up must bind the earlier question and state one exact new discriminatory delta.
3. An authority snapshot that binds source/runtime, opened-Train or aggregate-only scope, network flag, public-byte budget, provider budget, Dev/Final=false, formal-evaluation=false, and the exact allowed tools. A capability existing in source code is not sufficient.
4. A mode-specific capability check:
   - local analysis: current workspace has exact admitted inputs/dates or exact aggregate receipts;
   - small experiment: quality/release/input gates pass, the plan is new, CPU/time/trial bounds are fixed, no retry, and runner/scorer remain independent;
   - Crossref: receipt is labeled metadata-only and the question is limited to bibliographic discovery;
   - public-source reading: final URL, media type, byte/content hash, offset/end/total, redirect trace and budget attempt are present; PDF/paywall/failure is recorded as not read;
   - frozen synopsis/archive: artifact path/hash and `frozen_synopsis` or `historical_archive` mode are explicit, with `full_text_read=false` and `fresh_network_read=false`.
5. One evidence bundle binding the question record, Controller decision, every source/search/read receipt, code/spec/runtime, local analysis or experiment artifact, result, boundary counters and terminal cleanup. Prose without exact artifact hashes is insufficient.
6. Independent Supervisor verification of hashes, mode labels, dedupe, permissions, causal boundary, predeclared decision rule and result. The author of a candidate cannot issue the final credit.
7. One terminal `credit_decision` with `credit`, reason, independent-review hash, route action and non-authoritative active-pool/budget hints. It is append-only and cannot revise Brier, KEEP/REVERT, incumbent history or a prior independent review.

## Research credit 0/1/2

| Credit | Admission rule | Scheduling consequence |
| --- | --- | --- |
| **0** | No valid new research answer: duplicate question/evidence; boundary violation; unsupported prose; metadata or frozen synopsis misrepresented as original text; tool/infrastructure failure without a research conclusion; unbound artifact; post-hoc hypothesis/threshold; missing independent verification. | Remove from the active pool or place the exact route on cooldown. It receives no experiment/provider/public-byte hint. Engineering repair, if needed, is tracked outside research credit. |
| **1** | Valid, novel and independently verified evidence that narrows the question but is not decision-resolving. Examples: a metadata-scoped source map; a bounded original-text passage with applicability/limitations; a causal Train-only diagnostic; or a clean but genuinely inconclusive small experiment. | Permit at most one bounded follow-up whose new discriminatory delta is predeclared. It may receive one ordinary active-pool slot/budget hint, never evaluation authority. |
| **2** | A complete independently verified cycle resolves the predeclared question under its support/refute rule and changes the route decision. Exact evidence and boundaries are fully bound. A decisive valid refutation qualifies equally with support. | Positive support may keep the route active for its next distinct question. A valid refutation immediately executes the predeclared stop/branch action and frees the slot; it must not be penalized for being negative. |

Credit is capped at 2 per question and is not cumulative model reward. Multiple papers, reads or trials supporting the same resolved question do not mint more credit. A later materially different question begins at zero with a new digest. A result that merely improves opened-Train Brier does not automatically earn credit 2; it must resolve the stated research question and survive independent review.

### Valid refutation and route stopping

A refutation is credit 2 when all of the following hold: the refuting threshold and stop action were recorded before execution; the evidence uses the exact admitted scope and control/comparison; the artifact and result were independently reproduced or recomputed; and no boundary/receipt failure explains the result. The Supervisor then records `route_action=stop` (or the predeclared alternate branch), a cooldown reason and the refutation bundle hash. Repeating the stopped route without a new causal mechanism or newly available evidence is a duplicate and earns 0. An infrastructure failure is not a refutation.

## Active-pool and budget-hint rule

- Keep approximately **70%** of next-batch slots for evidence-backed active questions and a baseline **30% exploration reserve** for orthogonal mechanisms, falsification, neglected evidence modes and diversity.
- The Supervisor may set the exploration reserve between **20% and 40%** only before a batch, with an append-only reason tied to queue health, route concentration and recent valid refutations. It cannot expand the total attempt, time, network-byte or monetary ceiling; unused reserve returns unused.
- Credit is only a priority hint. Credit 2 support ranks one distinct follow-up above unresolved credit-1 work; credit 2 refutation stops that route rather than promoting it; credit 1 gets at most one bounded follow-up; credit 0 is removed/cooldown. Apply diversity caps so one route cannot consume the active pool by accumulating related questions.
- A budget hint names a bounded resource class (local analysis, one small experiment, metadata lookup, one bounded page read) and its maximum attempts/time/bytes. It is not spend authority. Actual network, provider or experimental execution still requires its ordinary fresh authorization and global-state claim.
- Research credit must never enter Brier arithmetic, fold aggregation, KEEP/REVERT thresholds, incumbent selection, formal validation, Dev/Final admission or independent-review logic. Those remain exclusively determined by the frozen scorer and review contracts.

## Architecture decision

Do **not** build a reward service, RL loop, policy-gradient learner, learned credit model, new scorer, or broad Harness rewrite for this policy. For the next batch, an append-only Supervisor-reviewed credit record and deterministic scheduler hint are sufficient. Credit is research-process accounting, not a model reward and not evidence of predictive quality. Any later code implementation must be a separately reviewed, versioned scheduling component outside the evaluation kernel.

## Verification performed

Command, run from `research/market_rsi`'s parent checkout with the pinned runtime and only fake transports/synthetic fixtures:

```text
PYTHONPATH=research/market_rsi /Users/estelle/.cache/market-rsi/runtimes/ds-py312-20260912-01/bin/python -m unittest -v \
  data_scientist_harness.test_harness \
  data_scientist_harness.test_public_budget \
  data_scientist_harness.test_source_study \
  data_scientist_harness.test_tool_schema \
  data_scientist_harness.test_sanity_and_trace \
  supervisor_harness.test_controller_tool_adapter \
  supervisor_harness.test_controller_mailbox \
  supervisor_harness.test_offline_connection_cycle
```

Result: **83/83 PASS** in 40.685 seconds. A non-failing joblib warning reported that physical-core discovery fell back to the logical core count. No test contacted a public source or provider, and no real Train experiment was run.

Final conclusion: **PASS the credit and scheduling rules above for the next batch; keep live Crossref/public-text actions unavailable to the current continuous Controller until a fresh, exact, current-source capability canary and explicit network/byte authorization pass.** Local frozen summaries remain useful discovery leads only and must never be promoted to full-text evidence.
