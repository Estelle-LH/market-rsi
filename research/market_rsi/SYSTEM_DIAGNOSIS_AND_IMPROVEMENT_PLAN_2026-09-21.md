# Market RSI system diagnosis and improvement plan

Date: 2026-09-21
Audience: advisor review
Status: diagnosis accepted; operational P0 largely implemented; scientific P0 blocked on data admission

Current update: packet commitments, outer supervision and structured terminal
submission are published through `market-rsi-protocol-v0.1.15`. The latest
post-publication production-path canary passed with zero provider calls and
`$0`. The next local candidate removes a separate release-checking friction:
documentation-only commits may follow a protocol tag, while any controlled
source difference still fails closed. That candidate is not published and no
new paid Controller request is authorized.

## 给导师的简短版本

这周发现的核心问题不是模型不够强，而是系统把三类事情混在了一起：
系统连接和故障恢复、真正的预测实验、以及 harness 自己的改进。因此我们
花了很多时间修运行问题，却还没有形成足够强的科学结果。最新一次 Gate 1
启动又给了一个很具体的例子：发布和几个模拟检查都通过了，但真实命令使用
的是 JSON 文件 hash，runner 检查的是同一内容的 canonical hash，所以在调用
模型之前停止。没有花模型费用，Supervisor 也正确清理了，但说明 canary 没有
完整走过生产路径。现在的改法是把三个循环分开：Supervisor 专门保证系统不
停死和不越界；Controller 负责选择科学问题；每完成一批实验，再单独检验
harness 是否真的变强。正式论文要比较固定 harness、带结构化经验的 harness
和 co-evolving harness，并且使用相同模型、数据、预算和隐藏评估集。

## Executive summary

The project has built a strong safety and accounting boundary, but its
scientific throughput is still low. The main system problem is not a shortage
of agents. It is that operational recovery, scientific experimentation, and
harness evolution have been mixed together. A transport or hash repair is not
a research result; a Train-only score change is not evidence that the harness
improved; and a human-authored harness edit is not autonomous self-improvement.

The next version separates three loops:

1. **Operational loop:** start, monitor, classify, repair, verify and resume.
2. **Scientific loop:** test data, feature, trainer, calibration and prediction
   hypotheses under a frozen evaluator.
3. **Harness loop:** after a batch of experiments, propose and test one change
   to the research process itself against the prior harness version.

The immediate priority is to make the operational loop fail before launching a
worker whenever the exact production inputs do not match their commitments.
After that, the highest scientific priorities remain prediction-data admission,
a strong ordinary-model baseline, structured evidence memory, and a controlled
comparison of static versus co-evolving research harnesses.

## Where we are now

The operational loop is no longer the main research bottleneck:

- exact file and canonical packet commitments are enforced;
- Supervisor owns liveness, immutable incidents, budget settlement and exact
  process/container cleanup;
- the Controller has one structured, non-operational terminal submission;
- v0.1.15 is published on the user's fork and its post-publication zero-provider
  production canary passed;
- no failed paid ID has been reused or retried.

The scientific loop is still blocked before prediction experiments:

- no valid model-authored Gate 1 data investigation exists yet;
- 2023 has 237/285 strict market matches and sparse regular-season fills;
- 2024 has 67.64% 60-second and 90.87% 300-second event-label coverage;
- 2025 whole-season trade access is not yet audited;
- the old Final has only 11 dates, below the frozen 20-date floor;
- HGB's 18.9% Train-only gain over Ridge is not an OOS RSI result.

Therefore the next scientific milestone remains: admit a defensible data cohort,
freeze the strongest ordinary baseline, then compare static, structured-memory
and co-evolving harnesses under one evaluator and budget.

## Concrete incident that exposed the current gap

Protocol `market-rsi-protocol-v0.1.11` was committed, annotated and published
to the user's fork. Fresh post-publication adapter, transaction and Supervisor
parent canaries passed without provider calls or cost.

