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
| 原财务请求行检查 | 本地18/18，未云测 | 原只读SQLite请求行与原memory在新建合成DB上执行；完整历史grant/Source/prefix与finance关闭面仍未接通 |
| 原完整预算核心接线 | 本地12/12；共享context18项回归通过 | 原完整函数及真实Git授权子检查执行，固定历史前缀拒绝虚构历史；规范只读profile已接线；原model/additional历史依赖另有13项本地验收，完整财务正例仍未取得 |
| 可选比较/停止观察05 | 独立离线9+9通过 | 原比较返回与原durable-stop提交位置，默认关闭；其余依赖明确stub，完整C3仍缺真实终点 |
| Linux boot时钟候选 | 本地及AWS19/19；实际host/kernel/clock探针通过，已停机 | 原Mac接口在Linux实际失败；候选经原host守卫读取内核boot，原跨boot/不续期及回读字节检查通过；未安装完整三文件118候选或准入科研 |
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

原clock的Mac专用boot接口已有独立Linux候选，本地及AWS各19项通过。用户明确批准原两文件清单后，仅上传该精确工程包，复用已批准的普通Source对象，保护与checksum回验通过；没有混入财务/evaluation/计时04文件。实际Linux探针记录原Mac sysctl接口失败，候选通过原host/Python守卫并读内核boot，两次一致；原新clock建立/恢复一致，跨boot与截止时间延长被拒绝，恢复及拒绝前后文件字节不变。原validate/capture_or_load、Darwin取值体及其余AST保持不变，无随机/时间fallback。历史clock没有读或重释。该有限探针只有host/config/clock树，三文件118完整候选未安装或准入。worker/容器/平台容器均0后，实际回读实例stopped且保留卷，BOOTSTRAP_ONLY与停止保护保留。首次拒绝和后续具体用户授权分别留档，本申请已完成。内核boot_id语义参照[官方文档](https://docs.kernel.org/admin-guide/sysctl/kernel.html#random)。

离线04计时修订独立复现11个consumer和7个时钟域检查。观察器只从原owner已检查的clock binding读回哈希验证后的记录域，不查询观察主机boot，也不再接受任意构造器clock。四参数回调、两份Source overlay与observer必须成套匹配，03和04不能混用；新观察器实例应按一次Source绑定evaluation创建，status或旧文件存在都不能当作当前测量成功。它与Linux候选的9字段schema相容。四文件118候选的116 Python仅做静态语法和清单验证，114基础文件未变；没有启用新Source、替代完整原准入或获得真实提速数据。

新增evaluation联合适配在同一独立manifest、memory/runtime与真实drain上实际执行原公司terminal和physical_requests。两个合成公司分别走wave与rolling4，完整reservation/payload、生成/count intent、编号/响应/raw哈希与公司退出/checkpoint/UUID/区间/持久事件一起校验。新增14项通过；修改入口的既有20项回归通过。联合工厂拒绝未给出原请求源码时退回terminal-only；请求和terminal分别重验，拒绝沿用缓存成功。缺响应、计数不符或后续boot漂移阻止stop且不写新提交intent。该新路径已有四个原验证面，剩余finance/private-seal及OS快照/stop为显式synthetic。它没有新增云上传、真实科研或全25公司准入证明，也不继承旧proposal19的route证明。

新财务请求行适配先核验原Source并执行原memory，再以原只读URI与事务检查编号请求的UUID、模型、预留、结算状态和charge。18项本地检查通过，覆盖未结算/缺行/超额/非整型、重复ID、配置错误、遗漏回执，以及数据库哈希/类型/权限/硬链接/sidecar/WAL格式拒绝。只读连接禁止写入和ATTACH，成功或失败均关闭；前后单文件字节保持一致。正例仅使用原历史legacy分支与虚构数据，带amendment的runtime不能降级到该分支取得通过。原amended-cap校验实际执行并拒绝缺失grant，复制一个合成grant也无法替代缺少的历史Git/prefix依赖。此回执明确不是完整finance关闭验证，没有提供stop的finance回调；原生产路径、预算常量和历史账本未读取或修改。本项没有云传输/开机或Devin/模型调用，也没有改变此前四原面evaluation接线。

原完整预算核心现已实际接入，新增12项本地检查和共享只读context的18项回归通过。原Git授权与实现blob子检查在新建合成仓库通过；原完整预算函数仍按固定历史前缀拒绝虚构账本，没有替换前缀或制造完整财务正例。条件finance回调仅在原函数及其全部实际适用依赖返回后给digest；真实drain下的财务拒绝阻止stop且无提交intent。原with和contextlib.closing均关闭只读连接。原12文件核心模式保留，16文件模式另接原只读model/additional历史依赖；完整财务正例仍未取得，生产配置未启用。

计时05增量的比较9项和停止9项在本部署副本独立复现。原模块恢复显式增量后保持一致，原stop代码及03/04不变；外部candidate源码未读取，新候选从本工程已批准副本重构。公司终态report和条件财务report现有明确的已校验terminal/runtime绑定，接口smoke通过；只有同一lease下整个原关闭验证成功后才可消费。完整C3仍缺原比较结果实际保存/归档seal、所有窗口的原闭合和当前主机时钟样本，不能从run_id、单面last_report、六个合成digest或上次clock探针推导完成时间。没有向其他聊天回复、云/模型操作或新科研owner。

公开目录不含实际云标识、私有Source版本、内部回执、原研究源码包或私有Git祖先；原函数接入的私有工程代码与详细回执在受控交付目录中。PR继续保持草稿。

规范财务只读路径profile现已接入原共享context、memory函数与受限Git入口，新增10项和请求行18/预算核心12/memory18回归通过。账本保持在原独立目录，population回执与账本收据使用同一精确artifact父目录manifest；不把fixture路径写回历史绑定。Mac和非独立部署命名空间会在原路径IO前拒绝。Linux正向仅做内存平台模拟与实际路由截点，尚未做该profile的Linux文件系统验收。原memory模块默认全局根与runtime/tasks根的差异已记录：只选用原函数并显式提供runtime根，不初始化原模块，不能据此授予Source准入。

原model/additional历史财务函数新增13项本地检查通过，旧核心12项与规范profile10项回归通过；初版12项也单独留档。16文件模式实际执行原read_grant、历史授权、window及来源注册规则；新建合成Git上的模型授权子检查通过，required grant缺失、金额/类型/窗口改变、混合来源根和未注册Source均拒绝。真实只读SQLite上的完整16文件入口仍由原固定历史前缀拒绝虚构历史，数据库不变。原追加授权的固定人类确认没有伪造；额外路径集合不能扩大显式manifest范围。panel/training和原历史Reader身份仍明确阻断，未提供成功替身；完整财务/Source/C3/生产准入仍未通过。本单元没有云、Devin、模型或原Supervisor操作。
