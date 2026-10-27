# HPC 方向：光线追踪与 Mini WorkSteal

这是我参加兰州大学超算队 2026 年秋季纳新时做的两个项目：光线追踪优化和 Mini WorkSteal。两部分整理在同一份 PDF 中，源码、补充实验和复现步骤放在这个仓库。

- [报告 PDF：6 页](report/HPC方向技术报告.pdf)
- [报告正文](report/main.md)
- [补充实验与资料](docs/appendices.md)
- [复现说明](docs/reproduction.md)
- [实验记录说明](docs/data-scope.md)
- [图表原始输入](report/figure-data-v2.json)
- [报告使用的数据索引](report/evidence-index-v2.json)
- [WorkSteal 机制补测](supplements/mechanism-controls/README.md)
- [单任务大于 LLC 的补测](supplements/large-task-controls/README.md)
- [官方实验要求对照](docs/official-requirements.md)

报告链接到一个[固定材料版本](https://github.com/daicy2005/lzuhpc-2026-hpc/tree/d994f19172f30dbf5951547269d385ed87c14bf6)，方便找到与文中内容对应的代码、附录和数据。

在仓库根目录执行 `python3 tools/verify_materials.py`，可以检查实验文件是否完整，并核对报告引用的计时记录。

两组补测另存了 205 次计时及预热、诊断。运行 `python3 tools/verify_mechanism_supplement.py` 和 `python3 tools/verify_large_task_supplement.py` 可以检查完整压缩包，并从逐次记录重算中位数。

## 两个项目

光追最终源码在 `hpc-raytracing/implementation/16fafcdc65f1ac9c25a14519ead75b345c88b82cd500f1da05e9f07ca99b6bc2/`。最终使用 O3、OpenMP 像素块并行、16 桶 SAH BVH，并延后构造命中记录。同批测量的 Render time 中位数从 1968.697 秒降到 85.006 秒，耗时比为 23.16。这是整套修改的效果，包含编译选项、算法和线程配置等因素。

WorkSteal 源码在 `hpc-worksteal/`，使用固定任务集、持久线程池和带锁双端队列，各类策略单独注册。最终保留 round_robin、immediate、single，线程数和粒度按负载选择。随机 victim 在两个新输入上收益不稳定，因此没有替换 round_robin。

## 运行环境与尚未解决的问题

实验环境为 i9-13900HX、Ubuntu 24.04 / WSL1。源码已在 Linux 下重新构建和测试，DevContainer 配置还没有实际构建。光追在不同批次测试中的耗时差异较大，原因尚未查明。WorkSteal 补测统一了窃取开关的空闲处理，比较了增加任务数的成本，也确认了三种内存规模下的动态窃取；固定执行线程的预读对照仍没有得到稳定的局部性损失估计。

题目和光追原始代码来自 [LZUOSS/LZUHPC](https://github.com/LZUOSS/LZUHPC/tree/33dad592cd74d8cf36ae7921a29c0e8393034a70/assignments/2026/autumn)，所用版本为 `33dad592cd74d8cf36ae7921a29c0e8393034a70`。OpenMP、BVH、SAH 和工作窃取都是已有方法，这里主要记录它们在题目中的实现、调整和实验比较。
