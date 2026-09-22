# Gate 1 v0.1.21 launch-readiness audit — 2026-09-22

**2026-09-22 15:37 EDT — REPLAN (mechanically ready, not launch-authorized).** The released, no-catalog one-response path is coherent and the intended next identity is currently unused, but `RESEARCH_STATE.md:14` and `SUPERVISOR_ROADMAP_2026-09-21.md:17` explicitly leave the paid request waiting on fresh authorization. This read-only audit is not that authorization. The exact launch command therefore cannot yet bind truthful post-authorization `expected_head_sha256` and `expected_decision_sha256` values. Record the authorization in the compact decision document and append the corresponding idle `decision_revision`, then recapture both hashes and rerun every freshness check immediately before the one allowed invocation. Do **not** launch using the current hashes merely because they are listed below.

## Frozen release, packet, runtime, and canary bindings

- Canonical checkout: `/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local`; branch `codex/market-rsi-round1-v2`; HEAD and annotated tag `market-rsi-protocol-v0.1.21^{commit}` both resolve to `f06214b3bb521096078d897fe60ec9ba589c00c6`. Local annotated tag object: `a94401bb2efc3e379500039f46b594c4f65f24da`. The controlled 324-file manifest recomputes to `872f05ae48fa49deeb811bc6ca4705652168f198b5f1f9d69d3ce172ad0986da`, and scoped Git status for all 324 controlled paths is empty. Production rechecks the annotated tag against the authorized origin and the exact controlled bytes before credential access (`protocol_source_release.py:127-175`, `p0_gate1_controller_live_entry.py:66-85`).
- Exact packet: `artifacts/p0-data-admission-gate1-packet-20260922-03/controller-input.json`; schema `market_p0_gate1_controller_packet_v4`; file SHA-256 `c819e55db781b6620cd2c4923afc442027312e082264127e4c1cadf100b6f614`; canonical SHA-256 `ae89eb930c1b4bc775ad3f02646b1f1b341ce082f530fc58119b915d24b76c18`. It advertises eight trusted documentation choices, reports `reviewed_real_train_catalog_available=false`, and authorizes no fetch or formal admission. Omit all three catalog arguments. Parent and child independently check the file and canonical hashes (`p0_gate1_controller_supervisor_parent.py:68-86`, `p0_gate1_controller_live_entry.py:69-76`).
- Pinned runtime receipt: `artifacts/market-rsi-gate1-controller-20260922-02/runtime.json`, SHA-256 `d5b52b7509e17b2e1dca24cb5c81707d6775b0cd7e7ede48208a338b47d0b0e9`. A fresh read-only `runtime_receipt()` was byte/content-equal: resolved Python `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12`, Python 3.12.3, image `python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`, runner `9c2b86386b8c4ebd5c31808307c3998a3b800889365d1f0286701914fd17f785`, common adapter `f58c8cfb84950f2498dacf4865ab2839e9fda4e78ba227eca66c87b17ac88d7e`, guest `35b0566a7cc65de4397c4d97fdc4a05d503ce37de98a9d072693985008f1fc1f`, and exact Jinja2 3.1.6 / MarkupSafe 3.0.3 / tinker 0.25.0 / transformers 5.5.4 dependencies. The old receipt supplies immutable runtime facts, not permission or reuse of an old response; production requires exact equality to current runtime (`bounded_live_outer_runner_v3.py:80-98,134-138`).
- Postrelease zero-provider production-CLI canary: `/private/tmp/market-rsi-gate1-v021-postrelease-canary-20260922-01/canary-result.json`, file SHA-256 `8e5f86aa20101979385c5fb57de3fa1fb978cf04036b5a483a15a07e13984ed9`. Readback: `passed=true`, `provider_calls=0`, actual provider cost `0`, production parent/arguments used, no fetch or admission, and exact packet hashes above. Bind this exact SHA as `--prior-canary-sha256`; it is evidence of the released CLI boundary, not evidence that the next model response will comply.
- Credential and tokenizer inputs exist as regular non-symlinks: `/Users/estelle/Library/Application Support/MarketRSI/tinker-gate1-20260921.env` (contents not inspected) and `/Users/estelle/Library/Application Support/MarketRSI/tokenizer-cache-glm53-20260921-01`. The live entry does not read the key until publication, runtime, packet, state, budget, catalog, duplicate-process, and Supervisor-claim gates pass (`p0_gate1_controller_live_entry.py:53-89`).

## Fresh run identity and current dry checks

