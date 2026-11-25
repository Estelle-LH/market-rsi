# Earnings research harness

This review package contains selected source, an offline check and aggregate experiment evidence. The original experiments ran with local sealed inputs and a fixed execution window. The GitHub copy is for reading and offline debugging.

## Last complete experiment

Candidate 222 passed proposal review. Evaluation windows 223–225 scored the same frozen candidate on all **25 training companies and 125 targets**. It scored **3.04 / 5**, against the incumbent's **3.18 / 5**. The incumbent was retained. This was a reused training panel.

The exact historical proposal source is `5c716ddb2cdae975e8f3280f845d23e2facde1d9`. The exact final evaluation source is `9022aeb400efa332ddeb8e2ec883f7ff9ab72651`. For each exported source excerpt, `source-manifest.json` names its original file and functions. The full original evaluation checkpoint is retained locally.

## Harness sequence

The Controller proposes a change. Author implements the proposal. Review checks the candidate before it can be frozen. A separate evaluation scores the frozen candidate. The loop records stage completion and failures so interrupted work can be distinguished from a completed result.

Run the offline check from this directory with `python3 smoke.py`. It uses the standard library.

## Current Q12 debug snapshot

Run 239 completed Controller and Author. The Author produced an H-only candidate with the forecasting code held fixed. Review stopped before its first model request and before it initialized the candidate's test case. The candidate remained unfrozen and the scoring panel did not start.

Read `source/earnings_population_services.py` at `Services.review`, then follow `declared_test` in `source/earnings_population_coevolution.py` and `slot_resolution` and `child_breadth` in `source/earnings_population_layered.py`. The generic rule expects a generation-9 breadth-policy field. The historical Root0 record enters Q12 through its own authorized contract for the twelfth question. Review reached the generic validator before using that contract.

`review-declaration.patch` projects the test description from the exact Q12 contract. Other origins still take the generic route. The offline check reproduces the original exception, tests the proposed declaration and checks that a forged origin and the generic breadth violation still fail. The Q12 contract authenticator uses a synthetic stand-in in this public test. The patch has no live Review result yet.
