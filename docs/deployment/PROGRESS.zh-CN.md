# AWS 并行小步部署进度

2026-10-28：独立代码与环境部署已到118个普通工程文件。原Supervisor继续自己的实验；部署不向该聊天发消息、不要求冻结，也不等待回复。真实状态接管后置。

| 工程块 | 已验证结果 | 验证边界 |
| --- | --- | --- |
| 普通源码与host | 118文件哈希、116 Python语法、原launcher host检查通过 | 独立Linux候选；完整资源与科研准入仍未完成 |
| 原runner/guest | 三个实际公开用例及真实退出/清理回执 | 算术、安全探针、可恢复guest异常；无科研模型调用 |
| 公开工具回归 | 本地及AWS的Python3.12.3均137/137 | 包含新Devin只读元数据17项；网络/云回调是合成fixture |
| 原memory与Docker清理验证接入 | 本地合并38/38；相关检查也在AWS通过 | 原验证函数经来源校验后在独立合成目录实际执行；输入/源码/二进制输出哈希和清理条件均需满足 |
| Linux Python声明兼容候选 | 本地源码级8/8；AWS与上述检查合并46/46，并实际通过Python3.12.3主机核验 | 候选恢复已测量的Linux字面量，同时保留实际解释器核验；原历史解析器未改 |
| 原owner锁与持久停机屏障接入 | 本地及AWS新16/16，使用真实竞争进程与flock | 复用原全局锁位置；原函数的preflight为合成探针，停在claim/clock/budget/client之前；未启动科学owner |
| 规范路径容器验收 | 本地与AWS新增7/7；4个实际容器场景通过 | 只读挂载新建合成材料，原memory函数在原规范绝对路径读回；两个接受、两个拒绝，全部字节保持不变 |
| 原物理请求与完整反馈接入 | 本地及AWS新19/19 | 原生成/count/响应/raw哈希/完整user反馈与Controller公共panel恢复函数实际执行；只启用普通proposal，完整task与其他route尚未准入 |
| 可选批次计时补丁离线审阅 | 独立本地及AWS11/11 | 默认关闭，原batch审计一次；回调位于原财务/清理/Native检查之后，依赖的合成stub明确标注，不能当作这些验证已接通 |
| 原公司批次terminal接线 | 新本地20/20，未加入本次云包 | 完整wave2..4/rolling4原退出、checkpoint、UUID归属、physical interval/并发及持久事件验证；其他路由与实时OS来源仍待接入 |
| 原evaluation请求与terminal联合接线 | 新本地14/14，修改入口的原20项回归通过，未云测 | 两公司wave/rolling4同一metadata/runtime下，实际原memory/cleanup/terminal/physical_requests与真实drain相连；财务/私有Git/OS来源仍未验 |
| Linux boot时钟候选 | 新本地19/19；真实Linux探针待具体新两文件上传审批 | 只增加Linux身份来源；原Darwin体与validate/capture AST不变，保持窗口与origin；本地host/kernel明确为合成 |
| owner-clock计时修订04 | 独立离线11+7通过，未云测 | 第四参数来自原checked owner.clock，不接受构造器自造时钟域；03及其AWS结果原样保留 |
| 停机链路 | 原memory、清理或请求拒绝会阻止stop；执行身份不符会阻止验证；重复key不重复提交；丢ACK不重发 | 已接真实lease和持久屏障；普通proposal原请求及本地完整evaluation四原面分别有明确证据；finance/private-seal和真实OS来源仍未验，生产停机未启用 |

只读元数据适配器按独立manifest检查规范路径、文件大小和哈希，拒绝未列明/符号链接/重复JSON字段/非有限数字，不跟随JSON里的目标。Devin只获得这个通用工具与合成brief，不接触内部源码、状态、云绑定或凭据。

原memory接入验证活动步骤、bookkeeping失败、较新terminal、防回滚、待结算/清理错误、private-seal来源和成员匹配等实际分支。输入全部为新建合成材料，这些检查不是实际费用结算或原始私有Git回读证明。完整生产接线仍须复用对应路由的真实原验证器和真实派发排他；不得把六个digest或结果JSON当作原协议。

清理适配保留并修复了三个实际缺陷：已列入清单的调用目录消失后被当成零调用、悬空目录链接被当作不存在、后续memory失败时残留旧清理成功报告。原清理函数体保持不变；适配层要求清单内回执全部由原验证器消费，并在每次验证前清除旧报告。这仍不是实时Docker空闲扫描，停机前另需真实worker/容器检查。

Linux候选的118文件清单在实机回读时与本地预期一致。该候选尚未获得新的受审私有Source身份，不能沿用旧Source身份进入科研。已有历史Mac字面量保持原身份；旧动态Python声明没有被重释，若正式接管遇到此类历史，仍需原执行主机依据。没有导入科研入口模块的初始化代码。

新的两文件候选把屏障检查放在原全局owner锁获取之后、第二次preflight及任何claim/clock/budget/client之前，原flock和其他源码AST保持不变。停止适配器持同一锁先持久写入屏障，再验证和提交；释放lease、杀掉持锁进程、丢失ACK或校验失败都不会自动移除屏障。屏障与观察到的run/owner/boot/target身份必须一致；该绑定缺口的失败回执与修复已保留。新16项同时覆盖已经开始preflight的竞争进程，防止其在停机ACK之后进入owner。

