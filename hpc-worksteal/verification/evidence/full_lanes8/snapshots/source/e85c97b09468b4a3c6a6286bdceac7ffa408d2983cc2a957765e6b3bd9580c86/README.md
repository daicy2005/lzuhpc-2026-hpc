# Mini WorkSteal：从 CS149 到可解释的并行运行时

状态：**前三轮实验均已完成（2026-10-16）。**

最新是[第三轮补充实验报告](report/refinement/第三轮补充实验报告.md)及[当前推荐配置](configs/refined/README.md)：168个研究进程、128个计时样本，另20个阶段观测/control进程。轻任务full_lanes8/p16/grain512相对第二轮推荐，在两个新输入分别再快2.04/2.89倍（epoch），应用端到端1.107/1.056倍；均匀/偏斜重计算保留第二轮推荐，memory未重选。阶段观测确认重计算完整参考核验占总时间约96.5%/97.1%。协议及口径见[16](docs/16-第三轮补充实验协议.md)、[17](docs/17-第三轮结果与复现.md)。下列第二轮结果与其configs/optimized是历史对照，保留原件。

第二轮结果：[第二轮优化报告](report/optimization/第二轮优化报告.md)、[第二轮选择与复现](docs/15-第二轮结果与复现.md)、[第二轮配置与构建预设](configs/optimized/README.md)。第二轮 616 个研究进程、470 个计时样本，另有4个推荐配置验收；两个新输入均五对全胜。计时区间相对原参数基线：light约15倍、uniform约14–16倍、skewed约14倍、memory约1.8–1.9倍。收益包含等价内核、逻辑线程数、粒度与运行时的联合变化，应用端到端收益较小，详见报告。

第二轮协议见 [14-第二轮优化协议](docs/14-第二轮优化协议.md)。第一轮报告、数据与推荐是历史基线，原件保留；第二轮编译开关默认关闭以保留基线配置，不使用旧的“生产源码等于 v3”审计描述当前源码。最新源码、构建与原始数据核验在 `optimization/results/archive-audit.json`。

第一轮历史结果：[实验报告](report/实验与策略选择报告.md)、[PDF](output/pdf/Mini-WorkSteal-实验与策略选择.pdf)、[评审与选择](docs/13-最终评审与选择.md)。共 498 个研究进程，其中 342 个正式计时；三类均未满足替换默认策略的双输入门槛，保留 base。集中偏斜布局 off/on 中位数比为 2.428；均匀负载收益很小。该结论仅针对当时策略集合，不与本轮等价内核及联合参数优化混淆。

C++20 runtime、声明式策略注册、五种执行模式、三种 workload 已实现。第一轮 v3 的 Release、ASan/UBSan 与 TSan 均真实通过；第二轮三种入选构建也各通过这些检查。当前推荐见 `configs/optimized/`，第一轮 `configs/recommended/` 保留为历史基线；旧 example/design JSON 是设计草案。题目提交所需的完整连续 Session 导出与 DevContainer 实建不在本次实验完成声明内。

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

最新统计：`python tools/analyze_opt.py --root .`；最新归档核验：`python tools/audit_opt.py --root .`。第一轮统计仍可用 `python tools/analyze.py --root . --out results` 再生成；`closeout.py audit` 的 v3生产源码一致性仅适用于第一轮封存时点，不用于检查当前已优化源码。报告依赖及生成见 [report/README.md](report/README.md)。

## 最终希望能回答

首要问题：**固定总工作量时，任务粒度和初始不均衡程度怎样决定工作窃取是否值得使用？** 先完成计算型机制，再研究缓存窗口。四种执行器之外，增加同一窃取运行时的S3-off/on对照；它只改变是否允许窃取。

1. 工作量不均匀时，动态调度能减少多少尾部等待？
2. 任务很小时，调度费用何时超过均衡收益？
3. 数据迁移在什么工作集规模与访问模式下会损害局部性？
4. 一组策略为何适合某类任务，换一种任务后是否仍成立？

不承诺全局最优或固定加速倍数。负收益和局部性效应接近零都是允许报告的结果。
