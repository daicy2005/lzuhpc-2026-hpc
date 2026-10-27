# HPC 方向：光线追踪与 Mini WorkSteal

这个仓库放的是我参加兰州大学超算队 2026 年秋季纳新时做的光线追踪优化和 Mini WorkSteal。报告合成了一份 PDF，主要讲实现思路、几组有代表性的实验，以及最后为什么选择这些方案。源码、其他尝试和复现步骤也在这里。

- [报告 PDF：6 页](report/HPC方向技术报告.pdf)
- [报告正文](report/main.md)
- [补充实验与资料](docs/appendices.md)
- [复现说明](docs/reproduction.md)
- [实验记录说明](docs/data-scope.md)
- [图表原始输入](report/figure-data-v2.json)
- [图表说明与重绘](docs/figure-design.md)
- [报告使用的数据索引](report/evidence-index-v2.json)
- [WorkSteal 机制补测](supplements/mechanism-controls/README.md)
- [单任务大于 LLC 的补测](supplements/large-task-controls/README.md)
- [官方实验要求对照](docs/official-requirements.md)

报告末尾可以找到[对应的代码、附录和数据](https://github.com/daicy2005/lzuhpc-2026-hpc/tree/a4927bc20d55eafdf0bab003bcccdc786465cb5e)。

在仓库根目录执行 `python3 tools/verify_materials.py`，可以检查实验文件是否完整，并核对报告引用的计时记录。

两组补测另存了 205 次计时及预热、诊断。运行 `python3 tools/verify_mechanism_supplement.py` 和 `python3 tools/verify_large_task_supplement.py` 可以检查完整压缩包，并从逐次记录重算中位数。

## 两个项目

光追最终源码在 `hpc-raytracing/implementation/16fafcdc65f1ac9c25a14519ead75b345c88b82cd500f1da05e9f07ca99b6bc2/`。最终使用 O3、OpenMP 像素块并行、16 桶 SAH BVH，并延后构造命中记录。同批测量的 Render time 中位数从 1968.697 秒降到 85.006 秒，耗时比为 23.16。这是整套修改的效果，包含编译选项、算法和线程配置等因素。

WorkSteal 源码在 `hpc-worksteal/`，使用固定任务集、持久线程池和带锁双端队列，各类策略单独注册。最终保留 round_robin、immediate、single，线程数和粒度按负载选择。随机 victim 在两个新输入上收益不稳定，因此没有替换 round_robin。

## 测试环境和不足

实验在日常使用的 i9-13900HX 电脑上完成，环境是 Ubuntu 24.04 / WSL1。Linux 下的重新构建和测试已通过，DevContainer 配置还没有实际构建。光追有一次明显的耗时波动，原因还没查明。WorkSteal 补做了相同空闲策略下的窃取开关、任务数和预读对照，也检查了实际窃取。预读对照没有测出稳定的变慢趋势，目前还不能据此分离缓存带来的影响。

题目和光追原始代码来自 [LZUOSS/LZUHPC](https://github.com/LZUOSS/LZUHPC/tree/33dad592cd74d8cf36ae7921a29c0e8393034a70/assignments/2026/autumn)。OpenMP、BVH、SAH 和工作窃取都是已有方法，这里记录的是我在题目约束下的实现、调整和实验比较。
