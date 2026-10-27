# HPC 方向：光线追踪与 Mini WorkSteal

兰州大学超算队 2026 年秋季纳新配套材料。唯一提交文件为技术报告 PDF；这里提供报告引用的源码、复现环境、详细附录和实验依据。

- [报告 PDF：6 页](report/HPC方向技术报告.pdf)
- [报告正文](report/main.md)
- [补充探索、复现命令与资料](docs/appendices.md)
- [复现说明](docs/reproduction.md)
- [数据范围与核对](docs/data-scope.md)
- [连续对话材料状态](docs/dialogue-status.md)
- [图表原始输入](report/figure-data.json)
- [报告证据索引](report/evidence-index.json)

本次不上传 AI 对话和 Session 文件；官方要求的 Prompt File 另行保留，当前尚未提供。

报告采用的[配套材料固定版本](https://github.com/daicy2005/lzuhpc-2026-hpc/tree/338e37ed4f74fc1d4f189af98379e725fcc16645)保存本次对应的代码、附录和数据，后续报告更新不改变该版本。

可以在仓库根目录执行 `python3 tools/verify_materials.py`，只读核对复制文件散列及所列正式记录，不重新运行性能实验。

## 两个项目

光追最终源码在 `hpc-raytracing/implementation/16fafcdc65f1ac9c25a14519ead75b345c88b82cd500f1da05e9f07ca99b6bc2/`。保留 O3、OpenMP 像素块并行、16 桶 SAH BVH 与最终命中后构造记录。同期正式对照 Render time 中位数 1968.697 → 85.006 秒，整体耗时比 23.16；该比值包含多个因素，不能解释为某一项优化的独立收益。

WorkSteal 源码在 `hpc-worksteal/`，采用固定任务集合、持久线程池和带锁双端队列。策略单独注册。第十六轮已于 10 月 27 日完成，随机 victim 未达到采用门槛；保留 round_robin、immediate、single，参数按负载选择。

## 已验证范围

性能记录来自 Ubuntu 24.04 / WSL1、本机 i9-13900HX。新的发布目录只复制既有证据，不重跑或补造性能样本。容器配置已提供但未实建；跨批耗时波动、局部性证据不足和历史对话附件缺失均保留说明。

光追题目和原始代码来自 [LZUOSS/LZUHPC](https://github.com/LZUOSS/LZUHPC/tree/33dad592cd74d8cf36ae7921a29c0e8393034a70/assignments/2026/autumn)，所用版本为 `33dad592cd74d8cf36ae7921a29c0e8393034a70`。OpenMP、BVH、SAH 与工作窃取为已有方法，本项目不声称发明这些算法。