The first authorized Gate 1 Controller launch then stopped before reading the
provider credential or calling GLM. The immutable failed ID is
`market-rsi-gate1-controller-20260921-01`. The child reported:

> `ValueError: Gate 1 packet differs from frozen hash`

The Supervisor did the right things after the failure: it created one incident,
did not retry, verified the exact process and container absent, and spent no
provider money. However, this failure should have been detected by the parent
before a child was launched.

The causal bug is precise:

- the Gate 1 packet builder recorded SHA-256 of the pretty-printed JSON file;
- the live runner loaded that JSON and compared SHA-256 of canonical JSON;
- both represented the same object but had different bytes;
- the canaries constructed canonical JSON directly, so they did not reproduce
  the real artifact-path mismatch.

This is not a model failure, data failure or scientific negative result. It is
a production-parity preflight gap.

## What the incident says about the system design

### What worked

- Published source and permanent run identity were preserved.
- The provider was not called and no provider cost was incurred.
- The failed run was not silently rewritten or retried.
- The outer Supervisor recorded an incident and verified cleanup.
- Data admission, prediction and Final remained blocked.

### What needs improvement

1. The parent must validate exact file bytes and canonical content before
   spawning a worker.
2. Hash names must state what they hash; generic `packet_sha256` is ambiguous.
3. A post-publication canary must exercise the exact production CLI, artifact
   paths and arguments, replacing only the final paid provider call.
4. A passed component canary is not enough; the composed production path needs
   its own acceptance test.
5. The dashboard should distinguish operational capability from scientific
   progress.

## New live finding: the Gate 1 Controller had no terminal-answer harness

The published v0.1.13 transport and supervision path passed, but the first live
Controller response did not produce a plan. GLM used exactly 2,048 output
tokens on open-ended comparison of the allowed questions and sources, returned
`finish_reason=length`, and was cut off before the required JSON object. The
raw response is useful evidence that the model understood the task and several
trade-offs; it is not a valid decision and cannot be repaired after the fact.

This changes the diagnosis. More timeout would not help: the provider returned
normally. More data would not help this layer either. The direct one-shot text
adapter is missing the terminal behavior already present in the stronger Codex
Controller harness: an explicit submit action, a reserved answer budget and a
deadline phase that stops exploration and requires submission. Simply raising
the token ceiling may make the same deliberation longer and increases cost
without guaranteeing a result.

The next Controller revision should therefore be tested offline as a harness
change, not treated as a retry:

1. require an answer-first structured submission through the existing trusted
   submit boundary;
2. reserve enough tokens for the terminal JSON independently of research
   tokens;
3. stop the turn if the submission is absent instead of inferring or repairing
   a plan from private reasoning;
4. test long-deliberation, truncated, malformed and valid-first-answer cases;
5. publish new immutable bytes and obtain new authority for a fresh ID.

The terminal run `market-rsi-gate1-controller-20260921-02` made one provider
call, fetched no public data, read no Dev/Final data and admitted no formal
data. The authoritative budget records `uncertain_terminal` at the conservative
`$0.05` upper because the strict provider receipt rejected the length-truncated
response; token-based preview cost was `$0.0282852`, but neither number is an
invoice. Exact process/container cleanup passed and no retry occurred.

## Target system

The trusted Supervisor owns global state, budget, liveness, immutable evaluator
and bottleneck recovery. The Controller chooses scientific questions and the
next bounded action. Researchers implement those actions in local containers.
An independent evaluator returns filtered aggregate evidence. The archive keeps
all positive, negative and failed attempts.

Every task must move through an enforced state machine:

`DISCOVER -> PLAN -> EXECUTE -> VERIFY -> ARCHIVE -> NEXT`

Failures are classified as infrastructure, data, scientific negative,
contamination or budget. Only a causal infrastructure repair followed by a new
canary can permit a fresh run ID. Scientific outcomes are never retried for a
better score.

## Evidence required for a publishable result

The main comparison should hold the controller model, data, tools, evaluator,
number of actions and dollar budget fixed while varying only the research
system:

