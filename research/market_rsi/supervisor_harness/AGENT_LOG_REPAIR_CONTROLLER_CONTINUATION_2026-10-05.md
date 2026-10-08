# Controller continuation integration recommendation — 2026-10-05

Registered scope: operational preparation only; own this new log. No scientific candidate selection before independently verified D1 feedback, no source writes, fits, provider/network acquisition, protected reads or commits. Existing four-hour repair authority15:27:11–19:27:11UTC/max6 selected attempts/24 fits/provider0; selection cutoff19:12:11UTC. This proposal does not extend the expired eight-hour window or any closed cap.

## 15:46:34–15:47:42 UTC — actual source/transport observations

Read actual recorder continuous_discovery_batch.py (SHA1b3065ea2990e886ff05869d5c6afd39bc0e80ebb053436f51fd9d9cee0d148c), worker opened_train_discovery_worker.py (SHA512176a1cb84ad81383e7e890abf9b2058ee66e7a8a643e3549fd5ec4c0db360), accepted final memoryd7bd0a67 and ranked pool45255f60. Current source HEAD30a690869f26656d18e222fedfcb88ffff6abcc2, adapterf62a5459a8e3c78bcdd7810e25291d1ef164ccc2d41f876fa37fb166f9dcc8bc frozen under review. No new science score inspected or invented.

Observed integration gap: record_result_review and record_research_credit precede mark_controller_feedback_ready. The latter seals a durable hash-bound packet and moves the branch to terminal; it does not call a model or acknowledge consumption. _evidence_packet_v2 contains result/scorecard/review/credit/source/memory hashes and pool hints, but not numerical aggregate metrics, timeblocks, intervals or correction diagnostics. Passing only this packet to a model does not deliver the evidence required for scientific feedback use.

Actual worker.execute already reserves before childspawn, forbids relaunch after claim, validates source/runtime/memory, uses fixedmodule CLI and writes a truthful outcome. Its twelve-fit cap is LOCAL to the current pilot; it cannot enforce the NEW shared six-attempt/24-fit budget acrossfreshsubpilots by itself. Sharedouterauthority must therefore be checked/reserved before every implementationselection and workercall; no worker/scorer rewrite required for this first consumer.

Read permanent transport-probe/response.json SHAffccb2839051a77434bcc1d29c77a696b3dd612d99c7e1172cc01aca6a098035 and response-schema.json. Actual stored response acknowledges a transportprobe, requestedgpt-6.1-sol/servingsnapshotunknown/scientific_decision_madefalse. Supervisor reports14549input/53output tokens and ChatGPTlogin; this is accountusage, not a zero-cost assertion. No scientific modelupgrade/matchedAstra claim. CLI localhelp documents stdin, --output-schema, --json, --output-last-message, --ephemeral and --ignore-user-config. It does not document a no-tools flag: exact already-tested command/config must be supplied and frozen by Supervisor, not guessed here. Observed zero toolcalls is not hard permission enforcement; reject/log any unintendedtool event and report trusted-host limits rather than claiming OS/network/protected-data isolation.

Read research-progress and OpenAI Docs skills. Research-progress requires actualfeedback->choice->execution/evidence and honest totaloverhead/intervention; memory/negativefinding reuse is a legitimate mechanism to test, not alreadyproven capacitygain. OpenAI Docs normally requests official externalretrieval first, but the user's explicit closed-retrieval boundary takes precedence: no websearch performed. Only actual localhelp/storedtransport evidence used, no officialdocumentation claim. One read failed because this newlyregistered log did not yetexist; creating only thisfile is authorized, no source failure.

## Smallest concrete increment: an H feedback consumer, not a new R policy

Recommended implementation allowlist (proposal only):

- research/market_rsi/supervisor_harness/account_controller_feedback_consumer.py
- research/market_rsi/supervisor_harness/test_account_controller_feedback_consumer.py

