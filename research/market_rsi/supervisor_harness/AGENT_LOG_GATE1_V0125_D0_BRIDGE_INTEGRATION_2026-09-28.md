# v0.1.25 D0-to-request bridge integration

- 2026-09-28 — Registered and waiting for both independent read-only audits. No implementation starts until both dependencies and the plan ready-step pass.

## 2026-09-28 — integrated stable offline candidate

**Integration verdict: PASS; independent review, release, canary and fetch remain closed.** Both preregistered audits passed before implementation:

- decision/capability gap audit SHA-256 `1a5fe06502dec5b2c555d362f093c31137ed99e77cd66cb8248bdc774e31e40a`;
- fetch-boundary audit SHA-256 `fb1eb8a30aea12326834e4af6ba5cf95ba59fdff8a9e76ba8ed2a805a4d11e9c`.

### Problem and changed causal stage

The single problem was that the independently reviewed D0 opaque source/response pair had no trusted deterministic crosswalk to the existing official-source registry and documentation capability. The only changed stage is offline request-plan compilation. The D0 bytes, semantic validator, provider path, low-level fetcher, rights/admission gates, target, horizon, split, training and evaluation remain unchanged.

The indicator-evaluation stage boundary was applied explicitly: this work remains before raw data in `raw data -> raw indicator -> prediction -> objective -> PnL`. It creates no observation, feature, prediction, score or PnL evidence.

### Evidence and alternatives

The integration reused the two local primary-source audits above and the immutable D0/release receipts. No live source or web research was needed or permitted. Alternatives were rejected as follows:

1. Passing a caller-built task to the generic HTTPS fetcher was rejected because the fetcher alone does not prove registry membership.
2. Fabricating a legacy bounded Controller decision was rejected because it would rewrite the Controller's scientific choice and add invented text.
3. Reusing the public-trade plan compiler was rejected because it is a catalog-bound trade-query lane, not a one-page documentation lane.
4. The selected design is a pure offline bridge that accepts only the exact D0 decision, exact provenance, exact packet and the pinned v0.1.25 controlled-source commitment.

### Implemented contract

`p0_gate1_source_scope_request_plan.py` now:

- revalidates and exact-binds cycle, decision, reconstructed Controller submission, field provenance, raw response, packet, scope options, v0.1.25 tag/commit/tag-object and base controlled-source digest;
- uses a code-owned injective mapping from `src_bbbbbbbbbbbbbbbbbbbbbbbbbb` + `rsp_ffffffffffffffffffffffffff` to the full `polymarket_official_trades` registry record and exact documentation capability;
- resolves exactly one `GET` to the fixed official documentation URL with empty query/body, fixed safe transport headers, one-page/one-attempt/1,000,000-byte/300-second ceilings, no redirects or retries, and explicit response/receipt/watchdog requirements;
- emits `plan_only: true` with request execution, fetch admission, network, credentials, purchase/spend, retention, Train/Dev/Final, training, evaluation, redistribution, repository and publication authority all false;
- requires a later fresh-ID admission to bind the exact plan hash before any transport. The output is not an admission object and cannot be consumed as authority.

The exact deterministic request-plan canonical SHA-256 is `34b45266df887dbf308b196eac865bfc5a3a6b65257c667849605e5a8b9b812c`. Its exact URL SHA-256 is `2f12d47b49fc82adafda53effcc7a11edaa9fbd85a6de9b9403cc90f86cfb3fc`.

### Stable source snapshot

- bridge source SHA-256: `469d0f5e548ceb18d3e7aefdce1d8cf36558c1acbcfa110e9c319fe5eddfe9b2`;
- bridge test SHA-256: `271f817f34de7193763e1deac36ad2771ee85e1db610423b5377fab0b6081733`;
- release manifest module SHA-256: `cf65cee14a0304b8664b1c130e6d8966f746487ad88d581aa03a0e0e5c1aaac7`;
- local candidate controlled-source digest: `c80531648d07f83ff73c1c70c3a8c0d5fd5d02459bb1957c875959daa51faee2` across 341 controlled files.

The two new source/test files are included in `PROTOCOL_FILES`; this inclusion changes only the unpublished local candidate. No commit, tag, push, release, provider call, credential read, network request, external byte, data admission, protected split read, training or evaluation occurred.