The intended next ID is exactly `market-rsi-gate1-controller-20260922-03`. The executable identifier rule is `[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}` (`market_rsi.py:46-49`); the date/ordinal naming convention is operational rather than regex-enforced. More importantly, the ID is permanent: any attempted outer transaction may consume it, and neither a format failure nor a pre-dispatch failure permits reuse (`p0_gate1_controller_outer.py:204-224`). A launch-time candidate must be absent simultaneously from:

1. global state `claimed_cycles`, with `active_cycle=null`;
2. authoritative budget `jobs`;
3. `artifacts/p0-gate1-controller-claims-v1/<ID>.json`;
4. `artifacts/<ID>` and `artifacts/<ID>-supervisor` (including symlinks); and
5. the process inventory and exact Docker name `market-rsi-b-<ID>` (`bounded_live_entry_v1.py:48-75`).

At 15:32 EDT, a read-only check for `market-rsi-gate1-controller-20260922-03` passed all five: no claim/job/output roots, no matching PID/container, and `active_cycle=null`. The then-current state head was `3b008cb00ce2674ef7b3a0b32b44fe1b7ea8e1079d57463c701ef37b1c66e30e`; decision-document SHA-256 was `43a99ef50c0d7126d728a991fbea6be198d7fc47faa7f17d7f3bb046cb259580`. These are audit evidence only and must be superseded by the exact post-authorization state binding.

## Cost and budget

Fresh local encoding of the exact packet through `TinkerGLMBackend.encode(adapter.request_turn(packet))` used tokenizer revision `aca966e4e02791568aa6a4ced368624b3d897f42` and chat-template SHA-256 `3740abcea51c45830cb3ca562084ad5fb2ef53589376f73332e9886f93ade41c`: **3,310 input tokens**. With `MAX_OUTPUT_TOKENS=2,750`, the frozen no-cache provider upper is **`$0.0494991`**. The independent outer transaction reserves the fixed **`$0.05`** ceiling; these are deliberately different numbers (`p0_gate1_controller_adapter.py:40-46`, `p0_gate1_controller_outer.py:24-27,246-251,266-288`). `--budget-cap-usd 200` binds the full authoritative experiment cap, not the per-call charge.

Read-only authoritative snapshot at 15:33 EDT: root `/Users/estelle/Library/Application Support/MarketRSI/budget-authoritative-20260916-01`, experiment `kalshi-research-glm53-20260907-01`, cap `$200`, metered `$85.122553742`, effective `$91.481134622`, reserved `$2.30`, global available `$106.218865378`; setup allocation `$10.60`, effective `$8.328494468`, reserved `$2.20`, available **`$0.071505532`**. The candidate ID has no job and both global/setup availability exceed the `$0.05` reservation. `invoice_reconciliation_complete=false` remains a disclosure; the runner still admits only from the authoritative available balances and later records returned metering or conservatively retains uncertainty. Recheck the snapshot immediately before launch; do not manually reserve.

## Only permitted entry point and launch command

Use the outer Supervisor parent, never `p0_gate1_controller_live_entry.py` directly:

`research/market_rsi/supervisor_harness/p0_gate1_controller_supervisor_parent.py`

It starts the fixed child with the same pinned interpreter, installs the exact PID/command/watchdog claim before credential access, and exposes no production child override (`p0_gate1_controller_supervisor_parent.py:23-65,89-138`). After explicit authorization and its journaled decision revision, replace the two angle-bracket values with the exact newly captured state snapshot. Then execute exactly once:

```sh
cd '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local'
GATE1_RUN_ID='market-rsi-gate1-controller-20260922-03'
GATE1_EXPECTED_HEAD='<POST_AUTHORIZATION_GLOBAL_STATE_HEAD_SHA256>'
GATE1_EXPECTED_DECISION='<POST_AUTHORIZATION_DECISION_DOC_SHA256>'
PYTHONPATH='research/market_rsi' PYTHONDONTWRITEBYTECODE=1 \
  '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' -B \
  research/market_rsi/supervisor_harness/p0_gate1_controller_supervisor_parent.py \
  --root "/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/${GATE1_RUN_ID}" \
  --claim-root '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/p0-gate1-controller-claims-v1' \
  --global-state-root '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/research/market_rsi/artifacts/supervisor-global-state-20260917-01' \
  --decision-doc '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/research/market_rsi/supervisor_harness/RESEARCH_STATE.md' \
  --budget-root '/Users/estelle/Library/Application Support/MarketRSI/budget-authoritative-20260916-01' \
  --packet '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/p0-data-admission-gate1-packet-20260922-03/controller-input.json' \
  --runtime-receipt '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/market-rsi-gate1-controller-20260922-02/runtime.json' \
  --env-file '/Users/estelle/Library/Application Support/MarketRSI/tinker-gate1-20260921.env' \
  --tokenizer-cache '/Users/estelle/Library/Application Support/MarketRSI/tokenizer-cache-glm53-20260921-01' \
  --experiment-id 'kalshi-research-glm53-20260907-01' \
  --budget-cap-usd '200' \
  --cycle-id "${GATE1_RUN_ID}" \
  --expected-packet-file-sha256 'c819e55db781b6620cd2c4923afc442027312e082264127e4c1cadf100b6f614' \
  --expected-packet-canonical-sha256 'ae89eb930c1b4bc775ad3f02646b1f1b341ce082f530fc58119b915d24b76c18' \
  --expected-head-sha256 "${GATE1_EXPECTED_HEAD}" \
  --expected-decision-sha256 "${GATE1_EXPECTED_DECISION}" \
  --prior-canary-sha256 '8e5f86aa20101979385c5fb57de3fa1fb978cf04036b5a483a15a07e13984ed9' \
  --release-tag 'market-rsi-protocol-v0.1.21' \
  --expected-source-sha256 '872f05ae48fa49deeb811bc6ca4705652168f198b5f1f9d69d3ce172ad0986da' \
  --supervisor-root "/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/${GATE1_RUN_ID}-supervisor"
```