One H component, target<=160 productionlines using existing hash/save/locking conventions; >200lines or>2productionmodules requires split or independent inseparability review. Do not edit recorder/worker/scorer/oldcontracts or add a rewardservice. Keep C/K/M/runtime/data/permissions and current researcherpolicy fixed except the explicitly recorded Controller transport/config identity. Native exactservingversion unknown and requestedCLI alias known must both be recorded; this route activation is not an inferred scientificmodelupgrade. The separately proposed R eligibilityfilter is not needed to deliver this consumer.

### Exact input and evidence boundary

Supervisor freezes one controller_feedback_input_v1 packet per acceptedfeedback identity. It contains:

- batch/attempt/feedbackpacket path+SHA; accepted independentreview path+SHA, scorecard+predictionmanifest commitments, source/runtime/actualresearchparent/incumbent identities;
- ACTUAL independently verified aggregate Brier/logloss/calibration, four fit/check counts and block metrics/paired deltas, date/week intervals, available correctionenergy/alignment and coverage/exclusion summaries; null metrics on executionfailure, never synthetic or unreviewed substitutions;
- immutable current Controller memory/history manifest+SHA, ranked globalpool+SHA, consumedC2 fact and exact relevant priorfinding references including validnegative evidence; no closed Dev/Final/external text or rawlabel expansion required;
- current sharedouterauthority+SHA: selected/reserved/actualfits, occupiedslots, observedclock, harddeadline19:27:11/selectioncutoff19:12:11 and remaining ceiling. Do not copy stale remainingattempts from a terminated singleton hint as the outerbudget;
- authorship/intervention ledger and observed componentwalltimes for proposal/implementation/tests/review/execution/feedback; unknown tokens/cost stay unknown;
- exact frozen account-backed transport executable/command/config/requestedmodel identity, structuredoutput schema, boundedtransporttimeout<=remainingdeadline and no automatic fallback/resample.

Trigger only after exact packet independently accepted and recorder.mark_controller_feedback_ready succeeds. Verify current journal branch has the SAME review/feedback/hash/source and required credit; equal identity is idempotent, changed evidence is a new rejected event, not an overwrite. Failedexecution may still receive independently verified factualfeedback; do not present it as validperformance evidence. External sources remain closed: current scientific claim is autonomous experimentation using existing authorized information only.

### Structured next decision, not executable model instructions

Use strictadditionalProperties=false schema with fields: schema, consumed_feedback_sha256, action(propose_candidate/stop_in_scope/request_closed_authority), actual_parent_sha256, comparison_incumbent_sha256, evidence_used[{artifact_sha256,finding,choice_consequence}], hypothesis, recipe(non-executable fullnumericaldescription/features/training/expectedsupport-refutation), requested_resources(fits<=4/seconds<=900/threads1/RSS<=1GiB/provider0), global_pool(two-or-three evidence/methoddiverse branchrecords), retained_findings, stopped_exact_recipes, attribution(changeaxis/component/authorship/limits), requested_model and servingsnapshotunknown. No shellcommand, credential, URL, changedscorer, permissiongrant or arbitrarysourcepath is accepted from this response.

The Controller chooses scientificmethod only after actual feedback; do not populate this response with a predetermined D2/D3 model. Its evidence_used must cite at least one supplied verifiedfinding and state what it changed. Merely repeating a citation is not sufficient: independentreview checks a concrete consequence in actualparent/hypothesis/representation/training/stop/repair choice. Existing negativearchive remains accessible and C2consumption neverresets.

### Durable once-claim and acknowledgement

Use the permanent rootartifacts/market-rsi-repair-discovery-20261005-01/controller-consumption/<feedback_sha>/; read-only externalinput hashes and exclusive-create files under one fcntl lock. Before CLIspawn, persist claim.json with feedback/input/schema/transport/source hashes and trustedclaimID; fsync. Capture original stdin commitment, CLIcommand, start/end/PID, rawJSONL/stderr and rawfinalresponse. Validate output once; save decision.json and ack.json binding SAME feedback/input/decisionhash, even when action is stop/requestclosedauthority. A schema-valid response is not source/run approval.

