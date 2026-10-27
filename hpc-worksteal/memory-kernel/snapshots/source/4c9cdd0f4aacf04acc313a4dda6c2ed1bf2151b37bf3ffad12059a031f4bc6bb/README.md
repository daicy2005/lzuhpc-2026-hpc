# Mini WorkSteal：从 CS149 到可解释的并行运行时

第八轮进行中：按[内存执行交错协议](docs/27-第八轮内存执行交错协议.md)验证可选`measurement.memory_lanes=4`。只交错任务内独立元素，原标量参考与完整工作量保留，默认1。主要目标为epoch，另设app退化护栏；固定44进程预算，尚无本轮性能结论。

第七轮已完成：按[覆盖式分配协议](docs/25-第七轮覆盖式分配协议.md)验证可选`measurement.data_allocation=overwrite`，省去随后被完整生成器覆盖的清零。44研究进程/28计时，两组应用总耗时中位数下降约12.0%/6.5%，配对胜出6/7、5/7；第二组未过预定门槛，因此不采用为推荐。默认zeroed、填充线程1、历史推荐保留，不追加样本。三种构建各通过1927项runtime检查和275次CLI调用，Windows核对569个导出文件。见[最新报告](report/allocation/第七轮覆盖式分配报告-7f045ca9.md)与[存储契约及结果](docs/26-第七轮存储契约与结果.md)。此为应用初始化研究，不是工作窃取策略加速。

状态：**前七轮实验均已完成（2026-10-21）。第六、七轮初始化候选未通过确认，保留原推荐。**

第六轮实现了可选的内存数据并行填充，默认仍为`measurement.initialization_workers=1`；Release、ASan/UBSan、TSan各通过1847项runtime检查和213次CLI调用。按冻结协议完成56研究进程/40计时，筛选选中4线程，但两个新输入仅3/7、4/7对端到端胜出，中位数改善约4.0%/0.6%，均未达到双输入门槛。因此不建立新的推荐配置，`configs/verified`继续有效。所有身份/输出/预读散列一致；Windows核对642个导出文件，独立重算结论。见[第六轮报告](report/initialization/第六轮内存初始化报告-4a69c6fd.md)、[协议](docs/23-第六轮初始化优化协议.md)和[接口及结果](docs/24-第六轮初始化契约与结果.md)。这是完整保留的负结果，不把筛选收益当作已确认提升。

第五轮按冻结的[空闲窗口确认协议](docs/20-第五轮空闲窗口确认协议.md)完整完成96研究进程/84计时，复用第四轮原二进制；两个新输入、每输入7对，三类均7/7对胜出。相对同二进制串行核验，应用端到端中位数：uniform快9.584/9.743倍，skewed快11.279/11.630倍，memory快1.468/1.496倍。light保留串行，本轮未重测。详见[第五轮报告](report/confirmation/第五轮空闲窗口确认报告-cdcc790a.md)与[结果及下一步](docs/22-第五轮结果与后续方向.md)。这是独立完整核验并行化的应用收益，不能称为工作窃取或epoch加速。

本轮起始三次Windows负载3%、11%、15%通过门禁，批中300次WSL观测均未触发阻断；只证明通过已定义门禁的观测窗口，不证明物理独占。Linux/Windows均从原始记录重审计，核对787个导出文件、98个冻结源码项及1158个批次/运行散列项。此前误报中止与三段等待的原件仍独立保留于`confirmation/`与`confirmation-retry/`；[进展记录](docs/21-第五轮进展与恢复.md)保留全过程。当前无后台等待任务，不追加同轮样本或重新筛选候选。

第四轮历史[并行核验报告](report/verification/第四轮并行核验报告.md)与[当前配置](configs/verified/README.md)：180研究进程、140计时样本，另4个配置复跑。每个元素仍完整标量重算、最后顺序散列；同新二进制串行核验对照下，uniform/skewed应用端到端约7.0–10.5倍，memory约1.37–1.39倍；light未过门槛保留串行。这是核验阶段的应用收益，不是epoch或工作窃取策略加速。实验期间存在另一32线程光追任务，因此保留共享WSL1主机证据范围；第五轮另用新输入确认，不覆盖此结果。协议与接口见[18](docs/18-第四轮并行核验协议.md)、[19](docs/19-第四轮结果与核验契约.md)。两个新Release及ASan/UBSan、TSan实际通过；历史各轮原件保留。

