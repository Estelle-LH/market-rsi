# Polymarket v2 cursor acquisition contract — agent log

- 2026-09-22 15:56 EDT — Started the bounded offline implementation after reading `research/market_rsi/AGENTS.md`, `RESEARCH_STATE.md`, `RESEARCH_SUPERVISOR.md`, `AGENT_LOG_REAL_TRAIN_ADMISSION_CRITICAL_PATH_2026-09-22.md`, the legacy v1 builder/tests, and the preserved Train-side `artifacts/nfl-2024-refresh-20260921-01/fetch_v2.py` plus README/receipts. Observed gap: released code only describes legacy v1 fixed-offset sampling; no code-owned v2 state-machine manifest validates invariant query fields, opaque cursor transitions, termination, or aggregate caps. Scope is a new no-I/O v2 module and focused frozen-response tests. The documented official v2 behavior already recorded on 2026-09-21/22 is reused; no new live search or network request is necessary. The legacy v1 module will not be edited. This contract will not grant network authority, resolve rights, authenticate provider origin, admit Train, or inspect Dev/Final. Planned adversarial checks: endpoint/version/query tamper, empty/repeated/looped cursors, incomplete/extra pages, envelope/pagination mismatch, page/request/byte/time caps, raw-byte/hash mismatch, wrong condition/token, duplicate JSON members, redirects/auth/write flags, and unchanged v1 behavior.

- 2026-09-22 16:03 EDT — **Implementation complete; PASS for the offline contract only.** Added `p0_polymarket_v2_cursor_acquisition.py` and `test_p0_polymarket_v2_cursor_acquisition.py`; no existing source file was modified. Final source SHA-256 is `6c329f546096eae1a604810a0d586d85e5353325a4141ec6ea96b1b8dc8e080f`; test SHA-256 is `7679375c5094ead1adbd35355480221b7b64adb41b38dbf0cf28f97ef29056b0`. Legacy `p0_gate1_trade_query.py` remains byte-identical at `60117c1ea76bfec6bca818d31ae05699f01ebe412ffd1babd1363e8da085784e`.

## Reused research and design choice

No new method or uncertain external fact was introduced, so the existing primary-source reading was reused as required by `AGENTS.md`. The recorded 2026-09-21/22 search was `site:polymarket.com terms of service API data download use historical data Polymarket`; the directly read official page was `https://docs.polymarket.com/api-reference/feeds/list-trades`, specifically its v2 query-parameter and pagination sections, with the Data API overview/rate-limit table also recorded in the preserved 2024 capture README. Local source evidence showed `/v2/trades`, invariant `condition`, `limit=1000`, `taker_only=true`, `filter_amount=0.01`, and opaque `pagination.next_cursor` copied to the next request. Transfer limitation: documentation and a self-consistent receipt do not prove data rights, provider authenticity, publication time, Train suitability, or that API behavior will remain unchanged; any changed response/query shape must fail this version and receive a new reviewed contract.

Alternatives considered:

1. Keep legacy v1 fixed offsets as the baseline. It remains correct for the small released sample contract but cannot prove v2 cursor completeness. It was preserved unchanged and is explicitly regression-tested.
2. Promote artifact-local `fetch_v2.py`. Rejected: it has a real HTTP transport, is not released/controlled, mixes execution with validation, and its receipts do not constitute external authority.
3. Implement a transport-free state-machine manifest plus byte-level validator. Chosen: it can be attacked entirely with frozen responses and later composed with a separately authorized executor without granting that authority itself.

## Exact implemented boundary

