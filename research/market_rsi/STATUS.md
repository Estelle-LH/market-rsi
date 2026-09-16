# Market RSI — current status

## 当前：三轮 archive-memory vs fresh pilot 完成，archive 小幅胜出；下一轮要扩大 final session

新的实验已完整跑完。代码发布在自己的私有 GitHub：`f7c300f` /
`pm-memory-pilot-v0.1.0`，运行目录为 `artifacts/memory-pilot-20260913-01`。
输入数据为 Aug26-Aug28 三个训练小时，合计 1,460,664 个已核对样本；Dev 和 final
日期由 runner 预先冻结，controller 没有提前看到 final。

三轮 Dev 结果：Round 1 三者打平；Round 2 fresh/no-memory 最好，archive 也优于
baseline；Round 3 archive 最好。最终 holdout 使用 Sep10/Sep11/Sep12 三个小时，
结果为 archive `5.756171720848301e-05`、fresh/no-memory `5.955168559442658e-05`、
baseline `5.9648811417630666e-05`。Archive 比 baseline 低 3.50% MSE，比 fresh
低 3.34% MSE。

实际 GLM 计量花费约 `$1.97057691`：archive `$1.407675186`，fresh `$0.562901724`。
硬上限约 `$50.64` 没有接近用满。Source hash 未变，运行正常完成。这个结果支持
“archive memory 可能帮助研究 agent 逐轮改进”的小样本证据；它不是正式 >=20 session
OOS promotion，也没有测 PnL。

9月14日补做 post-hoc 诊断：fresh/no-memory 在 Round 2 其实找到过和 archive 最终
几乎一样的复杂特征组合，但最后没有保留；archive 的优势更像是“记住并延续有效思路”，
不是发现了 fresh 完全没见过的东西。诊断文件在
[Memory pilot postmortem](MEMORY_PILOT_POSTMORTEM_2026-09-14.md)。下一轮应至少用
20个 untouched final sessions，重点看 per-session delta、positive-market breadth
和 concentration，而不是只看一个平均 MSE。

## 当前：真实比较完成，平均MSE下降21.1%，但结果集中

一次拟合、四个较晚小时文件全部完成，三个更好、一个更差。MSE从0.0001141124
降到0.0000900582，RMSE从106.82降到94.90价格基点。检查共1,110,248个配对行，
不是独立案例数。90.2%的净改善来自9月9日；不能只看平均值就说稳定有效。

程序、模型、文件指纹和逐行评分复算一致；所有任务和锁已清理，无后台实验。
没有新增Tinker调用，原$200计量$41.25、可用$151.59不变。代码已发布33af87a。
这是用户同意的初步历史诊断，不是正式RSI、独立最终测试或盈利证明；旧采集日志
限制不改。完整结果和不足见[本次比较结果](PRELIMINARY_RESULT_2026-09-13.md)。
下文为历史状态，里面的“等待答复”和“运行中”均已结束。

## 最新：真实样本生成已跑通；等待确认初步模型比较的范围

89秒处理controller选定的一个真实文件，得到1,051,922个合法特征—答案对，
覆盖1,078个有可用样本的token。92.25%的答案为零变化；这些行有重叠，不是独立样本。
本小时不变预测的MSE为0.0000215821、RMSE为46.46价格基点；还没有候选模型结果。

转换代码已发布到私有GitHub，样本统计核对通过，相关进程和锁已清理。没有新增Tinker花费。
下一步是真实baseline/candidate比较。原方案仍要求缺失的采集日志才允许拟合，已询问是否
允许另做明确标为初步历史诊断的比较，不改原正式方案。此时尚未收到答复，未开训。
见[真实结果与范围](TYPED_RAW_RESULT_2026-09-13.md)。

## 最新：新样本接口已发布，controller交出了明确参数；还未训练

v1.5.0已推到自己的私有GitHub。188项测试和两次免费真实工具链检查通过。
GLM续接8分04秒结束，15次回复、17次工具调用，实际计量$1.89。它自己选了
price_change消息的直接买卖价，明确窗口、间隔和答案规则；两项检查通过，首次方案保留。
5次提交错误均记录并在同一会话内修正，没有换方案挑结果。

还没完成的是原始文件到这些样本的转换程序；它请求的Aug21T12单文件检查尚未执行。
下一步接好并测试转换程序，不再付费重复征求同一份方案。没有新MSE或模型提升。
原$200累计计量$41.25，可用$151.59；差额包括旧不确定费用上限和预留，不是都花掉了。
当前没有实验后台进程，E2B活跃数0。见[具体方案、费用与下一步](SAMPLE_CONTRACT_2026-09-13.md)。

以下是此前结果，不表示仍有任务运行。

## 最新：时间回退已定位到消息类型交界；样本转换原型通过测试

同一小时的120次来源时间回退，全部发生在REST快照与WebSocket更新之间；
各类型内部没有观察到回退。早于当天的来源时间全在REST快照里。
因此不能把原先的120次直接叫作实时更新乱序，也不能据此自动删数据。

样本转换原型已补上：预测输入只用过去，未来答案单独算；缺答案不填0；
混合时钟、回退和无效端点明确处理。87项相关测试通过，其中19项检查样本转换。
controller续接已正常结束，自己选了WS-only样本范围；计量$1.79。
但新的缺消息判定和文件尾部规则仍不够明确，请求没有执行，新训练尚未开始。
下一步把这些规则做成必填、可检查的结构，不能靠长段文字直接运行。
代码与记录已推自己的私有GitHub。原$200可用$153.48；当前没有后台训练。
详细依据见[时间来源与样本转换](CLOCK_ORIGIN_AND_SAMPLES_2026-09-13.md)。

## 较早：9月13日晚，真实单文件检查完成；新训练尚未开始

Controller正常交了方案，本次计量$1.34。随后读取它选中的一个Polymarket文件，
37秒读完151,802条记录：约90.3%的相邻有效中间价没变，发现120次相邻来源时间回退。
文件名是9月8日，但部分来源时间早到8月27日；具体含义仍需查清，不能直接删掉。

数据检查代码已发布到自己的私有GitHub，59项相关测试和服务器完整合成canary通过。
只读一个文件，没有新增付费模型调用；任务及子进程已结束。目前没有后台训练。
原$200预算仍可用约$155.27。还缺时间字段核实、样本生成及相关检查，没有新MSE。
结果、费用和下一步见[本次真实检查](SINGLE_OBJECT_AUDIT_2026-09-13.md)。

以下为历史过程，不代表仍在运行。

## 较早：9月13日，参数解析修复通过检查；真实新实验尚未开始

反馈会话已停止，进程已回收。三次“文本被转成对象”的接口错误已定位并修复，
31项相关测试、157项harness测试、两项免费真实Codex检查通过，`dsh-v1.4.1`已发布并核对远端。
没有新真实拟合。单文件核验尚未执行，事件到训练样本的转换仍需完成。
本次计量$1.560731166，另保留未返回调用上限$0.99967527；原$200可用$156.606502048。
见[接口修复及真实结局](JSON_TEXT_INTERFACE_FIX_2026-09-13.md)。下文是历史过程，不代表仍在运行。

## 9月13日更新：02已结束，编号接口修复已测试

02连续三次抄错两个长历史编号，没有产生新方案或训练结果。已等当前回复计量后结束，
实际花费$1.03047、不确定费用0，原$200可用$160.02051。不是模型分数不够而重试。
新输入改用短编号，完整原文和指纹保留；12项相关测试及真实Codex免费工具链通过。
正在发布修复后准备新会话。以下“已启动”段落是此前过程，02现在不再运行。

## 9月13日：新controller会话已启动

已接回核对后的旧研究，使用已发布`dsh-v1.4.0`和新时间检查工具。新会话
`temporal-source-controller-20260913-02`已启动；不是重跑旧会话。
18条当前反馈编号不重复，保留旧方案、archive、文件清单和费用。
controller自己填写并测试时间规则，随后提交第一份有效方案；数据仍未准入，不能直接训练。

本次会话上限$8.44038144，不是已消费金额。启动前原$200账本可用$161.050977880，
无未结束的模型调用。原final$50、repair$20未动。结果与实际费用完成后补到
[9月13日记录](DAILY_LOG_2026-09-13.md)。

历史交接8项测试、原harness157项测试、真实Codex免费7工具检查通过；外部交接程序
`pm-temporal-history-v0.1.0`在`feb46f8`发布到自己的origin，DSH运行源码没变。
取回的旧文件完整核对通过，未修改旧工作区或重开Dev/Test。
下面是此前状态，不能当成新会话的结果。

## 9月12日：时间规则检查已跑通，尚未开始新训练

给controller加了能实际调用的检查：明确什么时候作出预测、从什么时候计算未来区间，
以及缺消息和坏报价怎样处理。它自己选规则，先测再提交方案。157项测试、两条真实
Codex免费工具链均通过；这是修harness，不是新的预测结果。

还发现本机旧账本和会话有云端占位文件，会让读取等待。已把新运行环境放到本机缓存
目录，并在付费入口加文件检查。随后已取回指定记录：618个文件检查中占位项降为0，
父manifest/方案/授权指纹一致，原账本完整复核通过，可用仍为$161.05098。
今天没有新增付费调用、真实训练或Test访问。当前没有本次真实训练在后台运行。

新版本`dsh-v1.4.0`已发布到自己的私有origin（`815f05c`），完整发布核对通过。
下一步先完成跨版本工作区交接和付费SDK检查，再由controller用新工具明确规则，
不是直接照旧方案开训。发布凭证和下一步见[今天记录](DAILY_LOG_2026-09-12.md)，
具体实现、研究依据和限制见[时间规则检查](TEMPORAL_CONTRACT_2026-09-12.md)。
以下保留历史状态，不作为今天的预算复核或运行状态。

## 9月11日继续：真实会话已结束，找到两处交接问题

又完成一次GLM会话，用时3分37秒，计量$0.67170。它结合文件清单修订了方案，
去掉两天没有文件的日期。**这仍是方案修订，不是训练；没有新增MSE结果。**

自动核对发现：从8天减到6天，仍是同样的122个文件、11.89GB，因为删掉的两天
原本就是空的。它引用的内容清单实际只绑定1个文件，其余121个只有目录记录。
这个区别此前没有直接交给它，是我们又一处输入交接缺口，现已补入后续准备代码。
检查不会把目录记录当成内容验证，也不会自动启动全量扫描。

时序定义还没收敛：什么时候算“作出预测”，缺消息怎样标记，坏报价能否沿用旧值，
仍有互相矛盾的描述；原采集时钟与断线记录也没拿到。没有据此训练或开封测试集。
这次修复了历史意见重号和文件范围交接，48项相关测试、146项harness回归通过。

原$200账本：计量$32.79012；加历史不确定额$36.64902；另有$2.30预留，
可用$161.05098。当前无本次后台controller/训练进程。下一步应先把最小检查的
文件和时间规则明确到能执行，再验数据；不再重复付费让它笼统地要求“查所有天”。
代码和过程持续存入自己的私有origin；详见[本次详细记录](SOURCE_STUDY_BRIDGE_2026-09-11.md)。

## 9月11日较早：controller交了方案，尚未开始新训练

这次继续完成了两次真实GLM会话：第一次提出实验方案，第二次收到复核意见后修订。
合计计量$1.19284。两次均正常结束，0次市场模型拟合，没有新的MSE或收益结果。

方案是用过去一分钟的价格变化预测下一分钟，和“价格不变”比较。反馈后，它改选直接
记录的买卖报价，补充了时间查找规则，也把“没训练成”和“结果不好”分开。仍有问题：
缺消息不等于真实零变化；原始时钟尚未核实；所选训练日期包含当前目录缺文件的两天。
逐日文件清单此前没交给它，这是我们的输入交接问题，已补代码及测试，旧会话不改写。

发布版本`dsh-v1.3.0`，工程修改和controller研究分别记录。原$200账本当前计量$32.11842，
加历史不确定额后$35.97732，另有$2.30预留，可用$161.72268；不是预算耗尽。
当前没有后台训练在运行。下一步是让controller结合完整文件清单解决上述定义问题，
通过真实数据检查后才拟合；不能把这两次方案会话算成训练轮次。