第三轮是[补充实验报告](report/refinement/第三轮补充实验报告.md)及[当时推荐配置](configs/refined/README.md)：168个研究进程、128个计时样本，另20个阶段观测/control进程。轻任务full_lanes8/p16/grain512相对第二轮推荐，在两个新输入分别再快2.04/2.89倍（epoch），应用端到端1.107/1.056倍；均匀/偏斜重计算保留第二轮推荐，memory未重选。阶段观测确认重计算完整参考核验占总时间约96.5%/97.1%。协议及口径见[16](docs/16-第三轮补充实验协议.md)、[17](docs/17-第三轮结果与复现.md)。下列第二轮结果与其configs/optimized是历史对照，保留原件。

第二轮结果：[第二轮优化报告](report/optimization/第二轮优化报告.md)、[第二轮选择与复现](docs/15-第二轮结果与复现.md)、[第二轮配置与构建预设](configs/optimized/README.md)。第二轮 616 个研究进程、470 个计时样本，另有4个推荐配置验收；两个新输入均五对全胜。计时区间相对原参数基线：light约15倍、uniform约14–16倍、skewed约14倍、memory约1.8–1.9倍。收益包含等价内核、逻辑线程数、粒度与运行时的联合变化，应用端到端收益较小，详见报告。

第二轮协议见 [14-第二轮优化协议](docs/14-第二轮优化协议.md)。第一轮报告、数据与推荐是历史基线，原件保留；第二轮编译开关默认关闭以保留基线配置，不使用旧的“生产源码等于 v3”审计描述当前源码。第二轮封存时的构建与原始数据核验在 `optimization/results/archive-audit.json`；当前第四轮核验在 `verification/results/archive-audit.json`。

第一轮历史结果：[实验报告](report/实验与策略选择报告.md)、[PDF](output/pdf/Mini-WorkSteal-实验与策略选择.pdf)、[评审与选择](docs/13-最终评审与选择.md)。共 498 个研究进程，其中 342 个正式计时；三类均未满足替换默认策略的双输入门槛，保留 base。集中偏斜布局 off/on 中位数比为 2.428；均匀负载收益很小。该结论仅针对当时策略集合，不与本轮等价内核及联合参数优化混淆。

C++20 runtime、声明式策略注册、五种执行模式、三种 workload 已实现。第一轮 v3 的 Release、ASan/UBSan 与 TSan 均真实通过；第二轮三种入选构建也各通过这些检查。当前配置见 `configs/verified/`，前三轮目录保留为历史基线；旧 example/design JSON 是设计草案。题目提交所需的完整连续 Session 导出与 DevContainer 实建不在本次实验完成声明内。

本项目对应 LZUHPC 2026 秋 HPC 创意题 Mini WorkSteal。目标是在 Linux 上实现小而完整的 CPU 工作窃取运行时，以可组合策略研究负载均衡、调度开销和缓存局部性的取舍。它独立于相邻的光追项目，不改上游题目仓库，不继承光追的性能结论。

## 阅读入口

| 文档 | 解决的问题 |
|---|---|
| [目标与题目边界](docs/01-立项与验收.md) | 要完成什么，什么算完成 |
| [架构与目录](docs/02-架构与文件职责.md) | 模块怎么分，依赖朝哪里走 |
| [策略与命令契约](docs/03-策略与接口契约.md) | 怎样增加策略而不改运行时 |
| [并发正确性](docs/04-并发与正确性规范.md) | 任务不丢不重、结束与退出如何保证 |
| [实验设计](docs/05-实验设计.md) | 怎样区分三类性能效应 |
| [数据归档](docs/06-实验记录与归档.md) | 怎样保留可复现证据与负结果 |
| [实施与学习路线](docs/07-阶段计划与CS149映射.md) | 按什么顺序做，每步需要理解什么 |
| [决策记录](docs/08-决策记录.md) | 为什么选择当前方案 |
| [工作负载与机制对照](docs/09-工作负载与机制对照.md) | 如何固定工作量、制造可解释的偏斜、验证迁移 |
| [首批实验协议](docs/10-首批实验协议.md) | 第一批做哪些配置，何时开始、停止，怎样冻结预算 |
| [社区与本机评审](docs/11-社区与本机评审.md) | 三方评审意见、社区依据、本机能力与待补契约 |
| [实施与实验变更](docs/12-实施与实验变更.md) | 实际同步、队列、计时和 WSL1 限制 |
| [最终评审与选择](docs/13-最终评审与选择.md) | 三方复核、实际结果、推荐组合与未完成提交项 |
| [项目约束](AGENTS.md) | 后续开发与实验必须遵守的规则 |
| [第四轮核验协议](docs/18-第四轮并行核验协议.md) | 应用端到端筛选、独立参考核验与新输入门槛 |
| [第四轮接口与结果](docs/19-第四轮结果与核验契约.md) | 核验线程生命周期、实际验证及共享主机限制 |
| [第五轮确认结果](docs/22-第五轮结果与后续方向.md) | 新输入资源门禁确认及后续热点 |
| [第六轮初始化协议](docs/23-第六轮初始化优化协议.md) | 同二进制筛选、独立新输入确认及停止门槛 |
| [第六轮初始化契约与结果](docs/24-第六轮初始化契约与结果.md) | 数据并行填充、生命周期及未采用的原因 |
| [第七轮覆盖式分配协议](docs/25-第七轮覆盖式分配协议.md) | 固定候选、完整核验与双输入采用门槛 |
| [第七轮存储契约与结果](docs/26-第七轮存储契约与结果.md) | 完整覆盖写入、安全依据及未采用的原因 |
| [第八轮内存执行交错协议](docs/27-第八轮内存执行交错协议.md) | 四路独立递推、epoch主门槛及app护栏 |

