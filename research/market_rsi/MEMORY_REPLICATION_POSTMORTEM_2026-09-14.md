# Archive-memory replication postmortem

## Status

`memory-replication-20260914-02` completed all eight controller rounds and all
eight rolling Dev evaluations. It completed 19 of the 20 frozen Final sessions.
The run is incomplete and does not support the preregistered primary claim.

The last source, `2026-09-14T09`, was already truncated at the frozen
21,909,504-byte size. A read-only source check reported a premature Zstandard
end and an unfinished JSON string at line 245,591. The runner rejected the
source, generated no score for it, did not substitute another hour and did not
retry.

## Dev result

Archive had lower MSE than fresh on five of eight Dev sessions. Equal-session
Dev MSE was:

- Archive: `2.3285275526e-05`
- Fresh: `2.4004943995e-05`
- Fixed baseline: `2.5275436247e-05`

## Preserved partial Final result

These 19-session figures are descriptive only:

- Equal-session MSE: archive `0.001220479489`, fresh `0.001143843492`, baseline
  `0.001137622520`.
- Archive beat fresh on 4/19 sessions.
- Archive was about 6.7% worse than fresh on the equal-session metric.
- Fresh was about 0.55% worse than baseline.
- Row-weighted MSE: archive `0.003847689587`, fresh `0.003926859915`, baseline
  `0.003860686249`.

Equal-session and row-weighted rankings disagree because a few large sessions
dominate the row-weighted result. No IID confidence claim is valid.

## Cost

- Archive controller: `$5.749798446`
- Fresh controller: `$1.593045306`
- Replacement total: `$7.342843752`

Complete raw archive access cost about 3.6 times as much as fresh sessions.

## What we learned

Full raw history looked better on rolling Dev but did not carry that advantage
to the 19 valid Final sessions. It also cost materially more. This run therefore
does not support the claim that giving the controller its complete raw archive
improves out-of-sample prediction.

Before another paid experiment, every sealed source must receive a structural
integrity check that reads no target statistics and reveals no market content.
A later preregistered comparison should test full raw history against a bounded,
provenance-preserving memory summary. The broken source cannot be replaced in
this run.
