# 附录A 补充实验

## A.1 其他光追优化方案

为了缩短尝试的时间，以下方案先在宽 1200、32 spp 下比较，表现较好的再测 200 spp；小图和专项测试另外检查正确性。表中 32 spp 的结果只作为初步筛选，不能直接推断 200 spp 下的速度。

|方案|每像素采样|实验结果|
|---|---|---|
|LTO|200 spp|中位数 23.762 → 17.327 秒，但只有 2/3 对更快，未采用|
|球体 SIMD|32 spp|初测没有通过筛选，继续使用标量计算|
|紧凑 BVH 节点|32 spp|节点更小，但耗时没有改善|
|用循环替代递归|200 spp|中位数略低，但没有同时满足配对次数和耗时要求|
|四叉 BVH|200 spp|没有满足筛选要求，继续使用二叉 BVH|

LTO 测试中出过一次参数问题：最初七次没有正确传入编译和链接参数，修正后重新测了，表中使用的是重测结果。有些方案中位数略低，但重复比较时不够稳定，没有达到正文的筛选要求，最后没有留下。完整结果在各项目的 report/ 和 results/ 中。

## A.2 WorkSteal 的其他优化

|方案|实验结果|
|---|---|
|执行内核与参数组合|按负载比较完成计数批处理、暂存、LTO 与独立计算链；收益也包含内核变化|
|完整核验并行化|换输入后仍有收益，保留；继续逐元素完整标量重算，缩短 app 时间|
|内存四路执行交错|两个输入的 epoch 时间比分别为 1.572 和 1.738，各 7 对比较全部更快，采用该方案|
|内存初始化与哈希计算|没有采用新方案；某一阶段变快，不一定缩短 app 总时间|
|空闲退避|没有同时满足目标性能和其他负载的退化限制，继续使用 immediate|
|随机 victim|两个集中输入分别为 6/7、2/7 对更快，收益不稳定，继续使用 round_robin|

分开看各部分耗时后，我发现 uniform 和 skewed 的完整核验占比中位数约为 96.5% 和 97.1%，于是也尝试把核验并行化。这部分用了 12 次单独测试，没有并入性能对照。内存四路交错改的是任务内核，各元素原有的递推和访问顺序仍保留，检查结果时再逐元素标量重算。

退避实验的采集器也出过问题，缓存键没有区分 grain，修正后重新测试，中止的运行不计入结果。随机 victim 共做了 84 次性能计时，但两个新输入上的表现不一致，所以仍使用 round_robin。

## A.3 相同空闲策略下的补测

[逐次结果、完整记录与源码](../supplements/mechanism-controls/README.md)

补测共 35 个条件，每个条件一次诊断、一次预热、五次计时，共 245 次运行。所有运行都通过完整输出核验，诊断另检查任务恰好一次及执行归属。下表为相同 yield 空闲策略下的 off/on 中位数时间比；八组均为 5/5 对 on 更快。

|输入|grain|集中 off / on|分散 off / on|
|---|---|---|---|
|170021|8|5.275|1.552|
|170021|256|2.553|1.828|
|176023|8|2.656|1.423|
|176023|256|5.074|1.257|

早先还测过 grain=16384 和每任务 288 MiB 的情况。后者虽然够大，但两个执行方向没有一致趋势，六组动态诊断也没有成功窃取，没法据此估计迁移代价。后来补测时，我把问题分开：固定执行线程比较预读，再单独检查窃取。三种总数据规模都发生了成功窃取，但还没有得到稳定的纯缓存损失估计。

完整记录和源码在 supplements/mechanism-controls/experiment.zip，逐次耗时、条件和 run_id 在同目录 summary.json。准备时，采集器误把 serial 也当成线程池来检查，导致四次诊断后停止；修正后换新目录重跑，这四次不进入正式统计。

## A.4 单任务远大于 LLC

[逐次结果、完整记录与源码](../supplements/large-task-controls/README.md)

这一组每任务 288 MiB，约为系统显示 LLC 的 8 倍，四个任务总数据为 1152 MiB。使用同一个通过检查的二进制，另换输入 seed=194033，每个条件测五次，预热和诊断另存。same / other 表示由执行线程自身或另一线程预读；动态 off / on 两者空闲时均 yield。

