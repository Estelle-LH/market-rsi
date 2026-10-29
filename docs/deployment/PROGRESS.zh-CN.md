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
| 规范五面与owner路径 | 新本地7/7，受影响的8组122项回归通过；native保护/原财务路由8项及fixture10项通过 | 独立mount/network与临时文件系统探针已写好；尚未实际Linux云测 |
| 主进程内核退出码 | 新本地12/12，涉及原memory/五面接线的退出码一致性 | Mac实际子进程wait；Linux pidfd后端为模拟，后代/容器未据此推断清空 |
| 私有Git回读适配 | 新本地14/14；实际原memory及新建Git仓库的真实blob回读 | 新只读工程实现，原归档写入器未在快照中；只核对明确声明的artifact，非真实科研归档准入 |

## 当前接线

五面联合收尾由工程自己构造真实财务验证器，不接受一个返回成功的财务占位回调。相同root、runtime和terminal绑定先后用于原memory、cleanup、公司终态/物理请求和财务；原owner锁贯穿验证。终态和请求共用一次实际联合审计，避免两次公司扫描。其后仍须配置独立原private-seal适配器，以及真实OS观测与完整task/Source/Native准入。

新增10项检查实际覆盖：前四面通过后，原财务固定历史拒绝和未结算行拒绝；runtime/terminal错接在财务前被拦截；active memory、缺raw、错误boot均不能提交停机；失败后清空所有可被误用的成功报告。数据库字节不变，持久drain保留，停机journal为空。私有seal和OS在这些输入中仍明确合成，没有完整财务成功替身。

18文件模式把原validation_epoch放在实际预算函数调用周围、同一把真实owner锁之内；拒绝后ContextVar恢复。原Reader是真实class实例，原方法/来源注册/缓存/装饰器保持原定义，入口与IO依赖额外收窄到独立manifest和受限Git。原32MiB/4096缓存上限不改；budget、clock、owner仍鲜读，extra集合不能扩大允许范围。12/16文件旧模式保留。

规范路径现同时接入memory、cleanup、公司/请求、finance及owner drain。原population回执和独立ledger目录保持原标签，财务使用artifact父目录manifest；其中population子集必须与其他四面逐行一致，遗漏、增加、哈希/大小变化及重复均拒绝。每个规范入口在Mac或不合格部署命名空间中先拒绝，再接触原路径。新的7项只验证这个契约及路由，没有在Mac探测或建立原目录，也没有冒称实际Linux文件系统通过。

原规范路径的native探针和启动器已经写好：仅在独立Linux代码目录执行，必须处于隔离的mount和network namespace；全新临时文件系统承载合成ledger、claims及drain，退出后清除。探针要求同ledger的实际竞争进程无法拿锁，前四原面通过后真实财务拒绝虚构历史、数据库不变、停机intent为空。8项隔离保护/原财务路由和10项联合fixture回归本地通过；实际Linux执行待单独具体云测授权，旧文件包授权不扩为新包。

新增private-seal只读适配先运行真实原memory，再核对声明的实际Git ref/commit、Source祖先、每个明确artifact的blob类型/长度/字节，以及HEAD和无暂存更改的index前后不变。14项在全新合成仓库中通过，覆盖同尺寸篡改、缺blob、错ref、无Source祖先、漏清单、暂存index、变HEAD及外部Git存储。它可作为同一真实drain内的明确回调；当前仅支持自有工程目录，规范Linux路径未启用。保存的118文件不包含原归档写入器，所以这部分明确标为新工程只读实现，不声称原collector已验收，也不读取真实私有Git祖先。

主进程退出码新增明确的父进程生产接口，只接受持有的真实Popen子进程，从内核wait状态取得退出码；不接受PID/JSON回执、不发信号、不启动进程。Linux实现要求pidfd并使用waitid(P_PIDFD)，缺少能力不降为按PID等待；Mac便携工程验证使用waitpid，不能算Linux原生通过。12项覆盖活动子进程、0/1/17和信号退出、别处已回收/缓存篡改/父进程身份改变，以及在真实drain下将实际退出码接入原memory和五面验证：真实0到达原财务拒绝，真实1不能复用成功memory。后代进程、Docker、账户结算和当前host身份仍明确待接。Python对进程返回码及wait接口的语义见[官方subprocess文档](https://docs.python.org/3.12/library/subprocess.html)和[官方os文档](https://docs.python.org/3.12/library/os.html#os.pidfd_open)。

## 已保留的工程故障

父进程联测首次暴露native探针的异常分类错误：真实原代码抛BudgetStop（RuntimeError子类），且消息带完整“no refund/reset”后缀。旧探针按缩短消息和基础异常名称匹配，会误报真实原财务拒绝。首失败和旧代码/包完整留档；修复为原 subtype及完整消息，新8项实际原代码路由回归通过，无预算/历史规则改动。旧具体云测请求撤回执行，修复后的V2精确包与18+1检查单另列，等待具体授权，不扩大旧批准。

原Reader发现此前把账本artifact父目录推断为源码仓库的错误：原Reader会把仓库内的回执当作未登记Git来源。新增11项首次1失败，原代码和日志保留；修复后11/11。源码仓库改为显式独立部署仓库，原ledger/population和历史Source绑定不改，原Source路由不作数据fallback。

此前也保留了输送校验、只读元数据、cleanup报告清理等首次失败和对应修复回执。不会用修改历史前缀、预算、模型、冻结划分、重试或科学断言取得合成通过。

## 云端与恢复

已完成的有限AWS检查在worker/容器/平台容器均0后停机，并实际回读stopped；EBS保留，BOOTSTRAP_ONLY和停止保护保留。最近这批五面/规范路径增量全部在本地执行，尚未上传或在AWS验收。旧clock探针只有host/config/clock树，未安装或准入完整三文件118候选；不把该探针当作新接线云测。

命令先写耐久intent，未知ACK查询原命令身份，不重发或另起owner。公开PR保持草稿、不合并，只含脱敏通用工具与说明；内部Source包、状态、云标识和私有Git祖先不发布。Devin只接触公开通用工具与合成brief，本轮无新Devin、模型或云操作。

## 下一步验收

按已准备的具体范围执行native Linux云测及idle/stop回读；上传新包目前等待单独授权，本地工程继续推进。继续补私有Git适配的规范路径与原归档协议确认、可信OS观测及完整科学准入；正式研究状态供应和跨主机接管须等用户明确切换，工程实现不等待原Supervisor回复。

可选计时03/04/05分别留档，默认关闭；已独立复现的批次/比较/停机观察仍含明确合成依赖。新送达的计时增量尚未计入本工程验收。完整科研耗时仍需要实际保存的比较结果、归档seal、最终memory/财务关闭和当前主机时钟；历史clock或digest形状不能替代这些端点。
