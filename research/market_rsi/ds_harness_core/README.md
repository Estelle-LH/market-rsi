# 固定版本公共统计与质量检查代码

来源：<https://github.com/Estelle-LH/data-scientist-harness>，commit
`df963b02f8e1fae7db4f4d99d34507e1f339b416`。这是明确选择的预发布提交，
不是声称上游已合并、push或发布。本目录五个 Python 文件与该提交逐字节一致。

Market RSI 接入 `moments`、`quality_checks` 和 `research_gate.guarded_research`。
本项目的显式毫秒grid适配器使用`feature_batch.py`；不伪造纳秒事件顺序，不把UTC日期
称作交易session。检查包围实际特征生成、归一化、模型拟合及评分callback。
数据行、目标与trainer公式未变，输入检查更严格。共享测试不能代替本项目真实源适配验收。
源码出处和五个 SHA256 固定在
`../data_scientist_harness/core_dependency.py`。

运行时不读取 LightHouse 或其他项目的目录，不自动下载或升级。每个新工作区保存一份
本地源码，并将版本及 hash 写入运行记录；修改或缺失时拒绝执行，不回退到旧实现。
旧工作区的冻结文件不改。未来升级由本项目单独决定并重新测试，不等待另一项目。

这是内部源码依赖，不是完整上游发行包；不冒充安装了同名 PyPI distribution。
若公共实现需要变更，先在共享仓库复核，再明确更新本项目的版本；不在此处偷偷改公式。
