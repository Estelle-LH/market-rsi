# What we carry forward from the earlier RSI experiments

This is a runner/human audit note, NOT model input. It cites old reports to
explain the starting design; it does not import their checkpoints, trajectories,
benchmark answers, task IDs, scores or paid plans into this experiment.

The historical reports contain later corrections and competing interpretations.
The entries below are process lessons supported by those reports, not a new
audit of every old artifact or provider invoice. In particular, neither
"the controller was too weak" nor "the training tasks were simply too easy"
has been established as the sole cause of the earlier results.

## Lessons and their current use

| Earlier issue | What we do now | Historical source |
| --- | --- | --- |
| Maximum reservations were reported as money spent, causing an early stop. Invoice coverage was incomplete. | Separate holds, terminal usage estimates and invoices; release unused holds only with evidence; preserve final funds. `paid_budget.py` already has offline regression tests. | [Weekly report, §3.2](../../docs/WEEKLY_PROGRESS_2026-08-28.md) |
| A serving/protocol failure was reported as model failure; a canary existed but had not been required by the paid evaluation path. | Require a verified end-to-end execution path and runtime fingerprint before scored paid trials. The completed GLM text canary is only the first component check. | [Handoff, execution update and §2](../../docs/HANDOFF_2026-08-28.md) |
| A budget guard led to changing the evaluation step limit. | Freeze paired resource limits and record usage/exhaustion; revise scope explicitly before scores, never change the scientific condition silently. | [Handoff, §3](../../docs/HANDOFF_2026-08-28.md) |
| Generated changes had not actually been applied. Apparent task saturation was therefore unreliable. | Audit actual executed inputs before diagnosing task difficulty. Validate generated examples; keep malformed or missing evidence out of training. | [Weekly report, §4.1 and §3.9](../../docs/WEEKLY_PROGRESS_2026-08-28.md) |
| Partial reward gave credit to unchanged output; small, concentrated evaluations could not establish general improvement. | Measure the unchanged baseline, preserve raw counts and report separate outcomes on common eligible rows. Do not import the old partial-reward formula. | [Handoff, §5](../../docs/HANDOFF_2026-08-28.md); [weekly report, §4.7–4.8](../../docs/WEEKLY_PROGRESS_2026-08-28.md) |
| A narrow action space and static assumptions limited the controller. Full evidence alone did not ensure it audited its inputs. | Let it propose data, generated examples, difficulty and methods from task one, inspect all permitted evidence, and explicitly reject an unreliable measurement. Do not impose old numerical curriculum gates. | [Weekly report, §4.8, §5.8–5.9](../../docs/WEEKLY_PROGRESS_2026-08-28.md) |
| Host-written policies and human corrections were mixed with controller-generated changes. The report later identified limited autonomous changes as well. | Mark common human starting advice separately from new agent revisions; preserve a human-intervention record. Measure whether revisions help on later tasks. | [Weekly report, §5.6 including §5.6.5](../../docs/WEEKLY_PROGRESS_2026-08-28.md); [handoff, §7](../../docs/HANDOFF_2026-08-28.md) |
| Files, runtime availability and handoffs were unreliable; written checks were not always used. | Store manifests and receipts in the durable run directory, verify hashes, and make the continuation instructions load the current contract. Runtime integration still needs independent tests. | [Handoff, §6 and §8/T3](../../docs/HANDOFF_2026-08-28.md) |

The evaluation skill adds a market-specific application: audit raw observations,
then distinguish signal, prediction, target and trading policy. Keep paired rows
and costs fixed. Better prediction is not automatically profitable trading;
repeatedly inspected periods are diagnostic, not untouched evidence. Its prior
Lighthouse feature identities, coefficients and results are NOT researcher input.

## A fair common starting point

`COMMON_RESEARCH_START.md` is a manually distilled, model-safe set of procedures.
All three arms get exactly the same text, frozen before their first scored task.
Reset means no NEW cross-task memory, not removal of common prior knowledge.
Archive and Learn retain only their own new permitted experience. Learn alone
has the experiment's separate self-revised guide. No arm gets these source docs.

The starting advice is human input and is reported as such. It is not evidence
that the current controller has already learned anything. A small number of
rounds, a longer guide or one improved market predictor does not establish that
the researcher generalizes better. GLM weight updates remain outside this pilot.

The starting heuristics may be challenged by evidence. Integrity, isolation,
the evaluation contract and budget remain fixed. Proposed training losses or
auxiliary diagnostics do not replace the common external scorer. No hard-coded
task-difficulty threshold or old operator menu is brought forward.

## Enforcement and remaining work

`research_context.py` freezes the common text in a new exclusive manifest and
returns byte-identical initial system instructions for Reset, Archive and Learn.
It refuses mismatches between the source text and the frozen hash. Its tests do
not prove an OS sandbox or that a model obeys a prompt.

The market researcher/coder worker is still being built. Before scored dispatch,
it MUST use this loader, bind its manifest hash to each request receipt, and
independently enforce the arm's evidence permissions. Do not count writing this
module as completing worker integration. No existing canary is rerun or relabeled.

Any later human change must record timestamp, author, reason, affected
code/instructions, before/after hashes and affected arms. A strategy hint to one
arm invalidates an autonomous paired comparison; preserve it as an intervention
instead of silently continuing the original claim. Infrastructure fixes can also
change behavior: test and record their effects, without claiming that the agent
invented the fix. Do not overwrite a scored arm's common initialization.