完整过程、原方案位置、复核和版本见[本次记录](SOURCE_STUDY_BRIDGE_2026-09-11.md)。
以下保留较早的结果，不代表最新状态。

## Train-CV feedback widened after Round 3 — September 8

Post-run diagnosis found that Round 3's reusable feedback came only from an
unusually quiet September 5: 0.34% of rows moved and persistence MSE was
`6.08e-8`. The one-shot September 6 Dev was much more active: 3.21% of rows
moved and persistence MSE was `1.08e-6`. The controller's safe persistence
choice fit the narrow feedback it received, so the harness—not just the
candidate algorithm—needed correction.

Train-CV now uses a fixed three-day suffix selected without candidate labels or
scores. On the already-open Round 3 Train artifact, the new split has 7,513 fit
rows / 73 games and 6,307 CV rows / 23 games across September 3–5, with two
boundary-crossing games omitted. The scorer now also reports whole-game day
robustness while leaving aggregate equal-game MSE as the primary metric.

The fresh diagnostic canary
`controller-harness-multiday-canary-20260908-01` ran the changed path end to
end. GLM-5.3 completed 8 turns and 14 tool calls. Two E2B candidates covered all
2,991 Train-CV rows across 30 games and the first was 47.38% worse than
persistence; the controller revised it and selected a persistence candidate at
0.00%. No sealed Dev or Transfer data was opened. The execution queue closed
cleanly, zero E2B sandboxes remained, and total effective provider cost became
`$11.810483176 / $200`.

A second fresh canary,
`controller-harness-temporal-metrics-canary-20260908-01`, verified the final
scorer path. It completed 8 GLM turns, 16 logged tool calls and three isolated
executions. The controller selected a +0.99% aggregate Train-CV candidate that
improved 2 of 3 days, and its decision cited the median (+0.12%) and worst-day
(-0.89%) checks. No sealed Dev or Transfer data was opened. The full offline
suite passes 747/747, zero E2B sandboxes remain, and current effective provider
cost is `$11.988091674 / $200` with `$2.30` reserved but not counted as spend. Because
the source changed, the next formal run needs a fresh H0 ID and a genuinely
unopened Dev period.

No additional formal score was launched. September 6 is already opened and
September 7 onward is reserved for Transfer, so another score tonight would
either repeat Dev or contaminate the final holdout.

## Formal Archive cycle completed — September 8

The first useful result is now recorded in
[the formal run report](/Users/estelle/Documents/ChatGPT/self-evolving/research/market_rsi/ARCHIVE_FORMAL_RESULTS_2026-09-08.md).
Round 2 improved one-shot sealed Dev MSE by 1.99% over persistence. That gain did
not carry into the next time period: Round 3 compared three executed candidates,
rejected an imbalance correction that scored -5.87% on Train-CV, selected a safe
continuation model, and tied persistence at 0.00% on 2,400/2,400 unseen Dev rows.

This is evidence that the controller can use negative execution feedback and
avoid a worse update. It is not evidence of repeated self-improvement or profit.
Transfer/Future Test remains unopened. The source manifest, Archive chain and
lifecycle ledger validate; zero E2B sandboxes remain. Effective provider cost is
`$11.673435002 / $200`; `$2.30` of reservations are not counted as spend.

## Controller harness v3 data boundary accepted — September 8

The real Train-CV plus one-shot Dev canary is complete. In
`controller-harness-traincv-canary-20260908-01`, GLM-5.3 used the Codex harness
for eight turns, fourteen logged tool calls and two isolated candidate runs. All
controller-visible candidate scores came from a temporal split of already-open
Train. The current Dev path was not supplied to the controller execution service.

After the controller selected `mid_persistence_v2.py` and its process was reaped,
the runner opened the old diagnostic Dev exactly once. All 300 rows completed,
the candidate matched the mid baseline (`3.75e-7` equal-game MSE, 0 relative
improvement), and the append-only lifecycle promoted `old-dev-00` to Train. The
result is marked invisible to the completed session and visible only from the
next Archive. Future Test stayed sealed. This proves the boundary and transition,
not researcher improvement.

The lifecycle audit passes with no active Dev claim. Afterward there were zero
matching local processes and zero active E2B sandboxes. The full offline suite
passes 719/719. Cumulative token-based Tinker cost is `$1.697538222`; `$2.30` of
E2B upper bounds remain reservations without provider invoices and are not
reported as spend. Formal A0 has not started; its data blocks and final Transfer
commitment still need to be frozen.

## Blocker-resolution work resumed — September 7, 15:47 UTC

The user authorized work to continue after the eight-hour pilot closeout. This
is a new implementation phase; it does not rewrite the closed pilot or turn its
diagnostic data into a result.

Two local blockers are now fixed. A small export from the exact original capture
host can be copied into a frozen, hash-checked intake without copying secrets or
raw order-book data. Live runs now require an immutable reviewed admission receipt
that binds the collector evidence, whole-game split, chronological labels, scorer,
runtime, budget and study deadline. There is no boolean or callback bypass.

The former per-stage timeouts are also replaced by one non-renewable step deadline.
Research, coding and sandbox execution share that same deadline; later stages do
not receive a new clock. The fixed bound includes every declared stage, process
reaping and 30 seconds of local overhead. A full step that no longer fits is not
started, and scientific limits are not shortened to squeeze it in.

**595 offline tests pass.** Source hashes are frozen in
`blocker-resolution-source-receipt-01.json`. No model call, sandbox, paid baseline,
market score, Test read or provider charge was made in this phase.

The remaining blocker is external evidence from the original collector host
`173.255.234.236`: collector source, service/startup definition without secrets,
existing session/reconnect evidence, and its capture manifest. The Linode page is
open in the in-app browser but still shows the login screen. Until that evidence
is reviewed, clock and reconnect semantics remain unknown and live admission stays
closed. After login, the next safe path is: freeze the small export, review those
semantics, materialize whole-game Train/Dev/Test splits, run the fixed baseline,
then authorize exactly one paid research step if all gates pass.

## Research closed — September 7, 13:20 UTC

[Final report](/Users/estelle/Documents/ChatGPT/self-evolving/research/market_rsi/EIGHT_HOUR_REPORT_2026-09-07.md).
The requested scored comparison was not delivered. No real research round,
learned guide, final Test evaluation or profit result exists. The historical
collector's clock/session evidence is missing, and the real data/task admission,
positive revised worker verification, whole-step deadline and PnL integration
are still incomplete. Do not restart research without new user authorization.

Verified: 579 offline tests; 23 final evidence checks; 5,213 diagnostic rows from
seven games, with 308 excluded decisions. The broader metadata audit found
44 games shared by the proposed file-date split. These are data/software findings,
not evidence of researcher improvement.

Cumulative pilot accounting: $0.00367902 token estimate, $0.40 unresolved E2B
holds, $199.59632098 available. The $200 was not spent; invoices and allocated
subscription/server costs remain incomplete. Only one synthetic E2B fixture
was dispatched within this eight-hour window, with a $0.10 hold and no new
Tinker inference. No hold was released without billing evidence.

At 13:19 UTC: zero E2B sandboxes, no exact local pilot workers, both existing
Linode feeds healthy, 78.792 GiB free. Kalshi tennis remains discovery-only idle;
Polymarket US has actual fresh observations. Only those existing feed-health
checks continue. No new collector, paid request, venue switch or experiment.

## Historical implementation log (not current authorization)

### Report draft — 12:34 UTC

[The eight-hour report](/Users/estelle/Documents/ChatGPT/self-evolving/research/market_rsi/EIGHT_HOUR_REPORT_2026-09-07.md)
now separates actual data findings, component checks, unrun research and costs.
It is a draft; research/report deadline remains13:33UTC /09:33New York.
A read-only evidence audit passed23 checks. No real study config, scored market
comparison or new model call was found in this pilot. Four exact sandbox cleanup
receipts verify; the12:29 live inventory was empty. The budget journal confirms
that the GLM canary and first three sandbox probes preceded05:33. Only the07:08
synthetic Harbor fixture was newly dispatched inside this window, with a$.10 hold
and no invoice yet. Cumulative pilot figures remain unchanged, not$200 spent.

### 12:27 UTC — late phases are stopped before another dispatch

The runner now checks the unchanged time allowance after catalog preparation,
after claiming an attempt, before coding, and after sandbox preparation. A late
phase keeps the existing claim, response and costs; it is not retried or given
shorter limits. The step envelope now includes the coder's existing five-second
process-reaping allowance. These are dispatch checks, not proof of one hard
whole-step operating-system deadline.

Coder version/auth preflights now run in bounded trusted subprocesses and share
the same request deadline as generation. A delayed setup cannot grant a fresh
timeout or round a fraction of a second up to another second. Independent receipt
readback checks the exact commands, permitted environment names, streams and
process termination. No account, model, package, old canary or common starting
instructions changed. Official Codex documentation was checked for saved-login
non-interactive behavior; it does not certify our custom timeout implementation.

**579 offline tests pass**, including 18 new checks. All new subprocess tests
are human-authored local fixtures, not model inference or candidate execution.
Source archive: phase-deadline-sources-01.json. No new paid execution or market
score. General live admission remains closed; historical source-clock/session
proof, real task/baseline/fee admission, positive revised live-path verification,
whole-step timing and final PnL integration remain unresolved.

At 12:25 both exact feeds were active/enabled with unchanged PIDs and zero restarts;
Polymarket had actual fresh observations, Kalshi tennis was discovery-only idle.
Disk free: 78.889 GiB. Budget unchanged: $0.00367902 token estimate, $0.40 unresolved
holds, $199.59632098 available; invoices incomplete. Research stops 13:33 UTC.

### 12:06 UTC — final failures stay visible, without a replacement score

Final evaluation now records a fully verified post-isolation failure separately
from an uncertain running/pending job. The failed attempt keeps its evidence,
cost and missing score. A recorded runner review is required before moving to
the next originally planned job; no new answer, code, retry or model advice is
created. Missing setup, output or cleanup evidence still leaves a job pending.

Reports retain every planned task. Unavailable pair scores are null, not zero
or a score on fewer rows. Available pairs are only partial diagnostics when a
method failed; no complete-comparison or overall-winner claim is made. The status
report also lists jobs that never started. Later invoices do not rewrite the
original cost snapshot. The causal judgment remains a trusted review, not a
conclusion inferred from candidate-controlled stderr.

**561 offline tests pass**, including 11 new failure/review tests. No actual final
failure, review, hidden set or market result was produced. Source archive:
final-failure-sources-01.json. Live admission is still closed. Remaining: original
source-clock/session proof, real task/baseline/fee admission, positive live-path
verification, independent whole-step wall timing and final PnL integration.

At 11:52 both exact Linode feeds were healthy/unchanged, with 78.947 GiB free.
At 12:00 the ledger was unchanged: $0.00367902 token estimate, $0.40 unresolved
holds, $199.59632098 available; invoices incomplete. No new paid execution or
source-server changes. Deadline remains 13:33 UTC / 09:33 New York.

### 11:46 UTC — sealed transfer scoring is connected offline

final_stage.py waits for every learning state and transfer submission to be
sealed before it can read hidden task files. It checks the original hidden and
baseline hashes, rejects shared games/contracts/rows, checks earlier information
availability, and uses only each arm's already-selected code. The final batch
has one common baseline plus Reset, Archive and Learn per transfer task. It makes
no new researcher/coder call and cannot send final results back into study memory.

The existing isolated fit/predict transport is reused with a final-only binding;
hidden labels/endpoints remain on the trusted host. Exact complete prediction
logs, original evidence and cloud cleanup are rechecked before one paired numeric
report. Missing predictions are not dropped, failures are not assigned zero, and
pending jobs are never redispatched. Numeric accuracy is not simulated net profit.

