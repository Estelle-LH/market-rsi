# 9月12日：旧文件取回本机，费用复核通过

开始时，618个相关文件中有231个云端占位文件，读取旧账本和旧运行环境会等待。
没有证据表明这些文件丢失；没有为了继续运行而重写账本或跳过核对。

## 怎样取回来的

先阅读了Apple官方的
[startDownloadingUbiquitousItem文档](https://developer.apple.com/documentation/foundation/filemanager/startdownloadingubiquitousitem(at:))。
访问日期2026-09-12；直接打开方法文档及其Markdown版本，没有论文搜索。
该方法请求下载指定云端项目；请求返回不代表已经下载完。如果文件已在本机，也可能同步
云端版本。因此只处理已识别的本实验文件，下载后必须与原指纹核对，不能把API成功当验收。

先只请求父会话`workspace.json`，它恢复本机可读，SHA256与9月11日记录完全一致。
再请求此前报告列出的231个文件，范围仅是原实验账本回执及指定父会话文件，不请求目录，
不改变iCloud设置，不碰行情或隐藏Test，不运行下载后文件中的代码。

这一步也有两个执行问题，保留如下：

- 首次批量请求在范围检查处停止：报告中两个工作区路径是相对路径。修正只对这两个
  已列明文件作绝对路径转换，未扩大范围；该次没有发出批量下载请求。
- 第二次已执行下载请求，但保存“请求回执”时，JXA将空attributes参数桥接成NSNull，
  导致回执写入失败。没有因此重复请求整批；改用独立本机状态与完整账本核对验证结果。
  不声称保存了每个下载请求的成功回执。

## 实际验收

后续独立检查：同样618个文件，云端占位/缺失项为0。报告为
`artifacts/io-residency-20260912-02/report.json`，结果hash
`85e16f466bef8e79171d6ee8c418b0378e6142e0e1e9b73575e53bd48f27ddec`。
这只是本机状态检查；以下内容核对另外执行，不混为一项。

| 文件 | 取回后的SHA256，与既有记录一致 |
|---|---|
| 父workspace.json | `2cb7e29e5aacc9d77c94f57aa75e8713a69aa0f673a19094bd78bd24ff275e02` |
| 父source-study-proposal.json | `7ff30153bfdf984706e7efbb0a4c9e5088e63949ec41abe43f15aa66108d7587` |
| 原budget/authorization.json | `d5bcc2d00a3b574485252693c4ba07b3a4a3ab9e083ac3bbbc1d8b30e556a8f9` |

2026-09-12 17:02:08 UTC，原PaidBudget完整读取并核对授权、追加事件链和终止计量回执，
通过。审计前后journal文件hash相同，没有改变记录。608个metered terminal、5个历史
uncertain terminal、23个旧dispatched预留仍按原状态保留，不虚构结算，不把预留算消费。

| 原$200账本 | 本次核对值 |
|---|---:|
| 按token计量费用 | $32.790116510 |
| 含历史不确定额的有效成本 | $36.649022120 |
| 另有旧预留，不是消费 | $2.30 |
| 总可用 | $161.050977880 |
| learning可用 | $90.001491218 |
| final / repair仍保护 | $50 / $20 |

完整发票仍未对账，不能把token计量称为最终发票金额。本次新增Tinker调用/费用均为0。
审计凭证：`artifacts/io-residency-20260912-02/budget-audit.json`，结果hash
`dab103c10909eb48c644442d5d340f5e3b43d818044a170c79d09a9a4e08d81a`。
journal SHA256为`8828884467e43954ceff6aa31b80acea24b01cd70ae48ccf0d3e2edcb7c40678`。

## 尚未解决的范围

不是整个repo或所有历史工作区都已永久留在本机；iCloud仍可能再次移出文件。
新CPU环境不放在Documents下，但原repo和旧记录仍在原位置。没有改系统同步设置。
本次只核对父manifest/方案及账本，不等于完整父会话所有引用文件都已做新版本迁移验证。
付费SDK检查、新版独立工作区的历史导入、真实数据准入仍是下一步，不能因恢复文件就开训。

版本发布核对曾在Git archive读取时超时，未生成半份release。待原对象可读、push完成后，
原检查不变地重新运行并通过；没有增加时限、删检查或移动tag。
新release详见[当天工作记录](DAILY_LOG_2026-09-12.md)。