这是独立工程目录内的接入验收。所有获准派发的owner必须使用带屏障检查的新受审Source，屏障不能替代这项准入。未增加自动清除/恢复实验入口，也未验证真实财务或私有Git收尾。

规范路径验收使用独立平台容器，原科学DockerRunner源码和参数未改。新增的唯一挂载是明确的新建合成目录，只读映射到容器内历史规范前缀；没有探测或创建原Mac路径。四次容器均通过实际参数检查、UID/GID65534、无有效capabilities、no-new-privileges、只读挂载及精确身份清理核验；活动memory和误用宿主路径绑定均由原函数拒绝。固定镜像内Python实测3.12.14，与已测宿主3.12.3分别记录；该平台探针不能替代原宿主或完整科研准入。

有限云端检查结束后按bootstrap空闲检查停机，保留卷和代码；存储继续计费。后续继续其余真实关闭验证接线和未来接管的路径配置。没有启动科学owner、复制memory/账本或改动原实验调度，也没有同规则完整科研轮次的提速倍数。

新请求适配层把原physical_requests、完整反馈包含检查、Controller严格JSON与panel恢复接入相同memory/runtime/manifest和真实owner drain。核对完整reservation与HTTP payload、唯一生成、连续编号、响应/raw及计数哈希和输入；仅assistant出现或部分user反馈会拒绝。raw仅哈希不解码。19项扩测发现并修复了boot身份提前拒绝后残留上次cleanup成功报告；测试fixture的共享反馈绑定也已补齐，原断言保留。该19项随后按用户批准的原清单在AWS通过。

用户授权的可选计时补丁在独立副本审阅，基础Source与既有批准包哈希一致；没有覆盖现有两文件候选。默认关闭路径保持原结果、读取与调用顺序，计时写入/读取/clock失败保持原科研结果，输入通过深拷贝隔离，系统中断继续传播。独立本地与AWS11项的finance/Native/task/cleanup/physical-request依赖仍明确为合成stub。它只观察批次审计；完整25公司、归档、memory写回及最终财务关闭事件仍缺，不能据此声称科研提速。

新S3上传曾被自动审批拒绝；用户随后明确批准该精确清单，原包未改，已完成加密上传、AWS19+11项通过、代码哈希回验和空闲扫描后停机。新增公司20项不在获批包内，保持本地结果，未擅自扩大云测范围。

公司terminal适配实际执行原八个批次函数，保留完整有序结果前提，拒绝PID/true-exit/checkpoint/UUID/预留/区间/事件不匹配。它与原memory/cleanup及真实drain共用执行身份；语义失败阻止stop并保留屏障。此evaluation子集的finance/requests/private-seal及stop/worker观测仍为synthetic；不能把此前proposal请求测试算作evaluation完整请求准入。normal-yield和rolling8在访问额外Native/context路径前明确拒绝。

原clock的Mac专用boot接口已有独立Linux候选，本地19项通过：原validate/capture_or_load、Darwin取值体和其他模块AST保持精确不变，只在已有测量host/Python守卫后读取有界内核boot UUID，无随机/时间fallback。恢复时不重建origin或续期；跨boot、配置/窗口漂移、残缺seal和非规范文件拒绝。本地Linux/host是显式mock，真实Linux探针还未运行。新两文件传输被自动审批限制为需单独明确授权，具体清单已提交；本轮无新上传或实例启动，之前获批23文件的云验收仍有效。内核boot_id语义参照[官方文档](https://docs.kernel.org/admin-guide/sysctl/kernel.html#random)。

离线04计时修订独立复现11个consumer和7个时钟域检查。观察器只从原owner已检查的clock binding读回哈希验证后的记录域，不查询观察主机boot，也不再接受任意构造器clock。四参数回调、两份Source overlay与observer必须成套匹配，03和04不能混用；新观察器实例应按一次Source绑定evaluation创建，status或旧文件存在都不能当作当前测量成功。它与Linux候选的9字段schema相容。四文件118候选的116 Python仅做静态语法和清单验证，114基础文件未变；没有启用新Source、替代完整原准入或获得真实提速数据。

新增evaluation联合适配在同一独立manifest、memory/runtime与真实drain上实际执行原公司terminal和physical_requests。两个合成公司分别走wave与rolling4，完整reservation/payload、生成/count intent、编号/响应/raw哈希与公司退出/checkpoint/UUID/区间/持久事件一起校验。新增14项通过；修改入口的既有20项回归通过。联合工厂拒绝未给出原请求源码时退回terminal-only；请求和terminal分别重验，拒绝沿用缓存成功。缺响应、计数不符或后续boot漂移阻止stop且不写新提交intent。该新路径已有四个原验证面，剩余finance/private-seal及OS快照/stop为显式synthetic。它没有新增云上传、真实科研或全25公司准入证明，也不继承旧proposal19的route证明。

公开目录不含实际云标识、私有Source版本、内部回执、原研究源码包或私有Git祖先；原函数接入的私有工程代码与详细回执在受控交付目录中。PR继续保持草稿。
