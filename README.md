# HPC 方向：光线追踪与 Mini WorkSteal

这是我参加兰州大学超算队 2026 年秋季纳新时做的两个项目：光线追踪优化和 Mini WorkSteal。两部分整理在同一份 PDF 中，源码、补充实验和复现步骤放在这个仓库。

- [报告 PDF：6 页](report/HPC方向技术报告.pdf)
- [报告正文](report/main.md)
- [补充探索、复现命令与资料](docs/appendices.md)
- [复现说明](docs/reproduction.md)
- [实验记录说明](docs/data-scope.md)
- [连续对话材料状态](docs/dialogue-status.md)
- [图表原始输入](report/figure-data.json)
- [报告使用的数据索引](report/evidence-index.json)

AI 对话和 Session 文件暂未上传；官方要求的 Prompt File 另行保留，目前还没有通过仓库提供。

报告链接到一个[固定材料版本](https://github.com/daicy2005/lzuhpc-2026-hpc/tree/338e37ed4f74fc1d4f189af98379e725fcc16645)，方便找到与文中内容对应的代码、附录和数据。

在仓库根目录执行 `python3 tools/verify_materials.py`，可以核对文件散列和报告使用的正式记录。这个脚本不会重新跑性能实验。

## 两个项目

光追最终源码在 `hpc-raytracing/implementation/16fafcdc65f1ac9c25a14519ead75b345c88b82cd500f1da05e9f07ca99b6bc2/`。最终使用 O3、OpenMP 像素块并行、16 桶 SAH BVH，并延后构造命中记录。同批测量的 Render time 中位数从 1968.697 秒降到 85.006 秒，耗时比为 23.16。这是整套修改的效果，包含编译选项、算法和线程配置等因素。

WorkSteal 源码在 `hpc-worksteal/`，使用固定任务集、持久线程池和带锁双端队列，各类策略单独注册。最终保留 round_robin、immediate、single，线程数和粒度按负载选择。10 月 27 日补跑的随机 victim 对照，在两个新输入上收益不稳定，因此没有替换 round_robin。

## 运行环境与尚未解决的问题

实验在本机 i9-13900HX、Ubuntu 24.04 / WSL1 上完成。源码在新的 Linux 目录中重新构建和检查过，DevContainer 配置还没有实际构建。光追跨批耗时波动较大，原因尚未定位；WorkSteal 的实验也还没能充分分开负载均衡、调度开销和局部性损失，报告中保留了这些问题。

题目和光追原始代码来自 [LZUOSS/LZUHPC](https://github.com/LZUOSS/LZUHPC/tree/33dad592cd74d8cf36ae7921a29c0e8393034a70/assignments/2026/autumn)，所用版本为 `33dad592cd74d8cf36ae7921a29c0e8393034a70`。OpenMP、BVH、SAH 和工作窃取都是已有方法，这里主要记录它们在题目中的实现、调整和实验比较。