**550 offline tests pass**, including 21 new final-stage tests. One test runs two
synthetic transfer tasks through eight fabricated final executions. No actual
hidden set was opened, real study created or market result measured. The skill's
same-mask, whole-game and short-sample rules influenced these checks; the actual
market experiment-spec validator still needs an admitted, frozen real task.

Source archive: final-stage-sources-01.json. Remaining: historical source-clock/
session proof, real task/baseline/fee admission, live verification of the revised
general path, enforced whole-step timing, and final failure/PnL handling. The final
stage currently keeps incomplete/failed executions pending, not silently skipped.
Do not describe the complete research experiment as ready or successfully run.

At 11:30 E2B showed zero running/paused sandboxes and no matching local market
worker was found. Both exact Linode feeds were healthy/unchanged, 78.986 GiB free.
The 11:44 ledger and old frozen artifacts verify unchanged: $0.00367902 estimated
token charges, $0.40 unresolved holds, $199.59632098 available; invoices incomplete.
No new paid execution. Research/report stop remains 13:33 UTC / 09:33 New York.

### 11:23 UTC — a reviewed candidate failure no longer blocks the study forever

The new runner-only review path rechecks the original failure's worker, sandbox,
runtime, protocol, cleanup and cost evidence. A trusted reviewer can record that
it was a candidate outcome under the unchanged execution contract. That judgment
is not inferred from the candidate's stderr or proved by filling in a form.
Uncertain jobs, missing setup evidence and source-changing repairs stay blocked.

The review appends a separate record: it does not erase the failed attempt,
invent a score, make the candidate eligible, add a retry or free money. Normal
scheduling uses a fresh next ID. Human review notes never enter any researcher's
memory or guide. Later invoices can be recorded without rewriting the old hold.
Interrupted review commits can recover without another model or sandbox call.

**529 offline tests pass**, including 16 new review/scheduling checks. These use
fabricated receipts. No actual review, scored market task or new provider call
ran. Live admission remains closed. This is human implementation work, not
agent-learned improvement. Source archive: failure-review-sources-01.json.

Remaining: source receipt-clock/session proof, an admitted real task/baseline,
verified whole-step timing, a live check of the revised general execution path,
and final scoring. Do not treat source-changing repair as a reviewed no-change
failure. At 11:20 both feeds were healthy/unchanged with 79.003 GiB free. No
services changed. Budget/report deadline unchanged: stop research at 13:33 UTC.

### 11:14 UTC — sandbox owner is bounded; cloud cleanup stays separate

The general Harbor path now runs in a trusted local process with a 270-second
deadline and a two-second reaping allowance. Before a new sandbox is created,
its unchanged 240-second lifetime plus setup/cleanup allowance must fit before
13:33 UTC. The E2B key stays in that trusted child's environment, not its input
artifact or the candidate sandbox. Local exit does not prove cloud cleanup;
exact sandbox kill receipts remain required and uncertain costs remain held.

The new child explicitly disables SDK connection retries before import. E2B's
existing retry transport concerns connection failures before request write;
this is NOT evidence that earlier sandbox creates were duplicated. No package,
old canary or scientific execution limit was changed. The revised positive live
path has not run. Sources: bounded-harbor-sources-01.json.

**513 offline tests pass**, including 12 new process/receipt checks. No new paid
request, scored market task or learned research guide. Original historical
receipt-clock/session provenance still blocks live admission. Whole-step timing,
reviewed-failure resumption and final scoring remain incomplete.

The ledger still records $0.00367902 in token-based estimated charges and $0.40
in unresolved holds, leaving $199.59632098 available; invoices are incomplete.
The old Harbor claim, GLM canary source and common initialization still verify.
At 10:36 both exact Linode feeds were healthy/unchanged with 79.081 GiB free.
Research/report deadline remains 13:33 UTC / 09:33 New York.

### 10:33 UTC — local model-worker timeout is now enforced separately

The GLM worker previously combined several SDK calls with separate timeouts;
that was not one firm local deadline. It now runs encoding and sampling in
trusted subprocesses under the same request deadline. The parent limits input
and output, kills/reaps only its own process group on timeout, and preserves
private hashed receipts. The sampling key goes only to the sampling child's
environment; no key is placed in its input artifact. Each permanent request
requires a fresh transport object, with no repeat response.

Live completion checks now verify both process receipts and their exact request/
response bytes before accepting terminal model usage. Killing the local worker
does NOT prove the provider stopped, cancel a remote request, release a hold or
make its cost zero. Ambiguous requests remain pending. Parent and child both
retain the closed data-admission check.

**501 offline tests pass**, including 21 new checks. Tests exercise actual benign
local hangs, output floods, bidirectional pipes, exact process reaping and the
GLM child refusing closed admission before model use. Successful model-process
receipts are fabricated tests; the revised valid live GLM path has NOT run.
No actual model call or market score. Old GLM-canary source and the old Harbor
fixture claim still verify unchanged. Sources: bounded-glm-sources-01.json.

Historical timestamp/session provenance, general Harbor/whole-step deadline
verification, causal-review resumption and final scoring remain incomplete.
The real ledger/common initialization are unchanged. At 10:18 both Linode feeds
were healthy/unchanged with 79.116 GiB free. Report/stop stays 13:33 UTC.

### 10:12 UTC — the three-arm loop is connected and tested offline

study_runner.py now connects the existing researcher, coder, sandbox receipt
checks, owned memory and submission choice. It advances one recorded action at
a time, without choosing a method or best score for the researcher. It freezes
its configuration/source/data commitments and uses the same task/step order for
all arms. Changed inputs, wrong transports, insufficient budget and expired
windows block new dispatch. Pending jobs require receipt reconciliation, never
another provider call; interrupted completion commits can be recovered.

**480 offline tests pass**, including 15 new orchestration checks. One complete
test traverses three arms, two learning tasks and two transfer tasks: 12 fake
research responses, 12 fake choices, 12 fake coder responses and 12 fabricated
sandbox receipts. No candidate code runs locally. The fixture checks that own
history and the last Learn guide propagate correctly, other-arm evidence stays
out, and earlier transfer feedback cannot affect later transfer tasks. These
counts are software tests, NOT actual experiments or evidence of improvement.

No new paid/cloud work. Historical receipt-clock/session evidence still blocks
live admission. A real task/baseline, live verification of the revised general
runner, enforced end-to-end wall timing, causal-review resumption and final
scoring are not complete. Do not turn the fixture executor into a live bypass.
Source/intervention archive: study-runner-sources-01.json.

At 10:12 the ledger was unchanged: $0.00367902 token estimate, $0.40 unresolved
holds, $199.59632098 available; invoices incomplete. Both Linode feeds were
healthy at 10:02, with 79.142 GiB free. No service changes. Research stops and
the report is due at 13:33 UTC / 09:33 New York.

### 10:02 UTC — failed sandbox attempts retain evidence, not invented scores

sandbox_failure_evidence.py now records a terminal post-isolation execution
failure with its actual available Train/Dev trace, partial unscored predictions,
candidate-only stderr and provider receipts. Missing isolation/library/cleanup
evidence or contradictory success receipts still block completion. It never
releases an unresolved cost hold or retries an answer. The shared sandbox receipt
checks are also used by successful completion.

StudyState keeps such a failed attempt in its own arm's history and blocks further
research, selection and phase freezing pending causal review. A trusted review
completion/resumption path is NOT implemented yet; this is not automatic recovery.
The outer study orchestrator is also still unfinished. This work addresses error
accounting, not historical source admission or measured research improvement.

**465 offline tests pass**, including 17 new fake-receipt failure tests. No new
cloud execution, scored market experiment, selector inference or learned guide.
Sources/intervention: sandbox-failure-sources-01.json. At 10:01 the real ledger
still showed $0.00367902 token estimate and $0.40 unresolved E2B holds, with
$199.59632098 available and invoices incomplete. At 09:42 both exact live feeds
were healthy/unchanged, with 79.565 GiB free. No service changes. The existing
heartbeat remains active and the research/report deadline remains 13:33 UTC.

### 09:37 UTC — preserve candidate errors instead of unexplained exits

While connecting the outer runner, code inspection found that candidate stderr
was discarded. A missing import could therefore surface only as an incomplete
response, hiding useful failure evidence. The prospective general driver now
uses diagnostic_channel.py and sandbox_development_runner.py to retain the
candidate's stderr in a separate private file. The unprivileged endpoint's
existing 10 MiB hard file limit remains fixed; output is hash-bound and explicitly
candidate-controlled, not an independently established cause or a score.

Root evaluator tracebacks remain runner-only. Successful Dev completion now
includes the separately verified candidate diagnostic. Large diagnostics may
exceed a later declared prompt allowance; reject that request rather than silently
truncate the Archive arm's history. A failed-sandbox completion producer and the
outer study orchestrator are still needed. This logging fix does not resolve the
historical arrival-clock/session gate or certify a new live execution path.

**448 offline tests pass**, including 12 new checks. Human-authored subprocess
fixtures cover missing imports, timeout/reaping, OS file-size bounds, private
exclusive logs and malformed bytes. Mocked composition tests keep evaluator
tracebacks out of model input and reject changed diagnostics. No generated code
was executed on Mac. The updated general root runner has NOT run in E2B.

The old cloud canary's worker and all five deployed source hashes still match;
they were not patched or rerun. Sources/intervention: diagnostic-channel-sources-01.json.
No new paid calls. At 09:37 the ledger remained $0.00367902 token estimate,
$0.40 unresolved holds, $199.59632098 available; invoices incomplete. At 09:28
both feeds were healthy/unchanged with 79.59 GiB free. Deadline stays 13:33 UTC.

### 09:23 UTC — actual historical metadata breadth and a split hazard

Read-only analysis of 12 daily CSVs (27.7 MB, source hashes saved) found 209
recognized MLB candidate game entries / 418 contracts. Of these, 109 start in
the proposed Train dates and 55 in the proposed Dev dates. These are metadata
listings, NOT counts of valid quote/label coverage or completed research tasks.

**44 game entries appear in both proposed file-date partitions.** Daily files
cannot be independently assigned to Train and Dev; whole-game grouping and
availability checks are necessary. There are also 45 listed games scheduled
outside the inspected date range. Across all series 48 unrecognized native
ticker rows were excluded with explicit counts, never repaired silently.

This is a real source-metadata finding, not a market prediction or profit result.
No model/provider job, source write or service change occurred. The original
collector clock/session proof is still absent. Historical data is not admitted
for scoring. Full evidence/script: historical-metadata-breadth-01.json; explanation
in HISTORICAL_DATA_INVENTORY_2026-09-07.md. **436 offline tests pass**, including
seven counter tests. Next: outer study orchestration and failed-sandbox evidence.
Report deadline remains 13:33 UTC / 09:33 New York, with no budget increase.

### 09:17 UTC — one recorded researcher choice per task

selection_protocol.py / selection_worker.py connect a durable owned selection
claim to the existing single-response GLM worker and its token ledger. After the
predeclared experiment count, an arm can select only its own eligible candidate
or the frozen baseline. Invalid terminal output uses that baseline without a
replacement answer or host-selected best score. Ambiguous calls remain pending.
The choice cannot trigger coding or revise a guide. Direct unverified submission
is now fixture-only; real studies require the claimed selection path.

StudyState persists the choice and its own evidence/usage, handles interrupted
completion without another sample, and keeps all research blocked while a choice
is pending. The last learning states and all transfer submissions must still
freeze in order; earlier transfer feedback is not available in a later task.
The ordering seal remains distinct from scientific admission and hidden scoring.

**429 offline tests pass**, including 16 new selection tests. They use fabricated
completed research and fake model responses; no actual selector inference or
market experiment ran. All model routes, common initialization and the completed
Harbor prediction fixture remain unchanged. New prospective selection policy and
source changes are recorded as human implementation decisions in the protocol
and selection-sources-01.json, not credited as autonomous learning.

