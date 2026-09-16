# Predict without seeing later observations

## Implemented

11:46 UTC update: final_stage.py connects sealed transfer submissions to numeric
final evaluation without new research/code generation or final feedback into
StudyState. The source is now pinned before the study starts. 550 offline tests
pass; all new final executions are fabricated. No real task or hidden set was
opened. Final failure/PnL handling and enforced whole-step timing remain unfinished,
and independent live admission stays closed. See the latest STATUS/RUNBOOK entries.

11:23 UTC update: 529 offline tests pass. The general GLM and Harbor owners now
have bounded trusted subprocesses; cloud cancellation/cleanup remains separately
verified. Completed candidate failures can receive an append-only runner review
under unchanged source and limits, without erasing the failure or giving human
advice to the models. See STATUS.md and RUNBOOK_2026-09-07.md for current sources
and evidence. Source-changing repair, verified whole-step timing and the final
evaluation worker remain unfinished. General live admission is still closed;
no real study or new scored market result is implied by these software tests.

10:12 UTC update: study_runner.py now connects the owned study state to researcher,
coder, development success/failure receipt producers and selection worker. A
complete fake-provider three-arm loop passes with learning/transfer barriers and
no redispatch during pending recovery. 480 offline tests pass. No real study has
been instantiated, no market result measured and no source admission granted.
It does not expose hidden data or implement the final scorer. End-to-end wall
enforcement and reviewed-failure resumption remain open gates.

The revised general runner preserves candidate-only stderr through
diagnostic_channel.py; root evaluator tracebacks remain private. This revised
path is offline-tested but not cloud-verified. The old actual cloud canary and
its original stderr-discarding channel remain unchanged, not retroactively fixed.

08:39 UTC update: study_state.py now provides durable own-arm memory, pending-step
recovery and learning/transfer ordering barriers. 384 offline tests pass. It makes
no predictor choice, verifies no arbitrary completion's factual contents, and
does not open hidden data. Complete the trusted producer that binds actual worker/
execution/Dev receipts into these records before any live loop. All new guide and
record tests are fabricated; no researcher-learning result is claimed.

08:24 UTC update: development_harbor.py now provides general development execution
composition for both modes, runtime-library checks and independent protocol/output
read-back. The installed Harbor constructor selects the actual custom classes in
offline tests; all provider lifecycle tests are mocked. No general cloud trial or
actual inspection trial is claimed. Live entry/start/setup/run all require the
still-unimplemented independent admission function, which unconditionally fails.
It cannot be enabled by a caller's fixture flag or unconditional callback. The
suite is357. Source snapshot: development-harbor-sources-01.json. Full study-state/
experience/transfer and source/task/deadline admission remain incomplete.

08:10 UTC update: worker_receipts.py now ties each handoff to actual completed
researcher/coder job files, not a caller-supplied response string alone. It checks
the terminal budget receipt, source/request ownership, exact coder event/body and
usage, then revalidates files before handoff. trial_inputs.py composes those jobs
with exact catalogued development data, stripping Dev labels for prediction and
allowing only the separate inspection path to see them. These checks are not
source-data certification or a production dispatch gate. The new root-side
sandbox_inspection_runner.py is still untested in cloud. Local mocked composition
and receipt checks bring the suite to332; no market score or paid call occurred.

07:53 UTC update: inspection_stream.py implements the separate inspection protocol.
It binds exact catalogued Train/Dev artifact bytes to the original research/coder
packets and owned common context. Only this mode exposes complete permitted Dev
rows/labels. Bad/missing values remain diagnostic evidence; they are not silently
cleaned or admitted for training. Its bounded output is candidate-authored, never
an authoritative score. The new inspection_candidate_server.py copies the tested
unprivileged/network-namespace/resource checks, but its actual cloud composition
is still untested/unwired. A human-written local transport fixture and boundary
tests pass; the complete offline suite is 294. No new model or sandbox call.

07:10 UTC update: the root-private sequential path now has an actual Harbor/E2B
integration receipt at harbor-stream-integration-01. The project-local
BoundedMarketE2B overrides the stock create/build/retry/lifetime behavior: one
creation, existing exact template, 180-second TTL, no Internet, $0.10 reserved
before dispatch. Installed Harbor/E2B packages are unchanged. Three toy predictions
were checked independently, all nine pre-import isolation checks passed, and the
exact sandbox was killed; the subsequent provider inventory was empty.

