# v0.1.25 D0-to-request bridge independent review

## 2026-09-28T21:01:30Z — non-author verdict: PASS

I independently reviewed the stable candidate in `/Users/estelle/Developer/market-rsi` under the applicable `AGENTS.md` and the indicator-evaluation stage boundary. The changed causal stage is only offline request-plan compilation, before raw data in `raw data -> raw indicator -> prediction -> objective -> PnL`. I did not contact a provider or source, read credentials or a data catalog, open Train/Dev/Final, fetch or retain external bytes, admit data, train or evaluate a model, or perform a commit, tag, push, release or canary.

### Stable source and release inclusion

- Recomputed controlled source: 341 files, canonical digest `c80531648d07f83ff73c1c70c3a8c0d5fd5d02459bb1957c875959daa51faee2`.
- Bridge source SHA-256: `469d0f5e548ceb18d3e7aefdce1d8cf36558c1acbcfa110e9c319fe5eddfe9b2`.
- Adversarial test SHA-256: `271f817f34de7193763e1deac36ad2771ee85e1db610423b5377fab0b6081733`.
- Release manifest module SHA-256: `cf65cee14a0304b8664b1c130e6d8966f746487ad88d581aa03a0e0e5c1aaac7`.
- Both new source and test paths occur exactly once in `PROTOCOL_FILES`; `source_hashes()` returns their exact hashes. The bridge/release diff is minimal, and the architecture text continues to describe the candidate as offline, non-executing and not yet independently authorized for later stages.

### Exact immutable D0 binding

Compiling from the actual durable D0 artifacts, not reconstructed test fixtures, passed and reproduced the same result twice. The bridge binds:

- D0 decision file SHA-256 `01054900be9075f0fef57b9e1481abb73f722b2223d664df24db8e6c81dcc216`, canonical decision digest `a4007dfc53d1cda8722e51f2545e95f3666e9d6e3c93c631606809e4f5a763cd`;
- submission file SHA-256 `ed1e391532112f413962d13ab1e6d9718cf92eb0e90ace8caeb31473e4f402d6`, canonical submission digest `71d3b31caa90b05d95578988bf747386390701421d587cdebef571a59bf051fa`;
- provenance file SHA-256 `bcd768989e33af91e42ba4d3db35201f294fb6be6d9a3182165f890140eeec65`, canonical provenance digest `d1344a446e9e04d9f56337cb60d501c7475869213cec7f67db8e00d11a8f683a`, and raw Controller response SHA-256 `126a5a1309251721a45b86ecc51955083234b60a9b40ffe09f4cf03e0f89fd27`;
- prior-canary packet file SHA-256 `bb15603ffd32c8b18b17339ce88aec15294862950d8dc8cb3036485716fe1acd`, canonical packet digest `39114563de6f34b100431d02edb0677184a40f83ce9c0d3eda8afe76f963620b`, and scope-options digest `e7834b4946721201feaac1893e356cebd84a3df6eba686d85381cfa612bbd4d0`;
- published D0 release tag `market-rsi-protocol-v0.1.25`, commit `ed4048e55096b763ba763526e768057b5180cdeb`, annotated tag object `67b8e4a88e22c1f00e60850f521b26282517d682`, and controlled-source digest `c61f48e21084671c1ff1257639f6a5d5ccfc8c1a64065e02157c5eb75c10a2d4`. These equal the immutable D0 `publication.json`; the new 341-file digest is correctly treated as an unpublished candidate, not retroactively substituted for the D0 release.

Any exact-decision, submission, provenance, packet, scope-options, raw-response or D0-source mutation fails closed. The bridge additionally rejects generic-validator-acceptable source reassignment, future-role reassignment and internally consistent horizon mutation.

### Registry, capability and output authority

The code-owned mapping is unique and explicit: opaque pair `src_bbbbbbbbbbbbbbbbbbbbbbbbbb` + `rsp_ffffffffffffffffffffffffff` maps to `polymarket_official_trades`, then to the complete official registry record and `inspect_official_documentation` capability with handler `p0_gate1_public_fetch.fetch_snapshot:v1` and sample contract `single_registry_document_v1`. Registry URL, opaque pair, capability and legacy envelope each have hard-pinned canonical hashes; missing, duplicated, reassigned or mutated records fail closed. The caller cannot supply a URL, method, request ID, query, body, header, handler, limit, retry rule or authority field.

The deterministic request-plan canonical SHA-256 is `34b45266df887dbf308b196eac865bfc5a3a6b65257c667849605e5a8b9b812c`. It contains exactly one prospective `GET` to the fixed official-documentation URL, empty query, no body, fixed safe headers, one-document/one-later-attempt/1,000,000-byte/300-second ceilings, zero provider requests, zero provider bytes and zero provider cost. Redirects, authentication, credentials, purchase, writes, link following, alternate pages and automatic retry are false; failure is terminal for the attempt.

`plan_only` is the only true authority marker. Request execution, fetch admission, network, credentials, spend, snapshot retention, catalog or prediction-data access, Train/Dev/Final, training, evaluation/scoring, redistribution, repository operations and publication are all false. The separate future-admission object also has `fetch_authorized=false`, requires a fresh attempt ID, forbids same-ID retry, and requires exact plan/source/URL/request/byte bindings plus separate rights, retention, candidate/formal admission and outer watchdog review. HTTP success would not establish rights or data admission.

### Independent checks

- Actual immutable D0 compile performed twice: byte-equivalent Python objects and fixed plan hash above.
- Focused offline suite independently rerun on the durable pinned Python runtime: 12/12 passed, including exact compilation, caller-field rejection, registry/capability/envelope mutation, semantic reassignment, provenance/packet/source mutation, release inclusion and forbidden-import checks.
- The author test log SHA-256 is `e050d1828ac70f11aab1c7667d09e6e69b536417177d949d0c517b160e4143ad`; it records the separate pinned-runtime full suite as 516/516 with two documented environment skips. I did not rely on that full-suite claim for the exact hashes or focused verdict above.
- Static inspection found no bridge import or call path for filesystem I/O, HTTP/network, subprocess, credentials, provider, budget, catalog/data, training or evaluation. Its transitive registry imports define pure constants/functions and perform no action on import.

### Verdict and claim boundary

**PASS.** The candidate is deterministic, exact-D0-bound, registry-bound, fail-closed and non-executing. It closes only the local D0-to-exact-request-plan compilation gap.

This verdict covers only an **unpublished offline release candidate**. It grants no commit/tag/push/release authority, no current-version canary authority, no provider or model call, no network/document/public-data fetch, no snapshot retention, no rights finding, no candidate or formal data admission, no catalog or Train/Dev/Final access, no training, no evaluation/scoring, and no experiment or prediction-improvement claim. Publication, a fresh release-bound canary, an exact fresh-ID watched-fetch admission, retention/rights review, and every later data or experiment gate remain separate authorizations.