No new provider calls. At 09:08 both exact Linode feeds were active/enabled with
unchanged PIDs/zero restarts and 79.62 GiB free; actual Polymarket observations
were fresh and Kalshi tennis had healthy idle discovery. No service changes.
Next: complete failed-sandbox evidence handling and the outer bounded study
orchestrator. Original historical clock/session provenance is still unavailable;
live admission remains closed, and the 13:33 UTC report deadline stays fixed.

### 09:05 UTC — terminal failed answers stay in owned memory

failure_evidence.py now retains invalid first researcher responses and terminal
unsupported/invalid coder output, with raw available evidence and actual metering.
It records no score, creates no eligible predictor, releases no holds and makes
no replacement call. A valid response cannot be discarded through this path.
worker_receipts.py now distinguishes a verified terminal response from permission
to execute it; live coder receipts additionally require exact process reaping.

**413 offline tests pass**, including 13 new failure tests. A mocked ambiguous
provider timeout keeps its reservation and active study claim: this is not
permission to continue while a request might still be running. Missing usage,
forbidden tool events and failed sandbox execution still require a separate
runner investigation/completion path. This is not a general recovery mechanism.

All new tests use fake providers and temporary ledgers. No new paid calls,
real-market scores or researcher learning results. The real ledger reconciles
unchanged: $0.00367902 token estimate, $0.40 unresolved E2B holds, $199.59632098
available; invoices incomplete and final50 protected. Source/intervention archive:
failure-evidence-sources-01.json. Earlier archives are preserved unchanged.

Next: record the researcher's task submission choice from its own permitted
evidence; do not substitute a host-selected best result. Live data/task admission
remains closed because the original historical collector clock/session evidence
is unavailable. Continue useful implementation within the fixed 13:33 UTC window.

### 08:59 UTC — completed execution evidence reaches owned memory

dev_evidence.py now rebuilds a completion from the active study request and
preserved researcher/coder/Harbor receipts. It independently recomputes Dev
errors on the full paired mask, using a baseline rule declared in the original
task, and retains the available own Train/Dev inputs and execution trace. It
does not trust an assessment file's claimed score. Inspection output stays
candidate-authored and cannot become a predictor submission. Source/runtime,
exact sandbox cleanup, budget dispatch and read-set mutation checks precede
memory commit. Sandbox holds remain holds after cleanup, not reported spend.

**400 offline tests pass**, including 16 new completion tests. They use mock
providers and fabricated execution receipts; no scored real-market experiment
or additional cloud execution has run. The live path still stops at the missing
independent admission gate. Snapshot: dev-evidence-sources-01.json.

Next: preserve failed attempts in the same owned memory without retrying or
inventing results; then record the researcher's final submission choice. Original
collector clock/session evidence is still missing. The existing feed check at
08:47 was healthy/unchanged, with 79.66 GiB free. No service changes or paid calls.
The 13:33 UTC report deadline and $200 total cap remain fixed.

### 08:39 UTC — durable owned memory and study phase barriers

study_state.py now persists common-bound requests, single active-step claims,
completions, guide revisions and submissions in an append-only study journal.
Reset keeps current-task feedback but drops earlier-task experience; Archive
keeps its own earlier learning records; Learn may also retain an evidence-linked
guide from its recorded response. All arms use the same starting instructions,
task order and request allowances. No all-arm status view is sent to a model.

The last learning states must all freeze before any transfer task begins. Transfer
feedback can be used within its current task, never by a later transfer task;
the guide cannot change in transfer. All submissions must be committed before
the ordering barrier reports ready. That is NOT scientific admission or permission
to open hidden data. The store makes no predictor choice and does not establish
that a submitted completion's contents are true. The trusted completion/scoring
producer and separately recorded researcher selection still need connecting.

**384 offline tests pass**, 27 new. Tests cover ownership, guide citations, phase
boundaries, deadlines, concurrent-claim exclusion and restart recovery. A durable
completion can be recovered after a crash before journal append without rewriting
it or sampling again. These tests use fabricated tasks, records and guide text;
there has been no actual researcher-generated revision or scored research study.
New sources/intervention: study-state-sources-01.json.

No new provider calls. At 08:38 the real ledger was unchanged: $0.00367902 Tinker
estimate, $0.40 unresolved E2B holds, $199.59632098 available; invoices incomplete.
The 08:30 feed check was healthy/unchanged with 79.69 GiB free, fresh actual Polymarket
books and idle-tennis discovery. Neither service was modified.

Next: bind real worker/execution/independent Dev evidence into the completion
producer, and record task submission choices without human score-based selection.
Independent source/task/deadline admission remains incomplete. Historical collector
arrival-clock/session evidence is still missing; do not bypass that gate or repeat
exhausted source searches. The 13:33 UTC report deadline remains unchanged.

### 08:24 UTC — general Harbor development driver, offline verification

development_harbor.py now composes both execution modes with Harbor and the
existing bounded E2B cleanup owner. It persists exact candidate/packet/runtime/
source commitments, rechecks upstream worker receipts, and rejects library
version mismatches before importing candidate code. Prediction journals and
inspection diagnostics receive independent full protocol/input/output read-back.
Inspection output stays candidate-authored; neither mode scores itself.

**357 offline tests pass**, 25 new. The actual installed Harbor constructor selects
the intended agent/environment classes without creating a sandbox. Mocked lifecycle
tests cover one creation, no network/build, exact cleanup after failure, exhausted
learning budget, protected final allocation, ambiguous-create holds, source changes
and incomplete output. These are software tests with fabricated inputs/receipts,
not actual general cloud execution, market scores or researcher improvement.

The general driver's require_admission remains an unconditional live block,
including before reading keys/reserving/creating a sandbox. There is no caller
callback or CLI flag to bypass it. Original historical collector clock/session
evidence remains missing; full source/task/phase/deadline and study-state supervision
are not complete. Do not buy another format canary or repeat exhausted searches.
Next: study state, owned experience/guide propagation, and all-transfer-submission
freeze; then connect the independent data gate when its actual evidence exists.

The new prospective general driver has a 240-second sandbox TTL/$0.10 hold and
fixed lifecycle timeouts. This is a recorded infrastructure design change before
scores, not an agent-learned decision. The old completed 180-second cloud fixture
is unchanged; its exact source claim passed read-back again without provider calls.
trial_inputs.py now returns its bound runtime for deployment; prior source archive
is preserved. Full new snapshot/intervention: development-harbor-sources-01.json.

No new provider calls or change to the real ledger: $0.00367902 Tinker estimate,
$0.40 E2B holds (not spend), final50/learning120/repair20 intact. At 08:12 the two
exact Linode services were active/enabled, unchanged PIDs and zero restarts; actual
Polymarket books were fresh and tennis had fresh idle discovery, not quotes.
Disk was 79.72 GiB free. No source service or data changes were made.

### 08:10 UTC — completed-job handoff and development input composition

worker_receipts.py now reads the stored first researcher response against the
original request, permanent claim and terminal append-only budget receipt. It
rechecks the coder's exact request, first terminal event, source text, subscribed
identity and usage. Changed, incomplete, cross-arm or failed jobs cannot pass to
execution; files are rechecked at handoff. It never executes returned code on Mac.
These are runner-storage integrity checks, not signatures against a malicious host
and not proof that the historical market source is valid.

trial_inputs.py connects those receipts to exact catalogued Train/Dev bytes.
Prediction inputs strip Dev labels and preserve sequential release; inspection
may see permitted Dev labels and keeps its output untrusted. Actual request sizes
and the implemented CPU/memory envelope are checked before execution preparation.
Runtime library availability still requires a sandbox check. Hidden Test is not
accepted by this development interface. The root-side inspection runner is now
written, but it has NOT run in Harbor/E2B; the earlier prediction fixture is
unchanged and must not be cited as cloud-inspection evidence.

**332 offline tests pass**, including 38 new receipt/composition checks. The local
composition tests use fabricated tasks, mock model responses and human-written
protocol responses, not candidate-code execution or research results. Source
snapshots: worker-handoff-sources-01.json. No new provider calls or real market
scores. The complete live source/task/phase/deadline admission and general Harbor
driver remain unfinished; default live dispatch remains blocked.

At 08:09 the real budget journal still reconciles unchanged: $0.00367902 Tinker
estimate, $0.40 unresolved E2B holds, $199.59632098 available; learning120/final50/
repair20 untouched. Holds are not spend, and invoice reconciliation is incomplete.
Next: connect these prepared development inputs to the general bounded Harbor
driver and its independent output checks, without bypassing the missing original
historical collector clock/session evidence. Do not repeat completed canaries or
exhausted source searches. The report deadline remains 13:33 UTC / 09:33 New York.

### 07:53 UTC — Train/Dev inspection interface and ownership checks

Implemented inspection_stream.py and inspection_candidate_server.py. An inspection
request is bound to the original researcher/coder packets, common initialization,
task, arm and exact Train/Dev artifact bytes listed in the public task catalog.
It refuses another task/arm, swapped files, uncatalogued IDs, Test-labelled input
and extra runner/hidden fields. All arms start with the same permitted payload.
Current-task Dev labels may be inspected, as allowed by the protocol; hidden Test
may not. This is deliberately separate from label-free sequential prediction.

Malformed/missing numeric values are preserved for diagnosis rather than cleaned
or imputed. Such inspection does not make those rows valid training examples.
The first bounded diagnostic is retained as candidate-authored/untrusted text or
JSON, not an independent score or data-admission decision. A claimed passed=true
inside it cannot replace runner checks. inspect/reject_measurement keep their
original action, with no resampling or rewritten experiment.

**294 offline tests pass**, 20 new, including one human-written local subprocess
fixture through the bounded line transport. The new Linux inspection endpoint
refuses Mac execution before candidate import. It is NOT yet connected/tested in
the actual Harbor/E2B driver; the earlier cloud fixture exercised prediction only.
Sources and limits are archived in inspection-sources-01.json. No new provider
calls, historical score or agent-learned revision occurred.

Next: complete source/provenance-backed task admission and outer researcher/coder/
execution orchestration, including cloud inspection composition. Do not replace
the absent production gate with an unconditional callback or a fixture flag.
Historical capture-clock/session provenance remains blocked externally. Budget
unchanged: $0.00367902 Tinker estimate and $0.40 unresolved E2B holds, not spend.
The 07:43 feed check was healthy: unchanged exact services/PIDs, zero restarts,
fresh Polymarket books, idle-tennis discovery and about 80 GiB free. No changes.

### 07:40 UTC — separate taking simulator tested on synthetic cases

Implemented taking_replay.py: explicit YES/NO contra-book prices, both-leg fees,
adverse slippage, fixed size, one global pending/open order and conservative
cash reservation at decision time. A later fill or gain cannot fund an earlier
decision. Exit-depth failure produces a write-off diagnostic and halts further
trading; it is not dropped or reported as a successful close. Zero-trade and
zero-PnL-trade days stay distinct. Unresolved scheduled windows reject PnL; the
historical diagnostic's 308 censored windows must not be silently omitted.

Per-market fee rules require validity/source commitments but are not independently
certified by this module. The implemented rounding is an explicitly declared
simulation approximation, not verified exchange billing. No actual market fee
contract, target or split has been frozen. Full source/phase/data admission is
still missing, so this module has no live CLI or scientific-admission override.

Reports separate modeled PnL/costs, per-day/game results and realized-only drawdown;
intrahorizon mark-to-market remains unavailable. A dynamic program computes
non-overlap perfect-foresight bounds and an exactly baseline-trade-count bound,
relaxing cash and post-writeoff halts. Independent exhaustive enumeration checks
the interval solver. These are objective diagnostics, not model improvements.

**274 offline tests pass**, 24 new. All new cases are synthetic. No real market
scores or new provider calls. Sources are archived in taking-simulator-sources-01.json.
Tinker estimate remains $0.00367902, E2B holds $0.40, learning120/final50 intact;
budget journal unchanged. Next: diagnostic inspect execution and outer task/worker
admission/orchestration. The original historical capture-clock/session export is
still missing; do not reopen denied SSH or repeat exhausted source searches.

