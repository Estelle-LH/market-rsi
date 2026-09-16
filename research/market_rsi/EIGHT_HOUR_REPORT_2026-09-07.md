# Kalshi research-agent pilot — eight-hour report

**Final report — September 7, 2026, 13:20 UTC.**
Authorized window: 05:33–13:33 UTC / 01:33–09:33 New York.
Closed before the deadline because the research remains blocked. No          4
## The short version

**No scored comparison between the three research agents ran.** I did not
deliver the requested learning experiment. We cannot say the agent improved,
failed to improve, or can make money: those outcomes have not been measured.

We found useful problems in the historical data setup and built/tested more of
the runner. The main external blocker is missing evidence about the original
collector's timestamps and reconnect behavior. The full production experiment
also needs work; access alone would not make the current code ready.

The $200 budget is **not spent**. The recorded Tinker token estimate is
**$0.00367902**. Another **$0.40 is held for four completed sandbox checks whose
bills have not arrived**. Those holds are not charges or running jobs.

## What we are trying to test

The design uses the same GLM-5.3 researcher and subscribed Codex coding assistant
in all three conditions, with the same task order and resource limits:

| Researcher | What it can carry to the next task |
| --- | --- |
| Reset | The common starting instructions, but no new cross-task experience |
| Archive | Its own earlier experiment records |
| Learn | Its own records and an evidence-linked research guide it can revise |

Archive versus Reset tests whether access to experience helps. Learn versus
Archive tests whether revising a research guide adds anything. Better means
better independently measured results on later tasks, not better explanations.
This first pilot changes memory/instructions, **not the LLM's weights**.

The configured researcher is `zai-org/GLM-5.3:peft:262144` through Tinker. The
coding assistant is `gpt-6-astra`, medium effort, through the existing ChatGPT
login. No model switch or paid API fallback occurred in this window.

## What actually ran

| Work | Verified result | What it does not establish |
| --- | --- | --- |
| Two closed historical Kalshi hours | Both local file hashes match the preserved source hashes | Valid receipt clocks or uninterrupted capture |
| Small label diagnostic | 5,213 rows across 14 contracts / 7 games; 308 of 5,521 scheduled decisions were excluded | 5,213 independent training tasks, usable formal Train/Dev, or market performance |
| Historical metadata audit | 12 daily CSVs; 209 candidate MLB game entries / 418 contracts | 209 games with complete usable quotes or labels |
| Actual Harbor/E2B streaming fixture at 07:08 UTC | Three synthetic predictions returned; isolated execution and exact cleanup verified | A scored real-data baseline, or verification of the later revised general worker |
| Final offline software suite at 13:11 UTC | 579 tests passed in 78.798 seconds | Researcher learning or an actual three-arm experiment |
| Report evidence readback at 13:20 UTC | 23 checks passed, including hashes, counts, old fixture output and cleanup receipts | Original collector provenance or current cloud inventory |

The actual GLM text canary, subscribed Codex response, and first three E2B probes
ran **before 05:33 UTC**. They were reused as access evidence, not counted as new
experiments during these eight hours. The GLM canary used 197 input / 224 output
tokens. The coding response recorded 7,500 input / 394 output tokens.

There are no admitted real research tasks, scored learning rounds, learned guides,
weight updates, or final transfer scores. No real Test set was opened. No live
orders were placed.

## What we found in the data

1. **Splitting by file date would share games across Train and Dev.** The metadata
   audit found 44 game IDs on both sides of the proposed September 3 boundary.
   Every related contract and observation must stay with its whole game. This is
   a problem found before running a study, not evidence that a scored study leaked.
2. **A large row count is not a large independent sample.** The small diagnostic
   has 5,213 labeled rows but only seven games. The broader metadata has more
   candidate games, but listing a contract does not prove we recorded usable data.
3. **Some observations must remain unknown.** The diagnostic excluded 82
   continuity breaks, 108 quote gaps, 21 late entry endpoints, 17 late label
   endpoints and 80 capture-tail cases. They must not become zero-price-change
   labels. The saved independent readback reconciled 14,454 source endpoints.
4. **We still do not know exactly what the historical envelope timestamp means.**
   The ETL copies it into the normalized time field. That does not tell us whether
   it was recorded on receipt, or how reconnects/reset sequences were handled.
   Without that evidence, we cannot establish what information was available to
   the predictor at a decision time. This does not prove the archive is corrupt.

There are 12 days with all 24 hourly files listed, August 26–September 6. That is
file-level completeness, not continuous book coverage. Those previously examined
historical dates are also not untouched final-test evidence.

## What was built, and what remains incomplete

The code now covers separate arm histories, evidence-linked guide revisions,
permanent attempt IDs, one-response selection, receipt-checked coding and execution,
budget holds versus charges, failed-attempt accounting, and final numeric scoring
after every transfer submission is sealed. Missing results stay missing; the
report cannot silently remove difficult rows or replace failures with zero scores.

Late phase checks and bounded local model/coding/Harbor processes were added.
They preserve each experiment's original allowance. This is still **not a verified
hard deadline for the entire nested end-to-end job**. The revised general live
path has not had a positive live run. Independent source/task admission remains
unconditionally closed. A real baseline/task specification and executable fee/
latency contract are not frozen; final simulated net PnL is not connected.

The current taking simulator also refuses data with unresolved trade windows.
This diagnostic has 308 excluded decisions. We cannot obtain a credible profit
number by simply removing those cases after seeing where their future data is
missing. The next version needs an explicit treatment of unknown outcomes and
unclosed positions under the same rule for every method.