|对照|配置|epoch / ms|
|---|---|---|
|preread-target0|same|446.4460|
|preread-target0|other|450.6728|
|preread-target1|same|452.3544|
|preread-target1|other|446.7660|
|dynamic|off|458.6950|
|dynamic|on|127.4055|

动态开关的中位数时间比为 3.60，诊断显示 3/4 个任务由非 home 执行。这个差值包含分担计算、调度和内存访问的共同影响。固定执行线程后的两个预读耗时比为 1.009、0.988，仍没显示出一致的变慢趋势。题面允许局部性窗口不成立时效应接近零，但本机的这些结果还不足以说明其他任务也没有局部性代价。完整记录及源码见 supplements/large-task-controls/。

## A.5 局部性对照的进一步分析

我重新核对了两组补测中与预读有关的 80 次计时，按原重复编号组成 40 对，没有新增实验。每组固定输入、任务大小、执行线程、队列和内核，只改变预读线程。same 为执行线程自己预读，other 为另一线程预读；两个执行方向分别比较。

|每任务 / 总数据|执行线程|same / ms|other / ms|中位数比|逐对比值范围|other 更慢|
|---|---|---|---|---|---|---|
|8 KiB / 512 KiB|0|0.1957|0.1998|1.021|0.802-1.283|4/5|
|8 KiB / 512 KiB|1|0.2079|0.1987|0.956|0.807-1.076|2/5|
|72 KiB / 4.5 MiB|0|1.5208|1.5308|1.007|0.990-1.074|4/5|
|72 KiB / 4.5 MiB|1|1.6321|1.6350|1.002|0.883-1.101|2/5|
|4.5 MiB / 288 MiB|0|99.9010|101.7545|1.019|0.967-1.024|3/5|
|4.5 MiB / 288 MiB|1|102.9606|100.3162|0.974|0.906-1.052|2/5|
|288 MiB / 1152 MiB|0|446.4460|450.6728|1.009|0.954-1.023|4/5|
|288 MiB / 1152 MiB|1|452.3544|446.7660|0.988|0.921-1.030|2/5|

中位数比是 other 中位数 / same 中位数；逐对比值是同一重复编号下的 other / same，范围为五对的实际最小值和最大值，不是置信区间。八组范围都跨过1。72 KiB 任务的执行1中位数比略大于1，但只有2/5对 other 更慢，也说明两种统计量不能互相替代。每组仅五对，不能据此证明两者等价，或把观测差异当作其他任务的缓存损失上限。

结合封存源码，我认为当前实验对缓存差异的灵敏度还有几处限制。首先，逻辑CPU0/1未确认属于不同物理核，换线程不保证换了私有缓存。其次，预读在整个任务集开始前完成；总数据超过LLC后，早先数据可能已经被后续读取挤出。最后，每个元素连续扫描四遍，首次访问与后续复用混在总计时里。标量内核还存在逐字递推依赖，没有独立带宽和PMU证据，不能只凭数组大就断言带宽受限。这些是可能影响观测的机制，没有证明哪一项实际主导结果。

动态诊断证明发生了窃取，但不能证明每次正式计时的缓存状态或迁移次数都相同。大任务off/on约 3.60 倍，是并行分担、调度和内存访问的共同效果；不能减去固定执行线程的预读比值，就拆出某一项的份额。home 表示预读归属，不是NUMA页归属。

若继续补测，我会先在原生Linux确认不同物理核与缓存共享关系，再让一个数据块预读后立即执行，分别记录首次与后续扫描，并增加经过检查的热、冷缓存参考。工作集还应覆盖私有缓存与LLC之间的中间区间。这些是后续设计，当前仍只能说：已覆盖工作集两端和实际窃取，但尚未得到可靠的纯缓存损失估计。逐次路径、重算脚本和完整说明见 docs/locality-analysis.md。

# 附录B 代码与环境复现

## B.1 光线追踪

光追源码位于 hpc-raytracing/implementation/ 下以 16fafcdc 开头的目录，完整路径见 results/final-selection.json。依赖 Ubuntu 24.04、G++ 13.3、GNU Make 和 OpenMP。将环境变量 OFFICIAL 设为官方 HPC.RayTracing 目录的绝对路径，进入源码目录后执行：