The 07:30 Linode check found both exact services active/enabled, unchanged PIDs,
zero restarts, fresh Polymarket books and idle-tennis discovery. Approximately
80 GiB was free; no source-side change was made.

### 07:21 UTC — independent numeric scorer and saved cloud-receipt read-back

Implemented market_scoring.py. It independently reads hash-bound complete
prediction journals, rejects missing/extra/invalid predictions and recomputes
numeric labels from saved price endpoints. It reports paired MSE/MAE, calibration,
Pearson/rank correlation, and per-day/per-game summaries. Unchanged predictions
have zero improvement; undefined constant-series correlations remain null.
Whole-session resampling is unavailable for fewer than 20 untouched sessions,
and no output automatically authorizes promotion. Exact source validity and
pre-score task/phase admission remain separate gates, not a caller's flag.

**250 offline tests pass**, including 21 new scorer checks. The new reader also
validated all three saved predictions from harbor-stream-integration-01 without
another sandbox or model call. Full new sources/hashes are archived in
numeric-scorer-sources-01.json. This is arithmetic and artifact-integrity evidence,
not a market score or LLM learning result. Net PnL is still explicitly unimplemented;
the actual scientific target and task split have not been frozen.

The official July7 Kalshi fee schedule was checked: series multipliers and its
fee-plus-position-cost rounding rule must be resolved for the chosen historical
markets, not replaced by a blanket fee assumption. See SCORING.md for the source
and remaining fee/latency/depth/position simulation work. Do not use gross quote
changes as profit. Other next work: separate inspect execution, provenance-backed
task admission and complete researcher/coder/market orchestration.

No new provider calls: Tinker estimate $0.00367902, unresolved E2B holds $0.40,
protected final $50. The ledger hash remains
b34393be63e5b5b11ea018fe11860ffc9d4c71fd8b9d1d6161fb207693ab3ea6.
The 07:13 read-only Linode check found both exact units healthy with unchanged
PIDs/zero restarts, fresh Polymarket books, healthy idle-tennis discovery and
about 80 GiB free. No source service or data was changed.

### 07:10 UTC — actual Harbor/E2B sequential execution passed

One new synthetic integration trial, `harbor-stream-integration-01`, completed
through the installed Harbor 0.17.1 lifecycle and E2B 2.38.0. Its human-written
candidate fitted two toy Train rows and returned three sequential predictions.
The independent host read-back verifies input/code bindings, prediction sequence,
hash chain, completion receipt and expected fixture values. This is execution
evidence only: no market data, model call, trading score or research improvement.

The new project-local E2B adapter uses one creation attempt, an explicit existing
template, a 180-second provider lifetime, denied Internet access and a permanent
$0.10 setup hold before dispatch. It bypasses neither data admission nor budgets.
It replaces Harbor's default creation/retry/lifetime behavior for this task without
patching the installed framework or building an image. Its only live entry point
currently admits the exact human-written fixture, not real datasets.

Before candidate import, a separate trusted probe verified UID65534, no groups,
no-new-privileges, loopback-only networking, blocked outbound TCP, absent paid
keys, denied private-file reads/writes and denied public-code writes. Complete
future feature inputs stayed root-private; no evaluation labels were uploaded.
The runner committed each prediction before releasing the next feature row.
This is tested isolation for this fixture, not a proof against all sandbox attacks.

Harbor reported no exception and finished at 07:08:59 UTC. Exact sandbox
`iel6mh1h82y8xwop33ouj` was killed with acknowledgement; the 07:09 inventory
showed zero running/paused sandboxes. No retry was needed. The only expected
missing output is failure.json because the worker succeeded. Candidate stderr
is intentionally discarded by the bounded transport, not claimed as captured.

**229 offline tests pass**, including 16 new adapter/receipt checks. The actual
Tinker token estimate remains $0.00367902. Four E2B holds now total **$0.40**,
awaiting provider billing; they are neither measured spend nor active resources.
The protected final $50 and learning $120 are untouched. No scored market
comparison exists. Next: independent fixed scoring, the separate inspect path,
then real task admission and outer researcher/coder orchestration. Original
historical capture-clock/session provenance remains the external data blocker;
do not repeat denied SSH, old canaries or completed source searches.

The 06:48 Linode check found both exact feed units active/enabled with unchanged
PIDs and zero restarts. Polymarket books were fresh; tennis discovery was healthy
idle with zero active pairs. Approximately 80 GiB remained free. No source
service, capture code or archive job was changed.

### 06:45 UTC — subscribed coding adapter and exact model pin

Implemented coder_worker.py. It passes the unchanged common instructions, the
researcher's permitted history and its proposal to one no-tools coding session.
The request, proposal, runtime and source are hash-bound. It preserves the first
response and terminal subscription usage, including unsupported/invalid code,
and does not automatically invoke the coder again. The response file must match
one saved terminal message. Returned source is only syntax/interface-checked;
it is never imported or executed on the Mac. inspect/reject_measurement retains
its separate diagnostic interface rather than becoming an invented experiment.

The new subprocess wrapper bounds wall time, prompt bytes and both output streams,
records failure evidence, and reaps its exact owned process. Human-written local
fixtures test timeout, malformed output, unexpected tool events and output floods.
This does not establish a fixed provider token cap or an exact HTTP request count;
CLI-internal transport behavior and subscription cost allocation remain distinct
from one logical invocation. Live dispatch still defaults to blocked until the
independent outer worker admits the task, data, source response and execution path.

Pinned the future coding role to **gpt-6-astra / medium**, existing ChatGPT login,
CLI 0.153.4, and a saved, hashed model-catalog entry. This is an explicit pre-score
choice, not retrospective proof of which default served coder-preflight-03.
The CLI binary and catalog are checked before use; actual readiness inspection
passes without inference. GLM-5.3 remains the researcher. No API fallback, new
model response or sandbox was launched. The pin is an identifier/runtime record,
not proof of an immutable provider backend. The official OpenAI documentation
guided the explicit model, catalog and ChatGPT-only settings.

Also fixed a billing-status bug demonstrated in a temporary ledger: an unmetered
dispatch could be omitted from invoice_reconciliation_complete, producing true
despite an outstanding hold. The flag now includes every pending job. No ledger
events, reservations or charge calculations were changed. The actual experiment
still has $0.00367902 token-metered estimate, $0.30 unresolved E2B holds and its
protected final $50. The budget journal remains hash-valid.

**213 offline tests pass** (23 new coding checks and one new accounting check).
These are implementation tests, not market scores or agent-learned improvements.
Still missing: original capture-clock/session proof, admitted real task manifests,
the complete Codex/Harbor/E2B trial driver and independent fixed market scoring.
No scored market comparison has run. Do not repeat passed canaries or source
searches to substitute for those missing pieces.

At 06:32 both exact Linode units were active/enabled with unchanged PIDs and zero
restarts; Polymarket observations were fresh and tennis discovery was healthy idle
with zero active pairs. Disk had about 80 GiB free. E2B inventory was zero and
the later local process check found no market worker. No source services changed.

### 06:20 UTC — GLM request stage binds common instructions and owned history

Implemented researcher_worker.py: it builds model messages from the unchanged
common initialization, an explicit public Train/Dev task and only the selected
arm's recorded evidence. It rejects other-arm/experiment records, hidden-Test
feedback, unrecorded human advice, future/reordered history and changed request
packets. Reset can retain within-task feedback but not earlier-task records;
Archive and Learn can retain prior learning records. Transfer feedback cannot
flow to later tasks, and guide updates require owned evidence and Learn's
learning phase. Before any records exist, all three initial messages are identical.

The single-dispatch function binds input/code/model/limits, reserves token-based
maximum cost, preserves the first response, settles terminal usage even for an
invalid proposal, and never automatically resamples. Mock transports are forbidden
from writing the real experiment ledger. Its real GLM transport uses the existing
model, tokenizer revision, high-effort template, seed and no-retry route. **Live
dispatch is blocked by default:** independent outer-worker data/admission checks
are still missing and must not be replaced by a researcher-supplied flag.

The first local tokenizer check failed before inference: the installed Transformers
Mistral-regex helper called HF model_info despite local_files_only=True. Loading
the exact cached snapshot directory fixed that code path without changing the
model or template. A second check with network calls patched to fail succeeds:
the original canary token IDs are reproduced exactly, and Reset/Archive/Learn
each produce the same 1,522-token initial fixture request. This is offline
tokenization evidence, not a new canary response or a market result.

**189 offline tests pass**, including 18 new request/accounting tests. No new
provider inference or sandbox was launched; the $200 budget and protected final
$50 are unchanged. Data provenance, actual task admission, subscribed coding-model
pinning, Codex/Harbor/E2B trial composition and independent market scoring remain
unfinished. Source/task materialization is not certified by this input projection.
The new module cannot yet execute the whole research loop by itself.

The 06:08 feed check found both units active/enabled with unchanged PIDs and zero
restarts, fresh actual Polymarket observations and healthy idle-tennis discovery.
Server free space remains about 80 GiB. No local market worker was present and
the ledger still reports $0.00367902 metered estimate plus $0.30 unresolved holds.

### 06:03 UTC — sequential prediction runner and durable output log

Implemented prediction_stream.py and prediction_candidate_server.py. The trusted
runner validates prior-date Train and game-disjoint evaluation inputs, sends
training examples once, then releases one evaluation feature row at a time.
It accepts only a matching finite prediction, appends/fsyncs its hash-linked
record, and only then releases the next observation. Evaluation labels, future
endpoints and unrecognized fields are rejected before candidate access. A failed
commit stops the stream. The completed log is read back and checked before a
completion receipt. Missing predictions cannot be called a completed trial.

The bounded persistent subprocess transport has been exercised with local,
human-written protocol fixtures, not model-generated code. Tests cover early
exit, oversized/multiple output lines, timeouts and exact owned-process cleanup.
An exited-process-group cleanup race was found and fixed; live kill failures are
not ignored. Bounded protocol traces preserve malformed-output diagnostics.
The production launcher refuses Mac/nonroot execution and uses the previously
tested E2B Linux network-namespace/unprivileged pattern. The outer worker must
still create private root-owned input files and kill the entire sandbox in its
finally block; process-group cleanup alone cannot contain escaped descendants.

**171 offline tests pass.** This new streaming path has NOT yet been verified in
a real E2B market trial. The common-context/model-request stage, exact coding
model pin, cloud/Harbor integration, fixed scorer and data-provenance gates remain
incomplete. No scored market experiment or new paid call occurred. The existing
5,213 numeric examples remain diagnostic only. This is host-written execution
infrastructure, not a learned researcher improvement. See EXECUTION_STREAM.md.

At 05:54 both collector units were healthy with unchanged PIDs, zero restarts,
fresh actual Polymarket observations and fresh idle-tennis discovery. About
80 GiB remained free on the server. Local process check found no market worker;
the 06:03 E2B listing returned zero visible sandboxes. Budget remains $0.00367902
token-metered estimate plus $0.30 unresolved holds; final $50 is untouched.
One bounded additional JS/TS/Go source search in the sports project found no
matching historical Kalshi collector. Do not keep repeating source searches.

### 05:47 UTC — historical replay now produces checked numeric examples

Built label_materializer.py and added a per-market quote segment to the replay.
A temporary one-sided book now breaks the continuity of any example spanning
that interval, even when subscription sequence numbers remain valid. The
materializer uses decision-time features and the first observed entry/future
endpoints within explicit timing bounds; it never fills missing endpoints with
unchanged prices. This is a host-written data-infrastructure change, not agent
learning. The old replay and its source snapshot are preserved unchanged.

Fresh local diagnostic replay-segmented-01 processed the two already-copied,
hash-verified hours: 6,181,609 raw records and 4,074,186 valid two-sided updates.
labels-diagnostic-01 used a predeclared metadata subset of 20 contracts / 10 games,
with diagnostic settings of 60-second horizon, 1-second entry delay, 5-second
endpoint lateness bounds, 10-second quote-gap bound and 10-second sample interval.
These settings are NOT the frozen scientific target or a controller decision.