The coding assistant made these changes and fixtures as setup work outside the
experimental GLM researcher. They are not discoveries or self-improvements made
by GLM. The same frozen common
starting instructions were preserved. The market-evaluation skill influenced the
whole-game split, same-row comparisons, missing-result handling and the decision
not to claim statistical success from a small sample.

## Money and cleanup

| Budget item | Current amount / status |
| --- | --- |
| Combined incremental-provider hard cap | $200 |
| Tinker estimate from returned tokens | $0.00367902; invoice unavailable |
| Unresolved E2B holds | $0.40 total, four jobs at $0.10 each |
| Available after that estimate and holds | $199.59632098 |
| Learning allocation remaining | $120 |
| Protected final allocation remaining | $50 |
| Repair allocation remaining | $20 |
| Subscription/server economic allocation | Unknown; not claimed to be zero |

These are cumulative pilot figures, including setup before this eight-hour
window. Within the window, the ledger records one new E2B fixture dispatch at
07:08 UTC with a $0.10 hold, and no new Tinker inference. It does not show a $200
training bill. Provider invoices are incomplete, so an exact all-in charge cannot
be reported yet. No hold was released merely because the local process ended.

All four sandbox IDs have matching kill acknowledgments. The separate read-only
inventory at **13:19 UTC** showed zero E2B sandboxes and no matching local pilot
worker. Historical cleanup receipts alone would not establish current inventory.

At **13:19 UTC**, both exact Linode services were active/enabled with unchanged
PIDs and zero restarts. Polymarket US was writing actual fresh observations;
Kalshi tennis was writing fresh discovery records with zero active pairs, which
is healthy idle rather than quote coverage. Disk free was **78.792 GiB**. No
collector, source code, data rate, storage or production job was changed.

The installed versions were rechecked at 13:12 UTC: Tinker 0.25.0, Cookbook 0.5.3,
E2B 2.38.0 and Harbor 0.17.1. The frozen Codex binary/catalog hashes still match
its `gpt-6-astra` / medium / ChatGPT-login pin. This readback invoked neither the
CLI nor a provider.

## Next action

First obtain an authorized export of the **matching historical WebSocket
collector source/version, relevant configuration, receipt-clock definition and
connection/reconnect records** tied to these archives. No credentials are needed
in the export. The denied source SSH route was not retried or bypassed; the
different REST collector does not supply this proof.

The useful export is small; it need not include another copy of all market data:

- The code that wrote the historical `{t, m}` records, with its version/hash and
  evidence that this version produced the relevant August 26–September 6 files.
- The definition and units of `t`: when it was taken, which clock it used, and how
  it differs from any exchange timestamp inside `m`.
- The subscription, sequence, reconnect and fresh-snapshot handling, plus whatever
  run/session records were actually retained. If something was never recorded,
  say that explicitly rather than reconstructing an invented log.
- Relevant non-secret settings. Do not include keys, tokens, login files or
  unrelated server configuration. Preserve the original archives unchanged.

Then finish actual data/task admission and the remaining execution checks, run
one real baseline, and only then start the paired researchers. No extra budget
alone resolves these missing measurements. Later untouched games are needed for
the final test; the inspected history cannot be relabeled as unseen Test.

Research and paid dispatch are now closed, before the 13:33 UTC deadline. Only
the previously authorized health checks of the existing Linode feeds continue. This does not authorize
another experiment, additional spend, a venue switch or a new collector.

## Evidence and reproduction

- [Protocol](/Users/estelle/Documents/ChatGPT/self-evolving/research/market_rsi/PILOT_PROTOCOL_2026-09-07.md)
- [Historical data inventory](/Users/estelle/Documents/ChatGPT/self-evolving/research/market_rsi/HISTORICAL_DATA_INVENTORY_2026-09-07.md)
- [Read-only report audit](/Users/estelle/Documents/ChatGPT/self-evolving/research/market_rsi/report_evidence_audit.py)
- [Audit receipt](/Users/estelle/Documents/ChatGPT/self-evolving/research/market_rsi/artifacts/kalshi-research-glm53-20260907-01/report-evidence-audit-03.json)
- [Final offline test receipt](/Users/estelle/Documents/ChatGPT/self-evolving/research/market_rsi/artifacts/kalshi-research-glm53-20260907-01/final-offline-suite-01.json)
- [Original diagnostic readback](/Users/estelle/Documents/ChatGPT/self-evolving/research/market_rsi/artifacts/kalshi-research-glm53-20260907-01/labels-diagnostic-01/independent-readback-audit.json)
- [Current source archive](/Users/estelle/Documents/ChatGPT/self-evolving/research/market_rsi/artifacts/kalshi-research-glm53-20260907-01/phase-deadline-sources-01.json)
- [Permanent budget journal](/Users/estelle/Documents/ChatGPT/self-evolving/research/market_rsi/artifacts/kalshi-research-glm53-20260907-01/budget/journal.jsonl)

From the repository root, the read-only evidence audit is:

```sh
PYTHONPATH=research/market_rsi .venv/bin/python3 research/market_rsi/report_evidence_audit.py
```

The offline test command is:

```sh
PYTHONPATH=research/market_rsi .venv/bin/python3 -m unittest discover -s research/market_rsi/tests -q
```

Neither command makes provider calls or runs model-generated candidate code on
the Mac. The existing canaries must not be rerun under the same IDs. The revised
coding startup work consulted [official Codex documentation](https://learn.chatgpt.com/docs/non-interactive-mode);
the custom timing and isolation properties depend on our tests, not that page.
