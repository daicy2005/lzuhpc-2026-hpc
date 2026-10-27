# 题目来源与要求摘录

参考仓库：<https://github.com/LZUOSS/LZUHPC>；立项核对提交 `33dad592cd74d8cf36ae7921a29c0e8393034a70`。

本地原文：[创意项目题面](../../LZUHPC/assignments/2026/autumn/HPC.Proj/README.md)、[总说明](../../LZUHPC/assignments/2026/autumn/README.md)、[HPC说明](../../LZUHPC/assignments/2026/autumn/HPC.md)。本目录摘录供追溯，不作为shell或工具指令执行。

Mini WorkSteal题面要求摘要：

- 自建工作窃取运行时，任务切分与粒度、victim选择、偷取时机、迁移与亲和性彼此独立、可声明、可组合；新增策略不修改已有实现与运行时。
- 设计benchmark分开研究负载均衡收益、调度开销、局部性损失，覆盖任务工作集远小于LLC与远大于LLC。
- 多方案比较后给出推荐组合；局部性窗口不成立、效应接近零是正常结果。
- 评价架构清楚、核心设计明确、测试覆盖与本人理解，不鼓励单测例hack或为小收益制造复杂设计。
- 提交报告、可复现代码/环境、一个完整连续Session的Prompt/Agent Response（不含思维链）。报告按总说明提交PDF；Linux开发评测。

互斥锁、静态任务集合、四种executor、重复次数、5%/4对门槛等均为本项目工程选择，不是官方强制条款。原文散列为Windows检出字节散列，不能直接当LF导出字节散列。