The output contains **5,213 examples from 14 contracts / 7 games**. Of 5,521
scheduled decisions, 308 were excluded: 82 continuity breaks, 108 quote gaps,
21 late entry endpoints, 17 late future endpoints and 80 recording-tail cases.
A separate read-back audit checked all 14,454 referenced source endpoints and
recomputed every output feature/label plus timing and count reconciliation.
It passes. Source metadata, specs, code snapshots, claims and hashes are saved
in the permanent run directory. No sports-project strategy results were used.

**150 offline tests pass**, including real replay-to-materializer one-sided-gap
coverage and future-price-change invariance of decision features. These tests
and numeric data checks are NOT scored research experiments. Collector clock /
session provenance, final game/split audit, the fixed external scorer and the
isolated research worker remain incomplete. Gross endpoint price changes omit
fees, slippage, position limits and fill uncertainty; no net PnL was computed.
No model inference or paid sandbox was launched in this continuation.

At 05:36 both Linode collector units were active/enabled, with unchanged PIDs,
zero restarts, fresh Polymarket observations and fresh idle-tennis discovery.
Server disk had about 80 GiB free. Local process inventory had no market worker;
the later E2B listing returned zero visible sandboxes. Budget integrity passes:
$0.00367902 token-metered estimate and $0.30 unresolved holds, not extra spend;
the final $50 and the common initialization hash are unchanged.

### 05:33 UTC — renewed eight-hour window; historical capture is primary

User approved using the existing Linode history for Train/Dev and asked for
another eight-hour work window. Updated the existing heartbeat in place; the
current report deadline is **September 7, 13:33 UTC / 09:33 New York**. No
duplicate automation, worker or collector was launched. The combined $200 cap,
protected final $50, controller model and source-server boundaries are unchanged.

Saved the read-only findings in HISTORICAL_DATA_INVENTORY_2026-09-07.md. Kalshi
daily manifests report 24 hourly files on every day August 26–September 6.
This history, not the newly started tennis feed, is the primary Train/Dev source.
File completeness does not establish valid book continuity or capture-clock
provenance. The proposed date split is not yet frozen. Previously studied sports
history is learning/diagnostic data; later untouched games remain reserved for
final evaluation. The report must distinguish unfinished final evaluation from
actual historical results. Scored experiments remain zero at this scheduling
update, with no new paid calls.

### Eight-hour execution window — report due September 7, 13:25 UTC

The user authorized continued experiment work for the next eight hours, starting
around 05:25 UTC. Updated the existing heartbeat in place; no duplicate automation
or collector. EIGHT_HOUR_PLAN_2026-09-07.md fixes the new report deadline at
13:25 UTC / 09:25 New York, replacing the older September 8 deadline. Combined
$200 cap and protected final $50 are unchanged. No controller model was switched.
No paid calls were launched by this scheduling update. Data and worker gates
still apply; report actual results or precise incomplete status at the deadline.

### 05:22 UTC — split-boundary checks and failure-exit fix; no new paid calls

Added `split_manifest.py` and 22 offline regression tests. It checks declared
whole-game/task separation, market-to-game identity, future feature timestamps,
label horizon/receipt availability, earlier-date fitting, duplicate observations,
and permanent Test exclusion from later Train. A public projection contains
only Train/Dev metadata and salted Test commitments; private Test indexes/nonces
remain runner-only. It refuses verified-live evidence claims: structural metadata
checks do not establish collector provenance, accurate labels or a working
researcher sandbox. No real dataset/split was frozen and no live label was made.

Fixed a control-flow issue in `e2b_coder_probe.py`: a failed isolation assessment
previously printed `passed=false` but could exit successfully. It now persists the
assessment, raises, and still kills the exact sandbox in `finally`. Four added
offline tests cover strict boolean checks and a fully mocked failed run with
preserved assessment/failure/cleanup receipts. No cloud preflight was repeated;
the earlier passed component artifacts remain unchanged. This is a host-written
infrastructure fix, not an agent-learned improvement.

Full offline suite: **129 tests passed**, including archived prototype fixtures;
scored market experiments remain **0**. The common initialization hash is unchanged.
At the 05:16 health check, both Linode services were active/enabled with the same
PIDs and zero restarts, Polymarket observations were fresh, Kalshi tennis had
fresh discovery with no active pairs, and 77.85 GiB disk space was free. No local
market worker or visible E2B sandbox was running. Ledger integrity passes; costs
remain $0.00367902 token-metered estimate plus $0.30 unresolved E2B holds, not
spend. Final $50 is untouched. Data provenance, actual label materialization,
exact coding-model pinning and live trial-worker integration remain incomplete.

### 05:04 UTC — live feed verified; real coding/execution preflight completed

Scored market experiments: **0**. No claim of prediction or researcher improvement.

The actual subscribed coding component returned code (7,500 input / 394 output
tokens). The first two invocations failed local configuration validation before
inference; their fresh-ID artifacts are preserved. The third completed once.
Its initial assessment mistook a CLI capability warning for a tool call; an
append-only review corrected the classification without resampling the model.
Subscription allocation remains unknown, not free compute.

The resulting code was executed on E2B, not on the Mac. Its 10 independent math
checks pass. The initial provider-network configuration did not prevent the
TCP-connect probe, so it was not accepted as demonstrated isolation. Adding a
Linux network namespace blocked the connection. A subsequent instrument fix
checked namespace interfaces instead of the inherited sysfs mount. Final probe
`e2b-coder-preflight-03` passes: only loopback, UID 65534, no supplementary groups,
no privilege elevation, blocked public IPv4 connection, no host files or paid
provider keys. These are execution checks, not proof against every sandbox attack.
All three exact sandboxes were killed; final visible E2B inventory is zero.

Costs: Tinker token-metered estimate remains **$0.00367902**. Three E2B requests
have a combined **$0.30 reservation**, not reported spend, pending provider runtime
billing. Known terminated sandboxes must not be mistaken for running workers
because their accounting state still awaits reconciliation. Available capacity
after those holds is **$199.69632098**; the final $50 remains protected. 103 offline
tests pass, including archived prototype tests; this is not a research score.

Data checks found a real remaining dependency: the historical native Kalshi
collector is on `173.255.234.236`, identified by the existing read-only sync script.
Direct SSH was denied; no alternate credentials or access bypass were attempted.
Its capture-clock/session implementation is not yet verified. The alternative
Kalshi tennis REST collector only started today and currently has discovery
records but no active-pair snapshots, so it cannot provide multi-day Train/Dev/Test.
Do not relax those gates to manufacture an immediate score. Need a permitted
collector-code/provenance export or a sufficiently long independently audited feed.
The full market task materializer and researcher/coder trial worker also remain
to be integrated; the component preflight is not that complete pipeline.

Both existing Linode collector services are running, boot-enabled and configured
for automatic restart. Polymarket US real observations are arriving. Details:
[LINODE_FEED_STATUS.md](LINODE_FEED_STATUS.md). The existing heartbeat is now
**Market RSI and Linode feed health**, every 15 minutes. At the original research
deadline it stops research and paid dispatch, but continues feed-health checks.
The separate daily backfill automation and all healthy server services were left
unchanged. No new server, public endpoint, live trade or duplicate collector.

### 04:46 UTC — earlier RSI lessons carried into the common starting contract

Read the earlier handoff and weekly report, including their corrections. Saved
the runner-only source note in PRIOR_RSI_LESSONS_2026-09-07.md and distilled
general procedures into COMMON_RESEARCH_START.md. All Reset/Archive/Learn arms
receive the same human-authored prior; only their NEW cross-task memory differs.
No old task, trajectory, checkpoint, benchmark answer or score is included in
the model-facing text. Human corrections are not counted as agent learning.

The exclusive common-initialization.json manifest is in the current run root.
Common text SHA256:
`2cfbecbb97021eac19e3c159d1c7050a98b0b4d9f6de6e57f5e6b76d9aa57430`.
research_context.py rejects changed text/provenance and gives identical common
system instructions to all three arms. Nine new tests pass; 96 total offline
tests pass. Actual researcher/coder worker integration and evidence isolation
remain required before scoring; the loader alone is not a sandbox or full worker.

Updated the existing automation to require these files and the worker-integration
gate. Model, scope, budget and schedule are unchanged. No paid calls or sandbox
launches were made for this lesson transfer. No new research result is claimed.

### Previous execution milestone

Latest milestone: the first real GLM-5.3 canary passed. One response, 197 input
and 224 output tokens; metered $0.00367902, invoice not yet reconciled. Its
$0.10049022 maximum reservation was released on terminal usage evidence, not
reported as spend. Remaining combined capacity $199.99632098; final $50 intact.
Zero E2B sandboxes were visible; none created by this pilot. 87 offline tests pass.

Built a cross-file replay adapter and caught a convention error before scoring:
the source ETL declares `no` prices to be YES asks. The initial standard-NO replay is
preserved as an adapter failure, not a source-data result. Corrected one-hour
replay yields 536,914 two-sided updates across 645 markets, with invalid states
excluded. Collector/session/clock provenance and complete task splits are still
required; no scored research experiment or profitable-strategy claim yet.

The preceding 48MB closed raw hour was copied read-only and checksum-verified.
Cross-file replay then completed: 6,181,609 records, 4,074,186 valid two-sided
updates across 645 markets. Missing anchors, two gaps/resets and 55 invalid book
states remain explicit exclusions. This is an input diagnostic, not a research
score or proof of continuous coverage. The canary and cross-file replay source
copies match their pre-run hashes.
Next: collector provenance, sealed market task manifests, coding/execution isolation,
then baseline and learning arms. Details and exact run paths: RUNBOOK_2026-09-07.md.
The existing automation is now ACTIVE with corrected instructions and the new
combined cap; it does not repeat the already completed canary.

The user authorized $100–200 for the entire experiment. New combined hard cap:
$200, with $50 protected for final comparison and $20 for diagnosed failures.
The active scope is PILOT_PROTOCOL_2026-09-07.md: real Kalshi markets, GLM-5.3
research controller and Codex coding. The internal-market/MLAgentBench-first
design below is superseded, not an approved alternative.

Read-only checks: Tinker account supports `zai-org/GLM-5.3:peft:262144`;
Codex CLI 0.153.4 is signed in through ChatGPT; Tinker/E2B credentials exist
without being exposed. No research worker was found in the local process check.
An unrelated sports-project SSH evaluation was left untouched. My stalled
read-only git check was stopped; no source reset, deletion or push occurred.

At the initial access-check entry, no sampling/training/E2B job had started and
the automation was paused. The milestone above supersedes that setup status.

## Historical entries below

## Latest priority: focus on the LLM researcher

User clarification: "lets focus on llm researcher now." Keep the three arms and
transfer test, but prioritize an existing research-agent benchmark subset for
the first actual comparison. Investigate MLAgentBench/MLE-bench task/runtime
requirements, choose a feasible subset BEFORE outcomes, and preserve native
scoring. Do not choose tasks because an agent already scored well on them.
Trading PnL is a later application, not the current objective. A new benchmark
paper/public release is not part of the present work. The virtual prediction
market remains an experiment-selection mechanism, even on nonfinancial tasks.

Next sequence: external benchmark adapter and restricted LLM canary -> original
researcher baseline -> learning episodes -> frozen-state transfer comparison.
Market-feed repair is secondary and must not consume the entire pilot. The
current Brier-only study scorer is not yet an external-benchmark integration.

Latest completed software verification: **61 tests passed**; the three-arm
lifecycle fixture is `artifacts/llm-study-fixture-20260906-01/`. That fixture has
zero LLM calls and fabricated scores, not a research finding. No actual LLM
research episode has run yet. The subsequent read-only check found Claude Code
2.1.222 signed in through the existing claude.ai Max account. Effective isolation,
model provenance and no-extra-charge execution still need verification. No
research worker was active at the process check; no paid or duplicate run began.

## Current direction: LLM research learning (September 6 evening ET)

