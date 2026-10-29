# AWS + Docker 迁移进度

当前完成普通工程部署与独立接线验证；真实实验尚未迁移，生产停机未启用，没有实测科研提速。原 Supervisor 继续实验，本工程不读取或修改它的状态、进程或调度。

| 工程部分 | 已有验收 | 实际边界 |
| --- | --- | --- |
| AWS 普通部署 | 118文件、116 Python语法检查；宿主Python3.12.3与固定Docker镜像验证 | 代码和持久卷保留；最后云端回读为stopped |
| 公开通用工具 | 本地与AWS均137/137；Devin建立并执行其中17项元数据检查 | 公开合成输入，无真实科研/性能结论 |
| 原memory/cleanup/Python接入 | 46项在AWS通过 | 已鉴别原函数与明确合成依赖，完整科学准入另需验证 |
| 原owner派发排他 | 16项本地及AWS；真实竞争进程与原global flock | 耐久屏障、真实锁和相同身份恢复；无自动清除或另起owner |
| 原规范路径平台探针 | 本地/AWS7项与4个实际容器 | 只读挂载新合成数据；guest3.12.14和host3.12.3分别记录 |
| 原请求/可选计时03 | 用户具体批准后AWS19+11通过 | 计时默认关闭，完整依赖与最终端点未齐 |
| 原Linux clock候选 | 本地/AWS各19项及真实host/boot/新clock探针通过 | 原Mac接口实际失败留档；跨boot/续期拒绝；非完整候选Source准入 |
| 原evaluation终态和请求 | 本地14项与终态20项回归通过 | 四个实际原面同runtime/manifest并持真实drain；raw只哈希不解码 |
| 原财务与历史Reader | 核心12、请求行18、历史grant13、真实Reader13本地通过 | 固定历史前缀、固定split及授权未伪造，完整财务正例尚无 |
| 五原面联合收尾 | 新本地10/10，变更后的Reader13/核心12回归通过 | memory/cleanup/terminal/requests实际通过后，真实财务按原规则拒绝虚构历史；无停机intent |
| 规范五面与owner路径 | 新本地7/7，受影响的8组122项回归通过 | Linux正向只做路由截点/平台模拟；实际原规范路径文件系统验收待做 |

## 当前接线

五面联合收尾由工程自己构造真实财务验证器，不接受一个返回成功的财务占位回调。相同root、runtime和terminal绑定先后用于原memory、cleanup、公司终态/物理请求和财务；原owner锁贯穿验证。终态和请求共用一次实际联合审计，避免两次公司扫描。其后仍须配置独立原private-seal适配器，以及真实OS观测与完整task/Source/Native准入。

新增10项检查实际覆盖：前四面通过后，原财务固定历史拒绝和未结算行拒绝；runtime/terminal错接在财务前被拦截；active memory、缺raw、错误boot均不能提交停机；失败后清空所有可被误用的成功报告。数据库字节不变，持久drain保留，停机journal为空。私有seal和OS在这些输入中仍明确合成，没有完整财务成功替身。

18文件模式把原validation_epoch放在实际预算函数调用周围、同一把真实owner锁之内；拒绝后ContextVar恢复。原Reader是真实class实例，原方法/来源注册/缓存/装饰器保持原定义，入口与IO依赖额外收窄到独立manifest和受限Git。原32MiB/4096缓存上限不改；budget、clock、owner仍鲜读，extra集合不能扩大允许范围。12/16文件旧模式保留。

规范路径现同时接入memory、cleanup、公司/请求、finance及owner drain。原population回执和独立ledger目录保持原标签，财务使用artifact父目录manifest；其中population子集必须与其他四面逐行一致，遗漏、增加、哈希/大小变化及重复均拒绝。每个规范入口在Mac或不合格部署命名空间中先拒绝，再接触原路径。新的7项只验证这个契约及路由，没有在Mac探测或建立原目录，也没有冒称实际Linux文件系统通过。

## 已保留的工程故障

原Reader发现此前把账本artifact父目录推断为源码仓库的错误：原Reader会把仓库内的回执当作未登记Git来源。新增11项首次1失败，原代码和日志保留；修复后11/11。源码仓库改为显式独立部署仓库，原ledger/population和历史Source绑定不改，原Source路由不作数据fallback。

此前也保留了输送校验、只读元数据、cleanup报告清理等首次失败和对应修复回执。不会用修改历史前缀、预算、模型、冻结划分、重试或科学断言取得合成通过。

## 云端与恢复

已完成的有限AWS检查在worker/容器/平台容器均0后停机，并实际回读stopped；EBS保留，BOOTSTRAP_ONLY和停止保护保留。最近这批五面/规范路径增量全部在本地执行，尚未上传或在AWS验收。旧clock探针只有host/config/clock树，未安装或准入完整三文件118候选；不把该探针当作新接线云测。

命令先写耐久intent，未知ACK查询原命令身份，不重发或另起owner。公开PR保持草稿、不合并，只含脱敏通用工具与说明；内部Source包、状态、云标识和私有Git祖先不发布。Devin只接触公开通用工具与合成brief，本轮无新Devin、模型或云操作。

## 下一步验收

先建立原规范目录下的全新合成fixture与native Linux探针，验证同一ledger、真实flock、相同metadata视图及原财务拒绝，再按具体有限范围进行云测和idle/stop回读。并继续补原private Git seal、可信OS观测与完整科学准入；正式研究状态供应和跨主机接管须等用户明确切换，工程实现不等待原Supervisor回复。

可选计时03/04/05分别留档，默认关闭；已独立复现的批次/比较/停机观察仍含明确合成依赖。新送达的计时增量尚未计入本工程验收。完整科研耗时仍需要实际保存的比较结果、归档seal、最终memory/财务关闭和当前主机时钟；历史clock或digest形状不能替代这些端点。