Crash before claim leaves no call and may proceed once. Crash after claim with uncertain process/result does NOT relaunch the CLI automatically: inspect PID/processreceipt/rawresponse, recover valid completed output once, or persist uncertain/failedcall and return boundedrecovery to Supervisor. Crash after decision beforeack reconstructsack only after originalhash validation, not a newmodelcall. Existingack returns the same decision without recalling. Malformed/truncated/timeout/unauthorizedresponse is preserved, no hidden repairprompt/retry/modelroutefallback. A servicecapacityerror is operational, not scientificrefutation; failurememory records it separately.

### Connect to existing implementation/review/worker handoffs

After validateddecision, the existing trusted Supervisor handoff freezes a new bounded C contract and exact independentwritepaths; it reserves one NEW outerattempt at selection (including implementationfailures), registers implementer/reviewer, and reuses existing sourcecheckpoint/test/review path. Author who proposed hypothesis versus sourceimplementation/repair/continuation must be recorded separately; Supervisor boundary fixes remain interventions.

An implementation-ready source/spec request is never accepted merely because a model producedJSON. Only the actual independent sourceverdict plus fixedsource/runtime/memory and sharedouterreservation allow the handoff to call existing worker.execute. Any root-owned integration/commit steps and manual repair interventions remain in totaloverhead. The consumer must not eval/exec modeltext, modify incumbent, choose the algorithm for the Controller or bypass review. Proposed consumer ends at a verified handoff; until the implementation/review/execution handoff actually proceeds without a new human roundinstruction, it is NOT a completed automaticexperimentloop.

Where current native Supervisor/agent handoffs are not callable from Python, expose the durable decision+readyevent to that EXISTING authorized actor rather than invent an unavailable autonomous API. This must cause a real actor invocation/ack, not just another queuefile. Subsequent trustedreviewacceptance triggers actualworker.execute once under sharedbudget; root verifies it happened. Splitting consumer and executioncontinuation checkpoints keeps causality and code small. No generic orchestration rewrite is a prerequisite.

### Failure/recovery and acceptance checks

Focused synthetic/matched checks: unreviewed or hash-driftedfeedback cannot spawn; numericpacket agrees independently acceptedscorecard; malformedresponse never reachesimplementation; duplicate/parallel samepacket causes oneCLIcall/oneack; processunknown timeout does not resample; recover afterclaim/response/review/ack without lostfeedback; newchildclaim cannot relaunch; sharedsubpilots cannot exceed6selected/24reserved+actualfitaccounting or2livechildren; stopselection at19:12:11 and kill/stop activeboundedjobs by19:27:11; source/model/permissions/scorer drift rejects. Spy-handlers alone earnL1/L2, not realresearchsuccess.

Measured next milestone requires BOTH: (1) actual reviewedD1 feedback automatically reaches the actual configuredController, producing a schema-validated evidence-cited newdecision; (2) its new independentlyadmitted predictioncandidate is automatically dispatched and completes an actual fit/87-row scorecard or truthfullypreserved boundedfailure. Record which exact priorfinding changed thatchoice and review whether reuse was scientifically appropriate. Queue creation, transportack, code or signalanalysis alone do notpass. D1 and later resultmetrics remain unknown until verified; no model chosen here.

Measure feedback-ready->CLI-start/end/ack->implementationdispatch->sourcefreeze/review->workerstart/result latency, CLI reportedtokens, all componentwalltime/failures/repetitions and human/Supervisor interventions. Report predictor score, H continuation capability and unproven researcherimprovement separately. A one-off usefulfindingreuse establishes feedback adaptation/evidenceuse, not superiority over equal-budget fixedresearchflow; that later comparison includes implementation/reviewcost, memory, repetition, interventions and independenttrajectories. No forced R coderewrite or external-literature claim.

Current disposition: concrete H integration recommendation delivered; no source/tests/fit/network/agent spawn performed. Await independentlyverified D1 numericalfeedback for scientificselection; existing threepriorities are not preselected nextexperiments.

## 2026-10-05 18:28:17–18:30:45 UTC — scoped continuation-contract repair