The user approved `RESEARCH_PROTOCOL.md`: study whether the LLM researcher gets
better on NEW tasks, not merely whether one downstream market model improves.
This supersedes the predictor-only research question and the older next-work
ordering below. Preserve the older entries as historical records.

Implemented `agent_study.py` on top of the existing experiment component:

- Three separate arms: reset memory + average forecasts; learned memory +
  average forecasts; learned memory + market selection.
- Versioned, evidence-linked researcher memories with a fixed common LLM/core.
  The fixed arm cannot update memory; other arms cannot borrow its competitors'
  experience. Final-test feedback cannot enter learning.
- Frozen task inventory, disjoint declared game/source groups, learning-before-
  transfer time checks, public-input allowlist and identical per-task baseline.
- Last-state freeze before transfer. No checkpoint inheritance across tasks.
  All final submissions must be committed before the one-time scoring claim.
- Complete paired task-level scores. Researcher-invalid submissions use the
  baseline fallback; infrastructure-unknown outcomes block a complete headline.
  Equal resource ceilings and usage receipts; no inherited paid budget.

These are trusted-runner lifecycle checks, NOT an autonomous LLM executor or
OS sandbox. Game group/timestamp commitments still require raw-data verification.
The module rejects prospective evidence claims until those independent execution
gates exist. No real LLM research episodes have run. No LLM weight updates.

Next work for the scheduled continuation:

1. Finish a restricted researcher/forecaster adapter with raw-response and usage
   receipts. Claude Code 2.1.222 is installed; its current authorization/model
   and effective isolation still need verification. A version check made no
   inference call. Do not assume prior authentication remains valid or charge an
   API. No real study input should include this conversation or prior hints.
2. In parallel in the work plan (not a request for delegated agents), build a
   valid task materializer from the sports source. Resolve raw replay coverage
   and timestamp provenance before scoring. Previously inspected slices stay
   diagnostic. Do not spend the entire pilot chasing the missing historical
   model; a clearly named new common baseline is acceptable.
3. Freeze a small learning/transfer task manifest and exact LLM/core/call/compute
   contract; run an access/format canary, then the three actual arm trajectories.
   If live access or real-data validity remains unavailable, complete the safe
   components and report the dependency; do not invent agent learning results.

The existing `market-rsi-two-day-pilot` automation was updated in place to this
direction. Its schedule and September 7 evening ET reporting deadline are
unchanged. No duplicate automation or paid job was created.

## 2026-09-06: framework started

Implemented a local, dependency-free pilot runner and logistic learner adapter.
The first 24 tests pass. A two-round fixture smoke run completed: three children
per round, forecast commitments, virtual-market settlement, exact paired row
scoring, and actual checkpoint inheritance. These are **fabricated-data software
tests**, with **zero independent forecaster/model API calls**. They are not new
market results and not evidence that the market selector improves research.

Artifacts: `artifacts/fixture-smoke-20260906-01/summary.json`. Source was further
hardened after this fixture run, so its frozen source hash must not be reused;
run a fresh fixture ID for subsequent verification.

## Source recovery

- Read-only GitHub access succeeded. Reference commit:
  `cdb3b0f108ff080626817fe393b41bd700b98014` in the user's private
  `Estelle-LH/prediction-market-research` repository.
- Recent MLB/NFL model scripts are absent from that commit and the local
  checkout. Historical 0.879/0.888 AUC values remain un-reproduced.
- Read-only SSH to `root@173.255.231.4` succeeded using the existing identity.
  Use BatchMode, StrictHostKeyChecking=yes, ConnectTimeout=8. Do not copy keys,
  modify server files, stop capture processes, or open a public data endpoint.
- Confirmed `/opt/d10/research/2026-09-05/manifest.json` says 24 hours and
  complete_day=true. Its note explicitly warns that games cross UTC midnight.
- Verified normalized columns: ts_utc, ts_ms, venue, market, outcome, bid,
  bid_size, ask, ask_size, mid, spread. `markets_YYYY-MM-DD.csv` carries league,
  matchup, outcome_label, game_start_utc, market_slug.
- Read `/opt/d10/bin/etl.py`, SHA-256
  `584c7682d9d6ed331bc192da31e75890b7fc4158f4082137f2e2c028b6b1bf8b`.
  Normalized ts_ms comes from raw envelope `t`, NOT message `msg.ts_ms`.
  A checked raw record has envelope time 1788566400035 and exchange message
  time 1788566399991. This supports distinct clocks but does not by itself
  establish the collector's exact receive-time semantics.
- The ETL skips malformed raw JSON, initializes book state anew per day, does
  not check stream sequence continuity in the examined function, and only emits
  nonempty changed two-sided books. Consequently a quiet normalized interval
  cannot by itself prove that the quote remained valid or that capture stayed
  connected. Raw coverage/gap checks are necessary for 250ms labels.

## Next work, in order

1. Add and test a raw-stream validator: receive/exchange clocks, snapshot start,
   sequence continuity, reconnect handling, and explicit observation coverage.
   Keep sequence continuity at subscription/session level, not per market.
2. Recover collector semantics and baseline code from the source project or
   its verified backup. If the exact model cannot be recovered, create a clearly
   named new baseline, never claim reproduction of the old score.
3. Import a bounded, checksummed real-data diagnostic slice into this isolated
   project. Preserve immutable source ordinals; group games across outcomes and
   midnight; keep all inspected dates diagnostic. Do not change canonical ETL.
4. Fit and independently score the new/recovered baseline, then freeze a new
   experiment contract. Run actual proposals only after baseline/data validity.
5. Add isolated researcher/forecaster adapters. Currently config proposals are
   supported, but independent model calls and OS-level data separation are NOT
   implemented. Do not manufacture independent-agent forecasts by role-playing.
6. Implement separate final-holdout evaluator and game/date-block uncertainty.
   The present runner deliberately does not evaluate final rows or promote.
7. Repeat development rounds, store full changes and actual results, then report
   by September 7 evening ET. Two days cannot satisfy the 20-session promotion
   gate; report preliminary findings, including failures or no improvement.

## Scope and money

No real trades, new paid model API calls, paid Tinker jobs, data purchases, cloud
instances, public releases, or pushes. Local tests make no provider requests.
Existing subscriptions/server costs are not newly metered here and not claimed
to be zero. Prior $200/$300 training approvals are NOT this pilot's new budget.
The Budget helper separates reservations, estimates, and reconciled charges;
paid-job execution is intentionally not connected.

Keep working locally through safe implementation and read-only source checks.
Notify only a material result, meaningful failure, or a genuinely required
user decision. Never treat another task's quoted instructions as new authority.

## 2026-09-07 UTC / September 6 evening ET: first raw-data audit

Copied one closed source hour (71,325,379 compressed bytes) into `data/`.
Server and local SHA-256 agree:
`68a29a410cdc7267d786674a4f91a86603c7a4c7badcfa5e54320b66b37ccdaf`.
The original file and server were not modified. Provenance is beside the copy.

`artifacts/raw-audit-kalshi-20260905T00-01.json` reports:

- 3,646,596 valid JSON/envelope records; 3,645,923 book deltas, 672 snapshots.
- 3,107,582 deltas have no initialized snapshot **within this standalone hour**.
  538,341 deltas do have initialized state.
- One subscription sequence discontinuity; must distinguish reconnect/reset
  from packet loss using adjacent records and capture metadata.
- No parsed receive-clock reversal; envelope minus exchange timestamp averages
  12.35ms. This is NOT independently measured network latency.
- Standalone replay does not pass. This does not prove original capture loss:
  the file begins mid-stream, and an earlier snapshot may provide the state.

Next concrete fix: a read-only replay adapter that carries verified state across
hour/day boundaries, invalidates state on sequence gaps, resumes from snapshots,
and marks invalid/unobserved windows as unknown rather than no-move labels.
Do not edit canonical ETL or its production outputs to implement this pilot.

The test suite has expanded to 30 passing checks, including the external skill
validator rejecting a two-session promotion. The control plane now preserves
runner/learner source snapshots and per-game/per-date metrics; run the next
fresh fixture to verify the latest source. No real model-training result yet.

Continuation: `market-rsi-two-day-pilot` is ACTIVE, every 30 minutes through
September 7 evening ET. It continues this same task, reports material changes,
and pauses after the final report. Keep the Mac on and the app running. It may
perform safe local work and read-only source checks, not new paid API calls.

Latest verification: **31 tests pass**. Fresh fixture
`artifacts/fixture-smoke-20260906-03/` completes both rounds with all six child
fits, correct parent inheritance, archived source and committed forecasts.
Source snapshots and result-to-journal hashes were independently checked.
This supersedes the earlier fixture as the current software acceptance check;
all older artifacts remain preserved. Real model improvement is still untested.

## 2026-09-07: controller harness v3 accepted with logging

The controller is no longer a one-shot 4,096-token form. GLM-5.3 remains the
decision maker; Codex supplies a bounded multi-turn workbench. Per-turn model
input/output limits are 65,536 tokens, with separate 262,144 input and 65,536
output cumulative caps, 12 turns, 32 tool calls and three candidate executions.

The next study uses one continuing Archive lineage. Archive is the learning
mechanism: GLM sees its own complete prior research record and freely chooses
what to do next. The former separate Learn arm and controller-written learned
guide are retired. The fixed read-only guide describes available tools and
integrity boundaries; it does not prescribe an algorithm or action order.

Formal diagnostic canary `controller-harness-formal-canary-20260907-07` passed:
9 model turns and 14 tool calls covered all 9 allowed actions, including the
fixed guide, own Archive, frozen literature, the non-exhaustive algorithm
catalog, four immutable candidate writes, two runner-owned Harbor/E2B executions
and one valid final decision. The three append-only hash-chain logs separately
record tools, literature and algorithm work and cross-check successfully.

Each E2B execution received 6,000 labeled Train rows and 300 label-free Dev rows.
The runner scored only after sandbox cleanup. Future Test was not used. The
exact local process reaped, the execution service has no pending request, both
cleanup receipts acknowledge sandbox termination, and the post-run E2B inventory
reported zero active sandboxes. All 24 frozen runtime-source hashes were
recorded. The full suite passes 697 tests.

The selected candidate improved relative MSE by about 2.50% on this old one-game
diagnostic Dev. That is not a research-performance, transfer, PnL or multi-round
Archive result. For `-07`, Tinker metered `$0.142423758`. Its two E2B `$0.10`
holds remain unreconciled reservations, not spend. The full new-experiment ledger
currently has `$0.714810258` metered Tinker cost and `$1.30` unreconciled E2B
reservations. Failed `-06` is preserved: it durably submitted a decision but
made one unnecessary post-submit turn and hit the turn cap. A deterministic
local terminal handshake and duplicate-execution guard fixed that protocol
failure before `-07`; no old ID was reused and no answer was resampled for score.

Formal research must start from freshly frozen tasks and new permanent IDs; no
old-task canary candidate, score or Dev feedback may enter it.

## 2026-09-08: fixed-H0 Archive carryover accepted

The two-session old-task diagnostic completed under one frozen H0. A0
`controller-harness-formal-canary-20260908-04` started from an empty Archive,
used 11 model turns, 17 tool calls and two E2B candidate executions, and selected
`candidate_v2.py`. Its metered controller cost was `$0.168413580`.

A1 `controller-archive-carryover-canary-20260908-01` read A0's immutable Archive,
recovered from one rejected malformed Archive-parent write, wrote and executed
`mid_persistence_refine_v1.py`, and selected it after 7 model turns, 8 tool calls
and one E2B execution. Its metered controller cost was `$0.322804116`. The
deterministic carryover assessment proves that the selected A1 source has the
exact A0 selected source as its Archive parent (`ancestry_depth=1`). Both
snapshots validate as a two-entry hash chain. The harness-profile hash and all
29 frozen runtime-source hashes match across sessions; neither session opened
Future Test. Post-run process checks and E2B inventory were zero.

This is mechanism evidence only. Both tasks are previously used diagnostics, so
their scores cannot support an RSI, transfer, PnL or model-improvement claim.
The next scientific step remains a fresh data/source freeze followed by the
precommitted A0-to-A3 Archive experiment.

