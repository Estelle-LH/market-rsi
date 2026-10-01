# Local NFL in-game/PBP audit and `InGameWinProbabilityTrainDiagnostic-v0` design

Date: 2026-09-29  
Scope: independent local-file inspection and design only  
Empirical run performed: **no**  
Dev/Final opened: **no**  
Network/provider use: **none**

## Bottom line

The opened 2025 Train root contains enough locally resident game-state, PBP,
moneyline-fill, identity, and settlement evidence to build a first **historical
Train diagnostic**. The exact proposed fixed checkpoint exists for all 195
games. A latest strictly preceding fill with age at most 300 seconds exists for
194; `2025_05_TEN_ARI` fails with age `1088.157` seconds. The binary home-win
target is unavailable for the 40-40 tie `2025_04_GB_DAL`. Therefore the first
three-arm common population is **193 games**, while the denominator remains
195 with two named exclusion codes.

This data does **not** prove real-time feature availability. It was downloaded
retrospectively from a static nflverse GitHub release. The RDS receipts contain
source URL, identity, byte count, and SHA-256, but no provider-publish,
provider-update, ingestion, or local-receive timestamp. The play schema has
event clocks but no availability field. Current evidence therefore supports
only a historical, repeatedly inspected opened-Train diagnostic—not a live,
executable, promotion, or formal OOS claim.

## Files inspected directly