New registered `repair_controller_continuation_20261005` role, operational H only. Read complete scope `COEVO_FEEDBACK_CONTINUATION_SCOPE_2026-10-05-v3.json` SHA `63b2746021625c40198815439fcde4e6fe0b9f878f86ed05a3b6249bec248f58`, complete original255-line consumer and414-line tests, and actual original D4 transaction review `8972c6ae1b6848e0edf5b7fb495198cec3de212b17bced1598699636fbb8743b`. The original account Controller returned voluntary `stop_in_scope` despite5selected/20fits/one open slot; transaction integrity passed, but continuation and batch completion were independently denied. That is an operational policy mismatch, not permission to rewrite the response or choose D5.

Read independent scope PASS `fd4594f73da60245fbad8e0d144fad413240be169151f7635c58ae5a4c320773` before edits. Actual clock18:29:39UTC; root's relative18:31 label was ahead of observed clock and is not used as an execution timestamp. New scope permits only the existing consumer/test and this log. OpenAI Docs normally requires external lookup for prompt work; explicit closed-retrieval authorization prevails, so no external sources were fetched or claimed. Used exact local source and frozen scope; no API key/provider operation.

Exactly three production edit locations: compiled SCOPE_SHA63b27460; remove voluntary-stop enum while retaining typed propose_candidate/request_closed_authority; strengthen prompt to continue within still-open budget using a reasonable distinct first small prediction hypothesis without prior gains, not stop because of negative scores/overhead, preserve open methods/no forced R/scorer change, and use closed-authority requests only for genuinely necessary specific operations without granting authority. No validator, numerical preparation, budget, claim/fsync, CLI, timeout/cleanup, transport I/O or original recovery algorithm changed. Production diff3added/3removed, length255 unchanged; no new module.

Tests: updated typed enum assertion, actual fakePopen prompt-guidance assertions, plus two focused synthetic regressions. Voluntary stop rejected by service-shaped typed schema and local validator; original invalid completion/response/failure retained, no ack and no same-key resample. Proposal and closed-authority request remain typed/bounded valid without changing synthetic authority. These validate mechanics, not scientific necessity of a hypothetical closed request or permission to execute it; Supervisor/independent review owns that decision.

Exact pinned commands, cwd `/Users/estelle/Developer/market-rsi/research/market_rsi`, Python `-B`, hashseed0/all numeric thread limits1:

`/Users/estelle/Library/Application Support/MarketRSI/runtimes/ds-py312-20260912-01/bin/python -B -m unittest supervisor_harness.test_account_controller_feedback_consumer -v`:25 PASS,0.274s.

Same runtime/environment: `-m unittest supervisor_harness.test_account_controller_feedback_consumer supervisor_harness.test_opened_train_discovery_worker -v`:59 PASS,0.741s. This is existing57 relevant checks plus2 new checks;34 worker-suite checks include25 recorder checks, not another separate25 unique tests. No test errors this repair. Test file450 lines, diff37added/1removed.

Frozen consumer SHA `b0c4c7a28f2eeb333587b9a53faa230a3b751d707433c0dc3b6f4d3e78e0e68e`; test SHA `304801701b69dd37912c903b4e5a46fd7ea36b1d55b12bd89535223df7ea455a`. Exact combined `git diff` for these two files SHA `faab4cbc822112ff5b3a98c1b0d224c3bc13a87992bcd941bf2a0b960232fade`. Original consumer d6b72f/sourceGit967107b8 and original D4 call artifacts remain recoverable/untouched; current changed-source guard deliberately does not turn old onceclaim into a retry. No old input/response/authority/pool/score/candidate/helper/source commit changed by this role; no model invocation, real Train fit, protected read, network, commit or scientific D5 choice.

Final-source independent review/commit and any separately authorized fresh replacement invocation belong to root. Original6/24/time caps unchanged, actual remaining authority must be rechecked. This is human/Supervisor-directed H repair and an additional human fresh-call intervention, not autonomous researcher R evolution, predictive improvement, reduced overhead, or fixed-flow superiority. Final source/test bytes handed off stable; no further edit pending.