The A1 preparation helper also exposed a local-name shadowing bug before any
model call or artifact-directory creation. A1 was prepared from the same frozen
lower-level functions without changing H0. Only after A1 finished was the helper
renamed and a regression test added. The full suite now passes 717 tests.

## 2026-09-08: formal Archive study frozen; paid dispatch awaiting data-transfer approval

The new three-round learning data is frozen in
`artifacts/archive-formal-learning-data-20260908-03/`. Round 1 has 6,000 Train
rows from 67 games and 1,443 sealed Dev rows from 5 games. Round 2 grows Train
to 9,943 rows and uses a fresh 1,500-row, 5-game Dev. Round 3 grows Train to
13,943 rows and uses a fresh 2,400-row, 8-game Dev. Every Train label becomes
available before the current Dev starts. The final Transfer population remains
unmaterialized and unopened; its pre-bound selection rule is frozen instead.

The formal study ID is
`archive-formal-self-improvement-20260908-01`. A0 persistence, the fixed Codex
H0 harness, GLM-5.3 controller identity, source manifest, prospective lifecycle,
Archive format, budget, and exact Round 1 input hashes are frozen. The Round 1
hard upper is `$2.47028224`; the learning bucket had `$119.90` available at
preparation. E2B reservations are not reported as spend. New terminal E2B
metering now converts a `$0.10` upper hold to measured runtime cost after
acknowledged cleanup; two live metering canaries passed with zero remaining
sandboxes. The full suite passes 734 tests.

No formal model call or sandbox execution has started. The external dispatch
was blocked because it would send the locally collected 6,000 labeled Train
rows and 1,443 label-free Dev feature rows to the Tinker-hosted GLM, while
candidate code and permitted rows would be processed in E2B. Explicit approval
of those data destinations is required before dispatch. At the block, there was
no formal process, no active E2B sandbox, and no new formal cost.

## 2026-09-08: first formal Round 1 attempt stopped before submission

After explicit approval of the Tinker and E2B data destinations, formal study
`archive-formal-self-improvement-20260908-01` dispatched Round 1. The controller
used 10 paid GLM turns, inspected the frozen data and guide, searched two public
papers, and independently executed two E2B candidates. Persistence matched the
Train-CV baseline; an imbalance/spread ridge correction was about 0.83% worse.

The provider returned a terminal tenth response selecting persistence, but GLM
spelled the final tool as bare `submit_decision`. The frozen adapter accepted
only `mcp__controller_tools__submit_decision`, so it raised a protocol error
before the broker received the decision. Codex surfaced a misleading generic
“high demand” message; the permanent provider receipt proves the response was
returned and metered. No Dev claim was made, no Dev label or score was opened,
and this study has no formal result. Its learning cost is `$0.278182338`,
including measured E2B runtime; the failed ID is permanent and will not be
retried.

The adapter now normalizes only known bare controller member names to their
frozen namespace; unknown tools remain forbidden. Protocol failures now record
their exact safe adapter message. The regression and full suite pass 735 tests.
A fresh source manifest and study ID are required before the next paid attempt.

Fresh study `archive-formal-self-improvement-20260908-02` verified that the
adapter fix works: the final `submit_decision` reached the broker. It still
stopped before submission because GLM put source/execution metadata inside the
`candidate_artifact` filename field. The broker correctly rejected it, but the
MCP server returned validation as a fatal JSON-RPC error, so Codex did not give
the controller a correction turn. Two candidates completed; no Dev was opened
and there is again no formal score. This attempt added `$0.532472000` of measured
learning cost and its ID will not be reused.

The harness now returns controller-originated `ValueError` validation as normal,
explicitly recoverable tool evidence. It also normalizes a decorated candidate
field only when its filename prefix uniquely identifies a candidate already
executed in that same session, while recording the raw-field hash and the
normalization. Infrastructure exceptions remain terminal.

Study `archive-formal-self-improvement-20260908-03` then completed a valid Round
1. The controller executed three candidates, selected `mid_persistence_v1.py`,
and the sealed 1,443-row / 5-game Dev score was exactly equal to persistence:
`0.0%` relative MSE improvement with full coverage. The result and all evidence
were finalized into A1 and the Dev was atomically promoted into Round 2 Train.

Round 2 read A1's full Archive and the enlarged Train, but stopped before any
candidate execution or Dev opening. Six completed turns had accumulated 213,136
input tokens; the next roughly 55K request exceeded H0's 262,144 cumulative
input cap. This is a harness-capacity failure, not a Round 2 score. The repaired
H0 keeps the 65,536 per-turn limit, raises the separately costed cumulative cap
to 786,432, and tells the controller to use at most 100-row targeted pages,
reserve room for execution/submission, use `archive_parent` across rounds, and
submit a filename without metadata. The worst-case controller upper becomes
`$4.61832192` per round, still inside the hard experiment budget.

Fresh fixed-H0 study `archive-formal-self-improvement-20260908-04` completed its
Round 1 controller session and selected `level_tie_mid_v2.py` after two Train-CV
candidates both tied persistence. Its one-shot Dev then stopped before sandbox
creation: `sealed_dev_runner` had derived the paid job ID only from the repeated
output basename `sealed-dev`, colliding with the prior study's already-used job
ID. The budget ledger correctly rejected reuse. No Dev score exists and the
active claim is not being mutated or retried.

The Dev execution ID is now bound to the permanent controller session as well
as the output basename. A regression test checks the exact namespaced ID, so two
studies can no longer claim the same paid Dev job.

Study `archive-formal-self-improvement-20260908-05` verified the unique Dev job
ID and again completed Round 1 at `0.0%` relative improvement. In Round 2, the
enlarged cumulative budget was available, but the next Codex request exceeded
the old 65,536-token per-turn input limit after five turns because every request
correctly carried the full Archive and tool history. No Round 2 candidate or Dev
score exists.

H0 now uses the GLM context as 196,608 maximum input plus 65,536 maximum output,
with 1,572,864 cumulative input tokens across the session. The adapter also
caps output by the actual remaining 262,144-token context. The worst-case
controller cost is `$8.44038144` per round; it remains separately budgeted and
well below the experiment hard cap.

## 2026-09-08: objective-discovery MVP and real Train grid

The separate Train-only objective-discovery stage now completes end to end on
a synthetic canary. GLM-5.3 used 8 turns and 19 tool calls to inspect data,
search literature, write three proposals, run three audits, compare candidates,
and freeze one valid objective. Its measured Tinker cost was `$0.179685864`.

Four hash-verified Linode archive days were then materialized from 8,401,097
book observations into 40,497 decision rows. The runner now exposes audited
point, mean, forward-EWMA and median targets at 60, 300 and 900 second horizons.
The moving fraction of the window-mean label rises from 2.05% at one minute to
6.24% at five minutes and 14.60% at fifteen minutes. This confirms that the old
one-minute target was mostly flat; it does not establish model improvement.

The real-Train objective controller then completed under the aggregate-only
egress guard. GLM-5.3 used 8 turns, 18 tool calls and 3 literature searches.
It compared one-minute and five-minute window means plus trade VWAP; the VWAP
proposal correctly failed audit because there is no verified trade stream. Its
first valid decision froze
`future-midpoint-window-mean-270-330s-v1`, a 60-second midpoint mean centered
about five minutes ahead. Metered cost was `$0.176343156`. All four append-only
logs and every egress event passed; no raw row, timestamp, market identity or
local path left the machine. No Dev existed during this selection and Future
Test stayed unopened.

The identical selection was promoted to a formal-learning contract without
resampling or changing the objective or evidence. The runner projected 91,369
historical rows and hash-bound them to that contract. A fresh three-round data
root contains 6,000/2,500/2,500 new Train rows and 3,784/3,298/3,232 separately
sealed Dev rows. Formal study
`objective5m-archive-formal-self-improvement-20260908-01` is prepared locally;
Round 1's hard upper is `$8.84038144`. No matching paid process or active E2B
sandbox exists.

Formal dispatch is now the only external blocker. It would send 6,000 labeled
historical Train rows to the Tinker-hosted GLM-5.3 and candidate code plus
permitted Train and label-free Dev features to E2B. Dev labels remain local
until one-shot runner scoring. This is broader than the aggregate-only
objective authorization, so it requires a separate explicit approval. The
dispatch was rejected before process creation; there is no new formal cost and
Future Test remains unopened. The full offline suite passes 798 tests and
`git diff --check` passes.

## 2026-09-08: objective-aligned Formal Round 1 completed, controller integrity failed

After explicit authorization, fresh study
`objective5m-archive-formal-self-improvement-20260908-04` completed Round 1 on
the frozen five-minute window-mean objective. The final repaired split contains
6,000 Train rows over four UTC dates and 3,921 sealed Dev rows from 14 whole
games on 2026-09-02. The builder assigns Dev by actual decision UTC date and
omits, rather than splits, games that cross midnight. Two earlier fresh study
IDs stopped locally before provider execution while this rule was corrected;
they produced no score and were not retried.

The GLM-5.3 controller used 14 turns, 20 tools, three literature searches and
three real E2B Train-CV executions. The best legitimate ridge candidate improved
Train-CV equal-game MSE by 1.78%. The one-shot sealed Dev result improved MSE
from `2.4275384979e-06` to `2.3703292947e-06` (`+2.3567%` skill), reducing RMSE
from 15.5806 to 15.3959 probability bps with 3,921/3,921 coverage. Future Test
remains unopened. Controller cost was `$0.553662864`; the four E2B executions
cost `$0.00117975`; total project effective metered cost after Round 1 is about
`$14.31855413 / $200`.

The selected A1 is quarantined from continuation. In turn 12 the controller
copied the already-executed `ridge_delta_type_v1.py`, added unrelated inert
metadata with hidden-reward/adversarial wording, and named it
`c4h_w2_child_v1.py`. Its Train-CV predictions and score hash are identical to
the legitimate parent. Thus the predictor score is real, but autonomous
controller integrity failed: a no-op change consumed an execution and was
selected for irrelevant reasons. The raw response is preserved; A1 will not be
silently replaced after seeing Dev.

Round 2 is blocked pending a new H0 with prediction-digest no-op rejection,
simple-parent tie handling, candidate semantic checks, structured-only Archive
carryover, injection canaries, and separate predictor-validity/controller-
integrity acceptance. The full offline suite passes 803 tests; exact processes
and active E2B sandboxes are zero. See `FORMAL_ROUND1_2026-09-08.md`.
# 9月13日：修复已发布，新会话03已启动

短编号修复已推送至自己的私有仓库，版本`pm-temporal-history-v0.1.1`，commit `2a9437a`。
03于16:41UTC启动，已成功读取当前检查结果。19条反馈保留原文和内容hash，DSHv1.4.0
不变。现在检查它是否能完成时间规则测试和第一份方案；不是训练，也没有新分数。
启动前原$200账本可用$160.020511594；本会话上限$8.44038144不是已消费。
# 9月13日最新：方案会话完成，复核发现仍需修改

03正常结束，约4分钟、计量$0.85、0次训练。编号接口已修好，controller自行完成时间
检查并保存方案。但它的“60秒目标”仍可能选到仅隔1毫秒的价格；要求的扫描仍是122个
文件，没有真正缩小。完整、简短说明见[本轮复核](TEMPORAL_SOURCE_REVIEW_2026-09-13.md)。
目前没有活跃controller或训练进程。原$200账本可用$159.17，不是钱花完了。

以下保留启动时记录，已由上面的完成状态取代。
# 9月13日接续：正在把方案变成具体执行任务

新的GLM反馈会话`temporal-feedback-controller-20260913-01`已启动。它需要修正目标含义，
并交出一个精确文件范围、输出和资源上限的下一步，不再泛泛要求六天全量扫描。
当前仍没有新的真实拟合。已确认还缺原始事件到训练grid的已验证转换程序；不是只改
一个时间参数。进度与有条件的时间估计见[开跑路径](EXPERIMENT_START_PATH_2026-09-13.md)。