sandbox_prediction_runner.py keeps all future feature rows under root/0700,
runs candidate code at UID65534 in a separate network namespace, and exports
only committed prediction/protocol receipts to the host. No evaluation labels
were uploaded. The live entry point currently accepts ONLY this fixed human-made
fixture; it is not a general real-data admission gate. The full suite is now 229
offline tests. This supersedes older statements below that no cloud integration
has run, but does not establish dataset validity or any market research score.

The new coder_worker.py builds a code request from the existing common/owned
research request and the first admitted researcher response. It checks packet
integrity, keeps the proposal's action, saves the response as text, validates
one terminal message plus subscription usage and never executes returned source
on the Mac. gpt-6-astra/medium and its CLI/catalog are explicitly pinned in the
permanent run artifacts before scored work. Model weights/backend immutability
and the prior canary's default model are not established by this pin.

Its CLI wrapper keeps the earlier no-tools/isolated-directory profile, forces
ChatGPT authentication, and bounds wall/input/output sizes. These are not an exact
model-token cap or proof of one internal provider HTTP request. Context overflow
fails rather than being silently truncated. Live task admission is not connected;
the outer worker must verify actual source provenance, the proposal's recorded
origin, exact active claims, resources and deadline independently before dispatch.
The complete suite now has 213 offline tests; none are market research scores.

prediction_stream.py provides the trusted sequential fit/predict protocol,
bounded persistent subprocess transport and exclusive durable prediction log.
prediction_candidate_server.py is the unprivileged candidate endpoint. It checks
the expected Linux UID, network namespace, no-new-privileges and absent paid
keys before importing candidate code. Code import/execution is only permitted
inside E2B through the trusted launcher; local tests use human-written fixtures.

The parent holds the evaluation sequence. It sends Train once, then sends one
feature row, validates and durably records the prediction, then sends the next.
Whole evaluation files, labels and future endpoints never enter candidate input.
The protocol preserves opaque identities, chronology and the frozen feature
schema. It refuses silent truncation/subsampling when a request is too large.

This is NOT the complete scientific worker or an authorization to score data.
Twenty-one new offline tests pass; the full project suite is 171 tests including
older fixtures. No cloud run was launched to test these new modules.

## Required outer-worker integration

1. Finish the real GLM request/response worker using common_system_prompt and
   bind the unchanged common initialization to each arm's request. Isolate each
   arm's permitted evidence. Load the pinned subscribed Codex model before scoring.
   worker_receipts.py and trial_inputs.py now bind completed jobs and exact
   catalogued inputs. Connect these readers to the outer supervisor's own frozen
   task/history/runtime rather than accepting candidate-selected receipt paths.
   The separate inspect(train, dev, feature_names) protocol is now implemented;
   wire it to the real isolated outer driver so diagnostic proposals get only
   permitted Train/Dev evidence and never hidden Test. Its response is untrusted.
2. Require independently verified market data and a frozen task/scorer/budget
   contract before a paid market trial. This stream validates declared rows;
   it cannot establish original collector clock or game-mapping provenance.
3. In a fresh runner-owned E2B sandbox, place the complete Train/evaluation
   feature inputs and trusted parent under a root-owned 0700 directory. Put
   only the candidate and its protocol wrapper in a root-owned read-only public
   directory. Do not upload evaluation labels at all. The wrapper's visibility
   depends on these OS permissions, not just a prompt or this Python protocol.
4. Run the trusted parent as root and the child through unshare --net / setpriv
   UID 65534, no groups, no-new-privileges, matching the earlier passed preflight.
   Use the frozen process/resource caps, same for every arm. The current server
   limits (120 CPU seconds, 512 MiB address space, bounded files/processes) are
   infrastructure defaults, not yet a declared scientific experiment condition.
5. Use PredictionJournal.commit before releasing each next feature. Persist
   bounded protocol events even on failure. The prospective general driver now
   saves candidate-only stderr with the endpoint's 10 MiB hard file limit; the
   earlier actual cloud fixture discarded it. Do not claim that a new log exists
   for that old run or that the revised channel has already passed cloud testing.
6. Always destroy the exact E2B sandbox in finally and reconcile actual provider
   usage. A malicious child may create another process group; local killpg is
   not a substitute for whole-sandbox cleanup. Never retry for a better score.
7. Independently score complete predictions outside the candidate sandbox.
   Commit all final submissions/researcher states before any hidden scoring;
   do not return hidden outcomes or later observations to the researchers.

The protocol's toy fixtures demonstrate order, data projection, durable commits,
limits and failure handling. They do not prove production filesystem isolation,
dataset validity, profitable predictions or researcher improvement.
