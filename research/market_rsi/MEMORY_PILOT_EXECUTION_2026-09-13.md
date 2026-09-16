# Frozen execution rules for the three-round pilot

This supplements, not rewrites, `MEMORY_PILOT_2026-09-13.md`. New source tag:
`pm-memory-pilot-v0.1.0`. It must be published after synthetic tests/canary and
before any actual model fit through this runner or any GLM session.

The three initial Train files completed with 568,838 / 542,710 / 349,116 paired
rows (1,460,664 total). Their counts/moments match the frozen rev6 kernel. This is
three recorded T12 hours, not three full trading days. All caches are local
runner data; hosted GLM receives aggregate QA, not rows or raw identifiers.

Initial arm context is identical except its arm label. `archive` receives its
own prior observable tool records, proposals, errors, interpretations, costs and
consumed-Dev score. `independent` receives an empty archive every round. Both
receive the same expanding Train and initial concentration finding. We do not
add a separately rewarded “learn mode” or tune the GLM weights. Three sessions
per arm; first valid submission ends each session. No resampling or selecting
between alternative controller responses.

Both use the same baseline plan at each round: lag-delta, no-intercept OLS. An
arm can build up to three current-round candidates from that baseline or a prior
candidate in the same round. Archives can inform new proposals, but neither arm
receives an extra inherited checkpoint as a free starting advantage. One proposal
changes features OR trainer/normalizer. This measures benefit of the research
archive, not joint weight inheritance, nor an unconstrained algorithm invention
benchmark. The four-method library is an initial executable scope, not a claim
to cover all methods.

Feature choices: lag delta, its absolute value/signed square root/cube; current
mid minus 0.5; current bid–ask spread; log(1 + past quote count); lag multiplied
by spread or centered mid. These are past/current values only. Missing rows are
not imputed. No feature uses future spread or future activity to select rows.
Normalizers are none or fit-only mean/std. Uniform Train row weights, no output
clipping, fixed seed23. Candidate models: Ridge, ElasticNet, RandomForest and
HistGradientBoosting with the existing tested parameter bounds.

Train-only chronological check: earlier Train files fit, last Train file scores.
No random split. The controller states its question/hypothesis/support/refutation
before fitting and records a result-bound interpretation afterwards. All valid
zero labels remain. Each child gets one CPU thread, 180 seconds and 2 GiB RSS;
failure is preserved, not silently repaired or downsampled. At most three fits
per researcher session. A common baseline diagnostic is shared by both arms.

After BOTH round submissions, refit each submitted specification on that
round's whole Train BEFORE opening its Dev file. Score once. Only then does Dev
become Train. Round order is archive/independent, independent/archive,
archive/independent. Failed candidate attempts can be interpreted and followed
by a different planned candidate within the three-attempt allowance, never
reusing an ID. A failed controller session, chosen refit, shared baseline or
source operation stops the paired study and preserves partial outcomes; do not
pretend the missing side scored zero or quietly choose another model.

Primary final models: the Round 3 submissions refit before Round 3 Dev, frozen
unchanged afterwards. If the controller explicitly submits `baseline`, that is
its model, not a failed result. No performance-based fallback after Dev. The
later September 10–12 T12 files open only after all three paired rounds and
final-model commitments. No final score goes back to either controller. Report
both arms, common OLS and zero predictions, equal-hour MSE, price-bps RMSE,
per-date scores, paired skill/IC/calibration and market concentration. Preserve
every prediction and full per-market table outside hosted-model context.

This is chronological within a market universe, not a market-disjoint study.
Complementary tokens share the same anonymous market group. Overlapping labels,
same-market dependence, possible carryover across dates and short coverage limit
claims. We do not infer IID standard errors or effective sample size from row
counts. There are only three later files: formal ≥20-session promotion fails by
design. The old missing capture provenance is not repaired by this experiment.

Spending: same $8.44038144 session ceiling, $25.32114432 per arm; at most
$50.64228864 combined out of the existing $200 authorization. The implementation
uses the original append-only ledger; actual metered charges, unresolved upper
bounds and reservations stay separate. No new allocation or invoice claim.
CPU runs use the existing machine; incremental host costs are not metered here.

## Implementation research and tests

Reuse the Ridge/ElasticNet/RandomForest/HistGradientBoosting constructors and
explicit-parameter checks from `historical_grid_learning.py`. The applicable
research and earlier four-trainer checks are recorded in
`LITERATURE_TO_HARNESS_2026-09-10.md` (scikit-learn1.6 common pitfalls §10.1–10.2,
FPP3 §5.10). The new input adapter does not reuse the grid's old admission claim.
This is the same numerical estimator family on causal event features; future
data must never fit its scaler or weights. Keep row-mask/hash parity, finite
features, temporal order and budget gates executable.

Archive comparison rationale and read portions of Reflexion/TimeSeriesSplit are
in the parent protocol. Reuse the official Codex MCP route/timeout documentation
and the existing credential-isolated provider. This uses that architecture, not
a new Codex provider/model or a newly written execution harness.

Planned tests: all four actual CPU fits on synthetic data; future-label isolation;
scaler fit isolation; cache corruption; one-layer changes; archive access; record
chain corruption; first submission only; held-out paired commitments; actual
Codex tool invocation, real synthetic fit and terminal handshake without an extra
provider turn. Results must be recorded separately after running.