## 项目组织

```text
hpc-worksteal/
  AGENTS.md                 开发、正确性、实验约束
  docs/                     架构、方法、阶段计划与决策
  reference/                题目来源与要求摘录
  configs/                  runtime 样例、recommended 完整配置、历史设计
  include/worksteal/        已编译的公共契约
  src/                      运行时、策略、工作负载与 CLI
  tests/                    正确性、并发、独立参考与扩展检查
  tools/                    构建、采集、核验、统计与报告生成
  runs/                     第一轮正式批次与单独保留的开发 smoke
  optimization/             第二轮跨构建批次、源码/构建快照、统计与核验
  initialization/           第六轮完整原始记录、四份构建及源快照、Windows核验
  allocation/               第七轮完整原始记录、构建及源快照、Windows核验
  snapshots/                源码、构建与工具的不可变快照
  evidence/                 sanitizer 与失败版本的独立导出
  results/                  从原始记录再生成的统计与结论
  report/                   报告正文、图表及其输入
  submission/               最终代码、PDF、复现说明与连续对话文件
  .devcontainer/            Ubuntu 24.04 环境草案，尚未构建验证
```

目录职责表保留最初架构规划。已实现入口为 `src/app/main.cpp`、`include/worksteal/`、`src/runtime/`、`src/workloads/`、`src/policies/`；实验工具见 `tools/lab.py` 与 `tools/study.py`。具体真实批次以不可变 plan/result/metadata 为准。

## 构建与检查

Linux 依赖：G++ 13 或兼容 C++20 编译器、CMake、Python 3、nlohmann-json3-dev。

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
./build/worksteal --config configs/runtime/diagnostic.json
./build/worksteal --list-policies
./build/worksteal --config configs/recommended/skewed.json
```

ASan/UBSan 与 TSan 分别使用新构建目录并设置 `-DWS_ASAN=ON` 或 `-DWS_TSAN=ON`。正式数据来自 Linux 独立目录，Windows 仅镜像源码与归档；当前 WSL1 的物理核驻留未证明。

优化构建使用 CMake 3.21+ 的 preset（当前实际 CMake 3.28），命令见 [configs/optimized/README.md](configs/optimized/README.md)。例如 `cmake --preset optimized-skewed`、`cmake --build --preset optimized-skewed`，然后运行 `build/optimized-skewed/worksteal --config configs/optimized/skewed.json`。不设优化开关的默认构建仍用于基线。

第七轮从原始数据复核并再生成报告：`python tools/allocation_study.py report --root allocation`，不重跑实验、不改写样本。第二轮历史统计和归档核验分别为`python tools/analyze_opt.py --root .`、`python tools/audit_opt.py --root .`。第一轮统计仍可用 `python tools/analyze.py --root . --out results` 再生成；`closeout.py audit` 的 v3生产源码一致性仅适用于第一轮封存时点，不用于检查当前已优化源码。报告依赖及生成见 [report/README.md](report/README.md)。

## 最终希望能回答

首要问题：**固定总工作量时，任务粒度和初始不均衡程度怎样决定工作窃取是否值得使用？** 先完成计算型机制，再研究缓存窗口。四种执行器之外，增加同一窃取运行时的S3-off/on对照；它只改变是否允许窃取。

1. 工作量不均匀时，动态调度能减少多少尾部等待？
2. 任务很小时，调度费用何时超过均衡收益？
3. 数据迁移在什么工作集规模与访问模式下会损害局部性？
4. 一组策略为何适合某类任务，换一种任务后是否仍成立？

不承诺全局最优或固定加速倍数。负收益和局部性效应接近零都是允许报告的结果。
