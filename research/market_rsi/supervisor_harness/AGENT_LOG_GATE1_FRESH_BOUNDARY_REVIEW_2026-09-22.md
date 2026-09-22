# Fresh independent Gate 1 boundary review

Registered for a bounded read-only review after two older task chats ended without visible verdicts. This curated log is copied from the independent agent's messages; it is not a raw tool stream.

## Independent result on original snapshot

- Verdict: **REPLAN** on controlled-source digest `48b7b78f2839dc1a215cce28627956f890359ad23bf21a63b4fe5e7fcb614afa` (324 files; HEAD `b9095a7`).
- Reproducer: frozen packet reports no reviewed real Train catalog (`build_p0_gate1_controller_packet.py:170-178`); tool schema and capability list hide `fetch_fixed_public_sample` (`p0_gate1_controller_adapter.py:113-120,192-210`). The GLM parser only coerces fields and does not enforce the operation enum (`codex_glm_responses_adapter.py:300-305`). `_submitted_action` accepted a crafted single terminal call using that hidden operation (`p0_gate1_controller_adapter.py:374-389`), and the research contract compiled it as a plan. The independent agent observed `advertised=['inspect_official_documentation']` but `accepted=bounded_plan ['fetch_fixed_public_sample']` with exact 6 requests / 2,000,000 bytes / 15 min / $0.
- The outer path still rejected the plan without catalog (`p0_gate1_controller_outer.py:101-109`); no network, protected-data, budget-cap or rights bypass was observed. The defect is a known paid dead end and an inaccurate capability contract.
- Other checked guards: exact packet equality, immutable source/rights/hard-limit checks, $0.05 per-call bound, publication/state/budget before credential, and proposal review-only. The old zero-provider canary passed but exercised only a document plan, not this adversarial call. Agent made no edits or provider/network/Dev/Final calls.
- Supervisor independently reproduced the defect with a new failing adapter regression, then implemented a narrow operation-enum check. **This log does not review the repaired source.** A fresh post-fix independent review is required.
