# 题目要求与完成情况

我按 [光追题面](https://github.com/LZUOSS/LZUHPC/blob/33dad592cd74d8cf36ae7921a29c0e8393034a70/assignments/2026/autumn/HPC.RayTracing/README.md)和 [Mini WorkSteal 题面](https://github.com/LZUOSS/LZUHPC/blob/33dad592cd74d8cf36ae7921a29c0e8393034a70/assignments/2026/autumn/HPC.Proj/README.md)整理了下面的对应关系，详细实验可以从表后的链接找到。

|题目要求|做了什么|结果和说明|
|---|---|---|
|光追按正式参数评测|1200×675、200 spp、depth=50、seed=42；原版与最终版各三次|采用本机同批 Render time，中位数 1968.697 / 85.006 秒|
|图像达到 45 dB|六次输出逐通道一致，MSE=0、PSNR=inf|报告第2节及原始检查记录|
|不改受限文件|四个文件与官方 Git blob 完全相同|见 [文件比较结果](official-source-check.json)|
|Linux 开发和测试|Ubuntu 24.04 / WSL1 构建、正确性检查与计时|题面允许 WSL；DevContainer 是建议方式，尚未实建|
|WorkSteal 策略独立可组合|Partition、Placement、Victim、Timing、Migration、Affinity；test_reverse 与 disabled_yield 的扩展检查|新增策略采用独立文件和注册，不改原运行时及已有策略|
|量化负载均衡收益|相同 yield 的 off/on、两输入、两粒度、两布局，各五对|集中布局中位数时间比 2.55—5.28，八组均为 5/5 对 on 更快|
|量化调度开销|单工作线程，固定内核和工作量，连续串行及三种粒度各五次|64 任务增至 32768 任务，epoch 增加 0.4889 ms（20.6%）；是调度路径综合成本|
|覆盖任务远小于 LLC|每任务 8 KiB，系统显示 LLC 约36 MiB|固定执行线程的预读对照及实际动态窃取，见第一组补测|
|覆盖任务远大于 LLC|每任务 288 MiB，约为 LLC 的8倍；四任务共1152 MiB|两执行线程的预读对照及四线程 off/on，共30次计时；动态诊断3/4任务由非 home 执行|
|分析局部性影响|固定执行线程、改变预读线程；重新核对80次计时的40对结果及封存源码|大任务比值1.009、0.988，other更慢分别4/5、2/5对；未可靠分离纯缓存损失，见[进一步分析](locality-analysis.md)|
|比较多种策略并选择组合|粒度、布局、批量迁移、退避、随机 victim、执行内核等比较|保留 round_robin、immediate、single，线程数与粒度按负载选择；不声称全局最优|
|代码、环境及数据可复现|原始配置、命令、源码、构建和检查日志、独立压缩包及校验工具|报告仍为一份 PDF，完整实验放在仓库|

两组新补测共 41 个条件、287 次运行，其中 205 次用于正式计时；41 次诊断、41 次预热另存。原有 663 次计时不改，总共整理 868 次 WorkSteal 计时。准备阶段中止的四次诊断未计入正式统计。

局部性是这次还没解释清楚的部分：换预读线程后，有的条件略慢，有的反而略快，没有一致趋势。题面允许局部性窗口不成立时效应接近零，但本机没有可靠 PMU，WSL1 的线程绑定也还不能证明数据实际留在哪级缓存。因此，我只报告这些对照测到了什么，没有把差值都归到缓存上，也没有把三个效应直接相加。

- [相同空闲策略、调度路径及预读对照](../supplements/mechanism-controls/README.md)
- [单任务大于 LLC 的对照](../supplements/large-task-controls/README.md)
- [完整补充实验与复现说明](appendices.md)