- `p0_polymarket_v2_cursor_acquisition.py:22-58` pins separate v2 schema/source/API identifiers, exact HTTPS host/path/method, query names/values, fixed headers, and hard ceilings: at most 300 streams, 3,000 requests/pages, 100 pages per stream, 2 MB per page, 500 MB total, three hours, and 4,096 cursor bytes.
- `:112-168` treats cursors as opaque but transport-safe allowlisted tokens; requires exactly two canonical asset IDs per condition stream; rejects duplicate stream/condition/asset identities; and type-checks every caller cap as a positive exact integer rather than accepting booleans/floats.
- `:172-267` constructs the initial request and manifest only from trusted constants and fixed stream selections. `network_execution_authorized=false`, no redirects/authentication/payment/write/retry, and all rights/admission/Dev/Final/improvement claims remain false.
- `:277-332` reconstructs every derived manifest field before accepting it, realizes later requests by changing only the single `cursor` query value, and emits a receipt contract bound to the canonical manifest hash.
- `:335-374` rejects duplicate JSON members, non-finite constants, non-object or extra-field envelopes, and noncanonical UTC-millisecond timestamps.
- `:377-575` validates a successful receipt and exact supplied bytes without transport: strict terminal flags and counts; monotonic per-page timing; exact stream/order/index/method/URL/query/header/status/content-type; page and aggregate byte hashes; `data` length no greater than the declared limit; exact-integer `limit`/`offset`; Boolean `has_more`; condition/token containment; duplicate-row rejection; nonempty continuing pages; nonempty unique cursor transition; null-cursor termination; no pages after termination; and request/page/byte/time caps. Its result explicitly keeps network authorization, source rights, provider authentication, Dev/Final access, formal admission and improvement false.

## Adversarial findings incorporated

An independent reviewer attacked the initial candidate before completion. The first concrete counterexample used a self-consistent terminal response with 1,001 rows while declaring `limit=1000`; the draft checked the declared limit but not `len(data)`. The final validator now requires `len(data) <= LIMIT`, with a 1,001-row regression.

The same reviewer then found Python equality could treat `False == 0` and `1000.0 == 1000`, and that the draft admitted a one-token stream. The final source requires exactly two assets; exact `int` types (not Boolean/float) for pagination limit/offset, receipt ordinal/index/status/byte/row fields and zero redirect/retry counters; and canonical query equality so a float-valued query cannot match the integer request. Dedicated regressions cover all four examples. The final hash above supersedes the reviewed draft hash `a85ade6386e45338a1c3844b71dcaa247e3cae96fd4f090276d8b0c0cb9bddb2`; rereview must bind `6c329f...`.

## Verification

Focused pinned-runtime command:

```text
PYTHONPATH=research/market_rsi PYTHONDONTWRITEBYTECODE=1 \
  /Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python -B \
  -m unittest supervisor_harness.test_p0_polymarket_v2_cursor_acquisition -q
```

Result: **25/25 passed**. Cases include a valid two-stream/multi-page chain and terminal empty stream; v2/version/endpoint/invariant query binding; opaque cursor URL encoding; empty/repeated/non-adjacent loop rejection; unfinished and post-termination page rejection; continuing-empty rejection; inconsistent `has_more`/cursor; extra/mistyped pagination/envelope fields; 1,001-row rejection; Boolean/float integer attacks; request/page/per-stream/page-byte/total-byte/time caps; exact raw bytes/hash/set; duplicate JSON/NaN; wrong condition/token and duplicate rows; receipt order/count/authority tampering; deterministic stream sorting; and the separate unchanged v1 offset path.

Adjacent pinned-runtime command covering the new contract plus legacy v1 query, plan compiler and outer transaction: **68/68 passed**. Wider Gate 1 acquisition/controller command covering the new test and nine existing packet/adapter/contract/materializer/query/compiler/outer/fetch modules: **137/137 passed**. Scoped `git diff --check` passed.

## Remaining gates

This is unpublished offline development. It is not yet in `protocol_source_release.FILES`, has no released executor, consumes no Controller task, and cannot validate whether an executor was actually authorized or whether supplied bytes came from Polymarket; it validates exact internal byte/query/cursor continuity only. Before any network use, the Supervisor must independently review the final bytes, add them to a new controlled-source release, bind a compatible exact task/selection manifest, implement and canary a separately authorized transport, resolve rights, and preserve failure receipts. A structurally valid acquisition receipt remains a candidate source receipt—not a formal Train admission receipt. No provider/network/fetch, catalog/protected-state mutation, Dev/Final read, commit, tag or push occurred.