```bash
make -B -j4
./build/RayTracing 1200 200 out.ppm
python3 "$OFFICIAL/tools/check_psnr.py" \
  "$OFFICIAL/reference.ppm" out.ppm
```

默认使用 C++20、O3 和 OpenMP，没有启用 LTO、PGO、native 或 fast-math。上述命令可用于构建和功能检查。要按历史配置比较性能，还需设置记录中的 32 线程、close 和显式 OMP_PLACES；换机器时应先核对 CPU 编号，耗时也可能不同。

## B.2 Mini WorkSteal

Linux 环境需要 CMake、C++20 编译器、pthread、Python3 和 nlohmann-json3-dev。在 hpc-worksteal 根目录运行：

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
./build/worksteal --config configs/runtime/diagnostic.json
```

默认 Release 可用于功能检查。若要重建实验中的优化版本，还需按 builds.json 设置完成计数批次、窃取暂存、IPO 和计算链数。下表列出最终配置，ref 是完整参考核验使用的线程数。

|任务|worker / grain|执行内核|ref|测量构建|
|---|---|---|---|---|
|light|16 / 512|compute_lanes8|1|full_lanes8|
|uniform|32 / 1024|compute_lanes8|32|lanes8|
|skewed|32 / 256|compute_lanes8|32|full_lanes8|
|memory|16 / 4|memory_lanes4|4|Release / memory_lanes4|

配置文件在 configs/verified/，内存负载的配置在 configs/memory-interleaved/。对应的 builds.json 列出了源码版本和编译选项。在 Linux 下重新构建后，三种 Release 版本均运行了 CTest，六个测试配置也都通过完整核验。DevContainer 配置已提供，但还没有实际构建；目前验证的是原生 Linux 环境。

# 附录C 实验记录与参考资料

## C.1 实验记录

以下路径分别相对于 hpc-raytracing/ 和 hpc-worksteal/。汇总文件中列有实验组和 run_id，对应运行目录保存配置、命令和输出日志。

|内容|文件或目录|
|---|---|
|光追整体耗时对照|results/round16-comparison.json|
|光追局部对照与其他尝试|results/round2-groups.json；results/round8-selection.json；各轮 selection|
|光追最终源码与全部运行|results/final-selection.json；runs/<run_id>/|
|WorkSteal 各章数据|report/student/evidence-index.json；results/study-summary.json|
|任务粒度与批量窃取|stealing-boundary/results/；batch-migration/results/|
|内存内核与退避|memory-kernel/results/；idle-backoff/results/|
|构建与测试记录|submission/reproduction/20261025/receipt.json|

WorkSteal 共整理了 868 次性能计时：原有 663 次，加上机制补测的 175 次和单任务大于 LLC 的 30 次；另有 12 次分阶段测试。补测的预热、诊断和未完成的采集单独保存，未计入性能中位数。补测汇总及完整记录分别见仓库 supplements/mechanism-controls/ 和 supplements/large-task-controls/。

## C.2 方法与资料来源

[1] LZUOSS/LZUHPC，2026 秋季纳新说明、HPC 题面及项目要求。使用版本 33dad592cd74。

https://github.com/LZUOSS/LZUHPC/tree/33dad592cd74d8cf36ae7921a29c0e8393034a70/assignments/2026/autumn

[2] PBRT 第四版，Bounding Volume Hierarchies。

https://pbr-book.org/4ed/Primitives_and_Intersection_Acceleration/Bounding_Volume_Hierarchies

[3] OpenMP 5.2 与 GCC 13.3 优化文档；oneTBB 调度、粒度与缓存亲和性说明；Google Benchmark 实验方法。链接见光追 operations/community-research-*/ 和 WorkSteal docs/11-社区与本机评审.md。

OpenMP、BVH、SAH 和工作窃取都是已有方法。这次项目中，我主要做了实现、配置比较和结果检查，再根据实验决定留下哪些修改。这个运行时使用带锁队列和固定任务集，引用其他调度模型的理论结论时，还需要检查它们的假设是否适用。

AI 辅助包括资料搜集、备选方案梳理、部分代码编写和数据整理。
