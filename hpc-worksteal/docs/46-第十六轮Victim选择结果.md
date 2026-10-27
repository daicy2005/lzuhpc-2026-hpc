# 第十六轮：准备完成，资源等待耗尽，尚无性能结果

2026-10-25，依据[冻结协议45](45-第十六轮Victim选择协议.md)。原推荐p32/g256/K1024/full_lanes8，比较已有round_robin与seeded_random(seed17)；两输入×集中/分散/打乱布局，固定计划114研究进程/84正式计时。采集器、原源码/构建及顺序已冻结，但两段资源等待都未通过，实际研究进程0、正式计时0，accepted=null。不能写成候选失败、策略没有收益或第十六轮实验已完成。

## 已完成的准备与核验

- 编排/门槛合成检查通过：固定数量、唯一victim差异、主目标胜对和中位数、两类布局护栏及app护栏的拒绝行为。合成数据不是性能样本。
- 独立Python实现mt19937_64与libstdc++13 shuffle，Linux上编译独立C++标准库探针，50组多seed/奇偶/尾部/实际任务数量全部一致，无编译警告。探针不执行本项目workload。
- 新checker从配置读取p32，按seed/N/K/p/grain/layout/layout_seed区分完整身份，避免跨粒度/布局错误复用；独立重建打乱队列，不依赖应用自己报告的队列hash作为期望值。
- 一份第四轮真实p32计时记录只读回放通过；队列身份、参考覆盖数、参考线程数、affinity、输出hash和resolved策略六种故意破坏均被拒绝。[回放收据](../results/victim-collector-replay-20261025.json)不代表重新执行应用或新计时。
- [冻结计划](../victim-selection/results/frozen-plan.json)的collector源码ID为`f240afa46fe86b8886420f0f8ed1d36312a169283a3f2e572ba5c9d8934b008f`；原测量应用源码仍为`e85c97b09468b4a3c6a6286bdceac7ffa408d2983cc2a957765e6b3bd9580c86`，二进制仍为`c52674ba1244813d7d71808298b552042487a8bbeb41b8349a3eb4915027da8c`。这两套来源不混称同一源码。

## 两段实际等待

|观察文件|状态|实际秒数|观察次数|Windows负载范围|最后负载|
|---|---|---:|---:|---:|---:|
|[第一段](../victim-selection/results/availability-9ef8d2031dd04e0e923e4746ca5894b2.json)|deferred_busy|590.9510036|28|21%—74%|38%|
|[第二段](../victim-selection/results/availability-cd778c02b42f497d9fe09606c4c04568.json)|deferred_busy|589.4136722|28|17%—77%|39%|

合计1180.3646758秒/56次观察，均未达到连续三次Windows CPU≤15%要求。采集器在等待预算不足以安排下一次观察时退出，因此实际时长略小于各600秒上限。Linux目录无runs批次，工具会拒绝第三段等待。没有放宽门槛、运行新workload、停止其他任务或关闭本机；两段等待进程均已终止，随后ps只见WSL初始化及检查进程，无后台采集器。

## 归档、解释和下一步

冻结资料、原构建及两段观察共256个文件由Linux验散列导出到victim-selection/。Windows使用`tools/archive_victim_preparation.py`重新检查导出清单、两套源码快照、原构建、shuffle模型及回放收据；结果另写`results/victim-selection-preparation-20261025.json`。该准备归档不能冒充完整批次审计，正式audit/report仍要求实际批次。

原计算/内存推荐保持不变，依据仍是已有确认实验，不以本次未采样为新证据。资源等待只说明这些观察窗口主机忙，不说明victim策略或硬件拓扑。继续采样需先另立明确的资源恢复协议，保留当前门槛、输入、候选和原等待资料，不在耗尽预算后反复run直到通过。

等待期间新增[随机序列相关性源码观察](47-随机Victim序列相关性源码观察.md)：现有随机策略的生成序列没有混入worker编号。这是下一步可验证的假设，不是实测争抢或耗时因果；当前未实现新策略。实际源码阅读地图补在[架构文档](02-架构与文件职责.md)，不再要求寻找早期规划但后来合并的文件。

综合PDF与约261MiB候选ZIP仍为第十五轮截至快照，原ZIP字节保持，不声称包含第十六轮准备或后续文档。DevContainer实建仍未完成：本轮再次检查Windows无可调用docker/podman及已登记路径程序/服务，WSL无docker/podman/nerdctl/devcontainer或标准Docker/Podman socket，且仍为WSL1；没有安装或改变系统。项目完整验收继续按[台账42](42-最终交付验收台账.md)，不能因准备资料归档就宣布目标完成。
