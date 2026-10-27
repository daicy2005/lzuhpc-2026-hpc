# 第十六轮：优化后p32运行时的victim选择

2026-10-25，正式采样前冻结。早期p4随机策略未获采用，不能直接覆盖优化后的p32推荐。本轮只比较已有round_robin与seeded_random(seed17)，不新增策略、不修改生产代码，不继续搜索批量上限或退避时间。

## 固定条件

复用第四轮full_lanes8原Release：二进制SHA256 `c52674ba1244813d7d71808298b552042487a8bbeb41b8349a3eb4915027da8c`，应用源码 `e85c97b09468b4a3c6a6286bdceac7ffa408d2983cc2a957765e6b3bd9580c86`。原构建1765项runtime/161项CLI验证是历史证据，不写成新增检查。batch32/scratch/LTO/compute_lanes8，32worker，逻辑CPU掩码0..31，grain256、K1024，immediate、single、reference_workers32固定。

工作负载compute_skewed，前floor(N/8)元素执行9K，其余K；每元素完整递推与独立标量核验保持。主目标concentrated；spread和shuffled为护栏。每种布局只排列同一任务集合，同布局两策略的输入/成本/任务/队列身份完全相同。shuffled使用配置layout_seed，独立Python实现当前libstdc++13的mt19937_64与shuffle并先和独立C++标准库探针对照，不以读取应用自身身份代替队列重建。

## 输入、顺序与预算

- 小control：seed138007/N1031/K7，grain256，三布局×两策略，共6个diagnostic；5任务、小于worker数、尾任务及八路计算尾部均覆盖。Python独立重算全部输出与身份。
- 两个未用于本轮选型的输入：seed140009/N229376、seed146021/N360448。每输入三布局×两策略，各1diagnostic、1预热、7正式计时。
- 固定114研究进程：18diagnostic、12预热、84正式计时；无筛选/条件分支，不追加seed、随机策略种子、重复数或备选候选。
- 6组配对以2026102516打乱，诊断和预热各按冻结组顺序；7轮计时逐轮循环移位，奇数AB、偶数BA。7对无法完全平衡方向，如实保留。
- 每进程90秒、批次600秒；最多两次各600秒资源等待。Windows连续三次CPU≤15%及WSL已知任务观察通过才启动；批内0.5秒后台及每进程前后WSL观察串行加锁。错误、超时或污染立即封存，不停止其他任务，不关闭本机。门禁不证明独占、物理核心类型或缓存因果，批内不持续采Windows CPU。

## 采用与停止

两个输入的concentrated各至少6/7对epoch更快，且全部7次epoch中位数各≤对照95%；每输入spread/shuffled的epoch中位数各≤110%；全部六组app中位数各≤105%。所有门槛同时满足才采用，这是工程规则而非显著性检验。未通过保留round_robin，不据单格赢家调整门槛。通过只另存本轮精确配置与原二进制来源，不改旧JSON、不推断uniform/light/memory同样受益、不与旧轮比值相乘。

## 验证与可追溯

准备阶段核对原推荐JSON/构建/源码快照/校验清单。保持当前生产代码与原测量源码两套来源独立，不宣称它们相同。新增采集器先验证计划数量、单一策略差异、成功/主门槛/两护栏拒绝规则；独立C++探针验证Python shuffle模型的奇偶长度、尾部、多个seed及实际任务数量。这些是工具准备检查，不是应用计时。

所有研究进程完整标量核验、mismatches=0、compared_elements=N、配置与affinity读回通过。diagnostic独立重建每任务执行者、成本/元素/任务数及初始owner；single要求steals=moved=最终异主任务数。attempts不覆盖第一次victim取锁失败，busy包含两处，不能用busy/attempts当总体失败率；计数与负载均衡度不能单独证明耗时因果。

每run唯一ID，诊断/预热不进入计时，全部慢成功样本保留。冻结协议、采集器、顺序、原构建及源码。Linux审计和验散列导出新victim-selection目录，再由Windows独立重算输入/队列、全部配对和采用决定。报告链接全部原件。已有综合PDF及候选包是第十五轮截至快照，本轮另存补充结果与交付收据，未重新打包前不声称旧包包含本轮。
