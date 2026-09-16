# Aggregate-only NFL Controller：实际运行结果

## 一句话

新的Controller workspace按设计工作了：GLM只看到Train汇总，没有看到原始行情或Dev/Final，
查了方法和文献后给出一份30秒feature-only A/B，并停在实验设计边界。它还没有证明新feature有效。

## 输入

- Harness：`dsh-v1.6.3`，commit `68d500a9be24eb277aa56d4dd442f48caf7bd565`。
- workspace：`artifacts/nfl-target-controller-20260916-01`。
- 六条findings：target-grid、same-support、表示/算法缺口、event-time候选、评估边界、下一步决定。
- 只含两次已完成Train实验的result/manifest/pre-score-lock精确副本与hash。
- 不含raw rows、比赛日期清单、Route-Dev、Final、既有Route-Dev分数或训练接口。

## 实际步骤

1. `inspect_harness`：确认`aggregate_only`、`training_allowed=false`、六条当前findings。
2. `inspect_sports_method_library(state_prediction)`：看到已安装方法与需要新增能力的方法。
3. `search_literature_live`：通过Crossref搜索NFL win-probability和state representation研究。
4. 第一次source read返回HTTP 202，失败被保留，没有伪装成已阅读。
5. 阅读nflfastR EP/WP/CP实现说明。
6. 阅读Yurko等人的nflWAR arXiv页面；Controller明确记录转移限制。
7. `record_research`：形成feature-engineering研究记录。
8. `acknowledge_current_findings`：逐条说明如何处理六条finding和还缺什么证据。
9. `submit defer`：因为aggregate workspace禁止raw input和训练，所以只提交下一实验方案，不训练。

## Controller决定

保持不变：

- target：`elapsed_30s_delta`；
- 16,632个15/20/30/45/60秒共同可用play；
- 3个rolling check blocks，每块21场；
- Random Forest：200 trees、depth 8、min leaf 50、max features 0.7、seed 23；
- 每个模型仍与自己的zero-change baseline比较。

只改变feature representation：

- score differential × elapsed-time exponential；
- possession × home-oriented field position；
- 同一个play开始到结束的历史state win-probability change。

它要求做按feature family的消融。事前主规则是：最弱fold要高于parent的5.8708%，calibration slope
在[0.9, 1.1]，逐场胜率至少75%。如果失败，下一次才单独测试HistGradientBoosting。

## 费用与系统行为

- 7个provider turns全部`metered_terminal`；无未解决账目。
- 账本effective cost从`$83.057743862`到`$83.342181194`。
- 本会话实际新增Tinker cost：`$0.284437332`。
- 启动前hard upper：`$8.44038144`；这是上界，不是实际花费。
- 会话结束后learning bucket可用`$43.310570174`；Final仍保护`$50`。
- 启动阶段本地运行时用了约10--12分钟导入并扫描`transformers/models`，期间没有provider call。
  文件读取持续变化，说明不是死锁。这个启动慢问题留给下一版Harness单独修，不改本次冻结运行。

## 我们学到什么

- aggregate-only边界有效：Controller能研究和设计，但不能偷跑训练或读Dev。
- 它这次比较保守：没有发明新算法，也没有请求新增XGBoost/GAM能力；先选择了feature-only实验。
- 这不是预测改善证据。真正的学习是否成立，要看下一次严格same-row A/B。
- Controller回复里提到“Harness bounded equivalent 128 trees”，但真实parent是200 trees。执行方不会
  静默改成128，否则parent就变了。新的sports runner固定200 trees。

## 下一步

`experiments/nfl_representation_ablation.py`把三类feature拆成一个唯一主候选、leave-one-out、
add-one和`k=2`敏感性。源码先测试、commit、tag、push，再用fresh ID跑opened Train。不会打开
Route-Dev或Final。

## 下一步后来实际发生了什么

精确源码已发布并完成fresh opened-Train运行。Parent完整复现。主候选的MSE相对parent改善
`31.66%`，63场中`98.41%`优于parent；但校准斜率`1.1310`超过事前上限`1.1`，所以正式记录为
“不支持”，没有事后放宽规则。

消融给出了更重要的定位：`state_wp_delta`单独相对parent改善`31.77%`；score×time和
possession×field-position几乎没有额外贡献。按照Controller原先写下的fallback，下一次实验保持
完整feature、target、rows和split不动，只测试固定HistGradientBoosting trainer。