No `--catalog`, `--expected-catalog-file-sha256`, or `--catalog-commitment-id` is valid for this packet. Do not source the credential file into the shell, log its content, call the child directly, wrap the invocation in a retry, or reuse `...-03` after any terminal outcome.

## Immediate preflight and terminal acceptance

Before the one command: (a) confirm written authorization and journal revision; (b) snapshot and paste the exact idle state head/document hash; (c) recompute source, packet-file, packet-canonical, runtime, and canary hashes; (d) confirm the 324 controlled paths remain clean and the tag is still published to the authorized origin; (e) re-encode locally and require the calculated upper `<= $0.05`; (f) re-read budget and require candidate absent plus both balances `>= $0.05`; (g) rerun all five uniqueness/process/container checks; and (h) confirm the packet/runtime/env/tokenizer/claim-root paths are regular, non-symlink inputs. The child repeats the mutable state, budget, and process checks immediately before reservation and again immediately before dispatch (`p0_gate1_controller_outer.py:240-251,300-331`).

After termination, accept either a reviewed single response or a terminal failure—never an automatic redraw. A successful launch result requires all of the following:

- adapter raw bytes preserved as both `adapter/<ID>/raw-response.json` and `raw-response.txt`; a provider receipt with one sample, `finish_reason=stop`, 1–2750 output tokens, model/session provenance, returned token metering, `provider_called=true`, and `automatic_retry=false` (`p0_gate1_controller_adapter.py:269-315,542-589`);
- exact submission/decision plus either bounded-plan `field-provenance.json` and `task.json`, or isolated non-executable `proposal.json`; all advertised choices remain documentation-only, and no `compiled-plan.json`, public fetch, sealed-data read, or formal admission should appear for this no-catalog packet (`p0_gate1_controller_outer.py:89-136,368-429`);
- outer `review.json` and `result.json` hash-linking publication, runtime, packet/input, admission, preflight, adapter result and chosen task/proposal, with `passed=true`, `execution_mode=live_pinned`, `ledger_outcome=metered_terminal`, `provider_sample_max=1`, `public_fetch_performed=false`, `formal_data_admitted=false`, and global state closed `passed` to the exact review SHA (`p0_gate1_controller_outer.py:405-467`);
- authoritative budget job `metered_terminal` with returned provider receipt and cost `<= $0.0494991`; if remote usage is unavailable, preserve `uncertain_terminal` at the full `$0.05`, treat the Supervisor result as an incident, reconcile explicitly, and do not retry (`p0_gate1_controller_outer.py:341-366`);
- Supervisor `artifacts/<ID>-supervisor/result.json` with `passed=true`, `child_exit_code=0`, `incident_created=false`, `automatic_retry=false`, and watchdog `active_task=null`; independent terminal evidence must show the exact child absent, exact container absent, and budget mapped to settled (`bounded_live_supervisor_parent_v1.py:169-211`). On failure/stall, require `terminal-cleanup.json`, `controller-repair-input.json`, incident receipt, `cleanup_verified=true`, and preserved child log rather than a second launch.

**Conclusion:** all immutable technical inputs and present-day dry capacity support one bounded v0.1.21 Controller request under the production Supervisor. The launch remains **REPLAN/HOLD** until the Supervisor receives explicit paid-request authorization, records it through the global decision state, substitutes the resulting exact two hashes, and reruns the perishable checks. No provider/network/fetch was called, no budget was reserved, no protected state was changed, and no Dev/Final material was inspected in this audit.