The main source is the non-cloud, non-temporary persistent root:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01`

Actual contents inspected, not merely README text:

| Path below the root | Format and direct observation |
| --- | --- |
| `cohort.csv`, `cohort.json` | 195 unique Train games on 42 schedule dates, 2025-09-04 through 2025-12-04, NFL weeks 1-14. |
| `pbp/<game>.rds` | 195 R serialized raw game objects, 7,906,669 bytes total. Every object contains `gameDetail`, a 57-column `plays` data frame, teams, final scoring fields, `scoringSummaries`, drives, and the complete play list. Direct total: 36,776 raw play rows. |
| `pbp/<game>.json` | 195 per-game RDS receipts with `game_id`, `game_date`, `event_slug`, URL, bytes, and SHA-256. |
| `plays/<game>.csv` | 195 derived four-column files: `game_id,play_id,play_type,time_utc`; 35,460 timed, typed, non-deleted plays. These files do not contain the state features needed by v0, so v0 must read the hash-bound RDS objects. |
| `catalog/<game>.json` and `.raw.json.gz` | 195 event/moneyline identities and immutable raw catalog captures. |
| `trades/<game>/trade_window.csv` | 195 fixed-window CSVs with side, token, condition, size, price, integer-second event timestamp, named outcome, outcome index, and transaction hash; 530,222 rows total. |
| `trades/<game>/manifest.json` and `pages/*.json.gz` | Complete per-game capture receipts and raw response pages. |
| `audit/per_game.json`, `manifest.json` | Source-support audit receipts. The root manifest still says `formal_train_admitted=false`; the later human opened-Train Discovery authorization is what permits diagnostic research and does not rewrite this historical receipt. |

Historical/tool references were also checked directly but are not the v0 main
population:

- 2024 root:
  `/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2024-refresh-20260921-01`.
  Its `play_by_play_2024.csv` has 49,492 rows, 285 games, 65 dates from
  2024-09-05 through 2025-02-09, and 372 columns; 284 games/64 dates have
  mapped trade captures. It explicitly records
  `historical_event_clock_only=true` and
  `provider_publish_or_local_receive_proven=false`.
- 2023 root:
  `/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2023-refresh-20260922-01`.
  Its PBP CSV has 49,665 rows, 285 games, and 63 dates from 2023-09-07 through
  2024-02-11. Only 237 games map to the archived on-chain source, 146 have
  in-game fills, and the existing 300-second all-game play coverage is only
  3.10%. It is reference evidence, not a substitute for the 2025 Train root.

## Source integrity and coverage reproduced independently

I re-read every 2025 receipt and every corresponding local file:

- all **195/195** RDS byte counts and SHA-256 values match their JSON receipt;
- all **195/195** trade-window SHA-256 values and row counts match their
  manifest;
- the 195 game IDs, dates, and event slugs agree with `cohort.csv`;
- all 195 RDS play frames have the same 57-column schema;
- `orderSequence` is monotone in all 195 game files;
- `timeOfDay` goes backwards at least once in six games, so causal truncation
  must use `orderSequence`, not event-clock sorting alone.

The 57 play columns contain `clockTime`, `timeOfDay`, `endClockTime`, and
`playClock`, but no column whose name indicates publish, receive, ingest,
available, or update time. At the proposed checkpoint, `endClockTime` is
present in only 179/195 games.

### Exact checkpoint replay

For each game, independently select the minimum `orderSequence` satisfying:

1. `quarter == 3`;
2. non-deleted play;
3. valid UTC `timeOfDay`;
4. parsed `clockTime <= 08:00`;
5. `down` in 1 through 4;
6. nonmissing `yardsToGo`, `yardLine`, and possession team.

Result: **195/195** games have exactly usable state. The selected clocks range
from 07:17 to 08:00 (median 07:41). State ranges are: home score differential
`[-28, 35]`, down counts `69/54/49/23`, yards-to-go `[1, 21]`, and
possession-relative yards to opponent goal `[1, 93]`; the home team possesses
the ball in 111/195 checkpoints. `goalToGo` is false in all 195 selected rows
and is therefore omitted rather than carried as a constant feature.

Pre-checkpoint score is reconstructed only from `scoringSummaries` whose
effective completion order—`max(playId order, patPlayId order)`—is strictly
less than the checkpoint order. This handles PAT/two-point completion and
produced a finite score for all 195 games. Final scoring-summary totals also
reconcile with game-detail final totals in all 195 games, but those final totals
are used only to form the label.

For the market snapshot, require integer trade timestamp strictly less than
`floor(decision_time_utc)`; this excludes unresolved same-second ordering. At
the most recent eligible second, convert every fill to home-win orientation
and take the size-weighted mean. Home nickname matches one named market outcome
in **195/195** games. The visitor nickname differs only for
`2025_13_LA_CAR` (`Rams` versus market `LAR`), which does not affect the unique
home-outcome match.

The strictly preceding-fill replay gives:

- age at most 60 seconds: 182/195;
- age at most 300 seconds: **194/195**;
- maximum age: `1088.157` seconds for `2025_05_TEN_ARI`;
- the 300-second population has one binary-target tie,
  `2025_04_GB_DAL` (home 40, visitor 40);
- exact modelable common population: **193 games, 42 dates, 14 weeks**;
- home-win/away-win labels within it: 107/86;
- normalized decision-time probabilities range from 0.003 to 0.999, with no
  exact endpoints.

Using the existing chronological date plan gives 106 eligible initial-fit
games and check blocks of 26, 16, 28, and 17 games. The four check blocks
contain 87 unique games on 20 schedule dates and seven NFL weeks.

## Availability and leakage assessment

### What is known by construction

The selected fields are pre-play state fields in the raw object: clock, down,
distance, yard line, possession, and score accumulated from strictly earlier
completed scoring entries. The decision market proxy uses only a strictly
earlier fill. This is sufficient for a historical causal reconstruction under
the source's event-clock semantics.

### What is not evidenced

There is no record of when nflverse/its upstream provider first published a
play, when a correction became visible, or when this machine could have
received it. `refresh.py` downloads the RDS with `curl` and writes a hash
receipt, but records no retrieval or receive time. The files were captured
after the games. Market rows are completed fills, not contemporaneous BBO
quotes, and likewise have no local-receive timestamp. Hence:

- v0 may be labelled **historical opened-Train diagnostic**;
- it may not be labelled real-time available, executable, or latency proven;
- a real-time claim is blocked until a future capture records immutable source
  sequence plus provider-publish and local-receive time and passes an observed
  latency/staleness audit.

### Columns and objects that must be denied to features

Nineteen of the 195 selected checkpoint rows are themselves scoring plays.
Because the decision time is the play's `timeOfDay`, all current-play result
fields must be excluded even if populated in the RDS. Deny at least:

- `yards`, `endYardLine`, `endClockTime`, `firstDown`, `isBigPlay`;
- `scoringPlay`, `scoringPlayType`, `scoringTeam.*`;
- `playDescription*`, `playStats`, `shortDescription`;
- `nextPlayType`, `nextPlayIsGoalToGo`, `latestPlay`;
- drive aggregates, full `drives`, and every later play;
- game-detail `homePoints*`, `visitorPoints*`, final phase, and weather fields
  not separately shown to be available at the checkpoint.

`playId` and `orderSequence` are audit keys only. `playType` is used neither as
a feature nor as an anchor requirement. The full scoring summary may be read
only inside a fail-closed helper that emits the last score strictly before the
anchor and never returns a future entry.

## Frozen minimal `InGameWinProbabilityTrainDiagnostic-v0`

This design changes the prediction task and must remain a separate experiment
namespace from every pregame scorecard.

### Population, row, and target

- Source: exact 195-game 2025 opened-Train root and receipt hashes listed
  below.
- One row per game at the fixed Q3 checkpoint defined above.
- Decision time: checkpoint `timeOfDay`; use only state logically preceding
  the current play.
- Market: latest strictly earlier fill-second, size-weighted after home
  orientation, maximum age **300 seconds inclusive**.
- Target: `1` iff final home points exceed final visitor points, `0` iff less.
- Full denominator stays 195. Frozen exclusions:
  `MARKET_STALE_GT_300S` for `2025_05_TEN_ARI` and
  `NON_BINARY_TIE_TARGET` for `2025_04_GB_DAL`. No other silent deletion.

### Three arms on exactly the same 193 rows

1. **Decision-time market:** the unmodified normalized home probability.
2. **Ordinary market model:** fixed L2 logistic regression using only the
   decision-time market logit.
3. **Market plus game state/PBP:** the same L2 logistic family and fitting
   procedure, adding only a frozen pre-play whitelist:
   home score differential, regulation seconds remaining, home-possession
   indicator, one-hot down 1-4, yards to go, and a
   home-oriented field-position value derived from possession and yards to the
   opponent goal. (`goalToGo` was inspected but is not included because it is
   constant false at this checkpoint in all 195 games.)

Freeze `regulation_seconds_remaining = 900 + quarter_clock_seconds`. Parse
`yardLine` into possession-relative yards to the opponent goal, then set
`home_field_position = possession_sign * (50 - yards_to_opponent_goal) / 50`,
where `possession_sign` is `+1` for home possession and `-1` otherwise.

For arms 2 and 3, use fit-only standardization for continuous columns and the
same fixed implementation: `LogisticRegression(penalty="l2", C=1.0,
solver="lbfgs", fit_intercept=True, max_iter=1000, tol=1e-10)`. Clip only
  inside logit/log-loss evaluation to `[1e-6, 1-1e-6]`; preserve and report raw
  probabilities. Reject nonfinite state, shape/schema drift, optimizer failure, or
row/mask mismatch before scoring. Do not tune features, `C`, anchor, staleness,
or exclusions after viewing scores.

### Chronology and scoring

- Keep the project-existing 42-date plan: first 22 schedule dates for the
  initial fit, followed by four five-date expanding checks. Refit both model
  arms once per fold on the identical prior rows; raw market is not fit.
- Primary metric: pooled **equal-game Brier** on the 87 unique check games.
- Also report equal-game log loss; calibration intercept/slope and a frozen
  reliability table; full 195/193 coverage; event/date/week breadth; every
  fold and every schedule-date paired delta.
- For paired candidate-minus-market and candidate-minus-ordinary inference,
  resample complete schedule dates and, separately, complete NFL weeks. In
  every draw recompute the pooled equal-game metric. Use 10,000 draws and seed
  `20260929`. Report that the week analysis has only seven check weeks and is a
  sensitivity, not strong precision evidence.
- A diagnostic KEEP may mean only that the state arm is worth another
  in-game Discovery round. It cannot mean promotion or formal OOS improvement.

The three arms must share the same game, timestamp, market probability,
target, fold, and row mask. The v0 scorer must reject any mismatch. **Do not
compare these scores numerically with the existing pregame scorecards**: the
decision time, available information, market entropy, and eligible-row task
are different.

## Can the first round run now?

**Data answer: yes for a historical diagnostic.** No external acquisition is
needed. The 2025 source supplies 193 valid paired rows, and the existing date
plan supplies 87 unique check games.

**Execution answer: not yet as a reviewed score.** The exact current blocker is
implementation, not source coverage:

1. There is no frozen three-arm `InGameWinProbabilityTrainDiagnostic-v0`
   runner or result schema/test suite yet. An untracked extraction helper was
   observed at
   `research/market_rsi/experiments/extract_nfl_ingame_checkpoint.R`, SHA-256
   `4aae86fc27f34cc0f7bd52ad93ff5f05f3aaae6cbf14f184714e3b7a8c9ad53f`,
   but it is not a scorer and is not treated as reviewed or frozen here.
2. The implementation must enforce the pre-play whitelist and strict
   order-based score truncation, with synthetic regressions where the current
   checkpoint play scores and where event clocks are nonmonotone.
3. It must bind all source/receipt hashes, materialize the 195-row exclusion
   ledger, prove the 193-row common mask, trap network/provider access and any
   Dev/Final path, and pass an independent pre-score review.

Those are small, bounded implementation gates. They do not justify new data
plumbing. Conversely, no amount of offline modeling can close the separate
real-time-availability blocker; only a future live receipt capture can.

## Evidence classification

- **General evaluation principles reused:** prior-only chronological fitting,
  identical paired rows and labels, proper probability scores, explicit
  availability boundaries, and complete-date/week grouped uncertainty.
- **Project choices frozen here:** Q3 first eligible `clockTime <= 08:00`
  anchor, 300-second fill staleness, feature whitelist, logistic specification,
  22 plus four-by-five date plan, clipping value, bootstrap count, and seed.
- **Unvalidated hypotheses:** contemporaneous state adds information beyond
  the in-game market; the effect transfers outside this 2025 NFL Train slice;
  the state would have been available at these event times in a live system;
  and any gain is economically executable.

No new literature or web search was performed because this audit was expressly
offline. The evaluation principles above are reused from the project's
existing reviewed methodology; the concrete parameters are not presented as
literature consensus.

## Hash ledger

- 2025 root `manifest.json`:
  `429a0ef100ade70f7e7b7f5862c39f42adffd7dcdaaddf35c73c88b60f80074f`.
- `cohort.csv`:
  `ba07b5535917f6ccfd4ddb5eadb53f6428b02bcc238595adac42894643d37885`.
- `cohort.json`:
  `49154e6a5a2780cc26c7384fc8d15f3c7275849e409054e8265581421e489a25`.
- `audit/per_game.json`:
  `99d2485e8b0b1a9eb3abf152e8a3df829d2f5b62ef9770f16f37d9f7cd5e668f`.
- `audit.py`:
  `e2a66e0458a9dc380a71e20f16e0af7edae74787fa3b08fe14966f228080c2e0`.
- `refresh.py`:
  `24f0a9b798fbb1fea83e3a7e3c650f2173a26a88cc4a23be6b5151335b1a395b`.
- `derive_plays.R`:
  `bad33f963af782e4722131359801d239b4663dfbf759b7f068c0a8287774f930`.
- Canonical verified 195-RDS receipt ledger:
  `37993ab26af997695e7ba595e76057edd60b5f02d83b980045d116a981f1ca20`.
  This is SHA-256 of the UTF-8 canonical JSON array in `cohort.csv` order,
  containing `bytes,event_slug,game_date,game_id,sha256,url`, with sorted keys
  and compact comma/colon separators. Each recorded RDS hash was independently
  recomputed from local bytes.
- Canonical verified 195-trade-window ledger:
  `d0fafcc72d8d876b22ea67689d9426629c4c16c2f406b35d3bd6abf2bdb57a48`.
  This is SHA-256 of the analogous canonical array in `cohort.csv` order of
  `game_id,rows,sha256`; all 530,222 local CSV rows reconcile with manifests.
- Sample RDS `pbp/2025_01_BAL_BUF.rds`:
  `405652c5d21ea30a83c856bccec16a9118a5f904a896105e9b0fde1737e84291`,
  exactly matching its receipt.
- Historical 2024 PBP CSV:
  `6ae564c2c49378ec531303292966caee596982278b9fcdad9c9dd0a0dc16bfa7`.
- Historical 2023 PBP CSV:
  `4aeca98ebe6357c5f1a13165533007964605d1f17bd54561937769b952c67613`.

This audit changed no state document, scorecard, result artifact, source file,
or experiment implementation.