1. strongest ordinary-model baseline;
2. static harness with fresh context;
3. static harness with structured evidence memory;
4. co-evolving harness with the same structured memory.

The co-evolving system must beat the strongest static system, not merely a weak
baseline. The result needs multiple Controller seeds, paired date/game-block
uncertainty, calibration, breadth across dates, and one genuinely untouched
Final with at least 20 dates. PnL is a later secondary evaluation after the
prediction claim is established.

## Ordered implementation plan

### P0 — close the production-parity gap

Status: **implemented through v0.1.15.** A smaller follow-up release-gate
usability fix is verified locally but unpublished.

- Record separate `packet_file_sha256` and `packet_canonical_sha256` values.
- Validate both in the Supervisor parent before child creation.
- Preserve the old receipt and failed run unchanged.
- Add regression tests using the historical pretty-printed packet.
- Add one real-command, zero-provider post-publication canary.
- The pre-publication production-path version of that canary now passes; rerun
  it unchanged after publishing the reviewed source.
- Publish a new immutable protocol version; never move v0.1.11.
- Obtain new authorization before any fresh paid Controller decision.

### P0 — enforce bottleneck recovery end to end

Status: **implemented for the current Controller/Supervisor boundary.** It still
needs to be exercised by the eventual data, training and evaluation workers.

- Every active bottleneck has an owner, evidence, next action, pass condition,
  timeout and replan rule.
- No state may remain `blocked` without a bounded next action or an explicit
  external decision.
- Runner transitions, not prose alone, enforce data and budget gates.

### P0 — admit enough prediction data

Status: **current highest-priority blocker.** No formal cohort has passed this
gate and no new Final has been opened.

- Verify comparable season-wide identities, real trade/quote semantics,
  event-time labels, rights and coverage.
- Keep AMM and CLOB cohorts separate unless transfer is explicitly tested.
- Require a genuinely untouched >=20-date Final before formal scoring.
- Do not spend model-search budget on a cohort that fails data admission.

### P1 — establish the strongest ordinary baseline

Status: **partial.** HGB beat Ridge on opened Train rows, but the complete model
family comparison and frozen OOS baseline are not done.

- Evaluate no-change, linear/regularized, HGB, LightGBM, XGBoost, CatBoost and
  appropriate event/time-series models on identical rows.
- Freeze the strongest baseline before formal RSI comparison.

### P1 — replace narrative memory with structured evidence

Status: **designed, not validated in a formal comparison.**

Each record stores the hypothesis, causal stage, expected evidence, result,
paired delta, uncertainty, calibration, supporting and opposing observations,
cost, failure and reuse boundary. Retrieval must include the strongest
counter-evidence, not only prior successes.

### P1 — add controlled harness co-evolution

Status: **not yet a scientific experiment.** Current harness changes are
human-assisted operational repairs and must stay labelled that way.

After 8–12 scientific actions, the Controller may propose one harness change.
It must pass historical replay, leakage checks and a shadow comparison against
the prior version. Human-authored repairs remain labelled human-assisted.

## Advisor discussion questions

1. Is the paper claim best framed as evidence-aware co-evolution of an LLM
   research harness under noisy, non-stationary prediction evaluation?
2. Is the strongest static harness the correct primary comparator, with the
   ordinary forecasting model serving as a separate task-performance baseline?
3. Should the formal budget be normalized primarily by dollars, while also
   reporting experiment count and wall time?
4. Is a three-comparable-season controlled pilot acceptable before the stronger
   five-season benchmark, provided the pilot is labelled clearly and has an
   untouched >=20-date Final?
5. What minimum improvement and replication standard would be compelling enough
   for the intended venue?

## Current conclusion boundary

The system has demonstrated durable supervision, fail-closed accounting and
some weak evidence that LLM-guided research can alter model choices. It has not
yet demonstrated recursive self-improvement, stable superiority of Archive over
Fresh, generalization to a sufficient untouched market period, or profitable
trading. The next meaningful milestone is a clean static-versus-co-evolving
comparison after data admission and strong-baseline selection.
