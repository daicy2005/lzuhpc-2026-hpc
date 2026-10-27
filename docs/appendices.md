# 附录A 其他尝试与结果

## A.1 光线追踪的代表性未采用方案

除正文方案外，我还试过以下方向。先用宽 1200、32 spp 筛选，再将表现较好的候选放到正式 200 spp 下比较；小图和专项检查用于检查正确性。表中标为筛选的结果，不能直接当作正式规模的结论。

|候选方向|阶段|结果与处理|
|---|---|---|
|当前内核 LTO|正式|中位数 23.762 → 17.327 秒，但仅 2/3 对更快，未采用|
|球体 SIMD|筛选|未通过，保留标量距离计算|
|紧凑 BVH 节点|筛选|节点更小，但筛选耗时未改善|
|路径去递归|正式|中位数略低，但配对次数和耗时范围未同时通过筛选|
|四子宽 BVH|正式|未通过筛选，继续使用二叉 BVH|

LTO 首批有七次运行没有正确传入编译和链接参数，表中只使用修正后的批次，原记录另存。有些候选虽然中位数略低，但没有同时通过配对次数和耗时范围的筛选，所以没有保留。其他轮次可在各项目的 report/ 和 results/ 中查看。

## A.2 WorkSteal 的其他阶段与策略尝试

|方向|观察与处理|
|---|---|
|执行内核与参数组合|按负载比较完成计数批处理、暂存、LTO 与独立计算链；收益也包含内核变化|
|完整核验并行化|换输入后仍有收益，保留；继续逐元素完整标量重算，缩短 app 时间|
|内存四路执行交错|两个输入 epoch 时间比 1.572 / 1.738，均 7/7 对更快，保留该轮配置|
|内存初始化与身份散列|没有保留新配置；某一阶段变快，不一定缩短 app 总时间|
|空闲退避|第十五轮未同时满足目标性能和退化限制，保留 immediate|
|随机 victim|第十六轮完成 84 份正式计时；两个集中输入分别 6/7、2/7 对更快，收益不稳定，保留 round_robin|

第三轮分阶段计时发现，uniform 和 skewed 的完整核验耗时占比中位数约为 96.5% 和 97.1%。因此第四、五轮先改核验，让它也能并行执行；这 12 份阶段观测没有混入正式计时。内存四路交错则改的是任务内核，仍保留各元素原有的递推和访问顺序，核验时照常逐元素标量重算。

第十五轮首批因采集器缓存键没有区分 grain 而中止，没有产生正式计时。复查应用输出、修正采集器后，在新目录重新运行。第十六轮最初因资源条件不足没有开始，10 月 27 日补跑，完成 114 个进程，其中 84 份为正式计时。随机 victim 在两个新输入上没有都通过筛选，最后保留 round_robin；最初未运行的记录也保留了原状态。

# 附录B 代码与环境复现

## B.1 光线追踪

最终源码位于 hpc-raytracing/implementation/ 下以 16fafcdc 开头的目录，完整版本号与命令见 results/final-selection.json。环境为 Ubuntu 24.04、G++ 13.3、GNU Make 和 OpenMP。将环境变量 OFFICIAL 设为官方 HPC.RayTracing 目录的绝对路径，进入最终源码根目录后执行：

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

具体配置在 configs/verified/，memory 在 configs/memory-interleaved/，对应 builds.json 记录了源码、二进制和编译选项。我在新的 Linux 目录中重新构建过三种 Release，运行了 CTest，六个原推荐配置也都通过完整核验。官方推荐的 DevContainer 配置已经提供，但还没有实际构建；目前完成的是原生 Linux 复现。

# 附录C 数据入口与参考资料

## C.1 对照与原始记录

以下路径分别从 hpc-raytracing/ 和 hpc-worksteal/ 起算。可以先在汇总中找到实验组和 run_id，再查看对应目录中的配置、命令、日志、图像质量结果和代码版本。

|项目与内容|数据入口|
|---|---|
|光追整体成绩|results/round16-comparison.json|
|光追局部对照与其他尝试|results/round2-groups.json；results/round8-selection.json；各轮 selection|
|光追最终源码与全部运行|results/final-selection.json；runs/<run_id>/|
|WorkSteal 各章数据|report/student/evidence-index.json；results/study-summary.json|
|窃取边界与批量确认|stealing-boundary/results/；batch-migration/results/|
|内存内核与退避|memory-kernel/results/；idle-backoff/results/|
|功能复现|submission/reproduction/20261025/receipt.json|

这份报告使用的 WorkSteal 数据包括原有 579 份正式记录和第十六轮新增的 84 份，共 663 份，另有 12 份阶段观测。663 不是全部历史运行次数，正文也只讨论其中几组有代表性的比较。完整记录保留在项目目录。原始数据的 Linux 与 Windows 副本位于同一物理盘，不能当作独立备份。

代码与复现环境通过配套仓库提供。官方要求的连续对话记录（Prompt File）另行保留，本次暂未上传。

## C.2 方法与资料来源

[1] LZUOSS/LZUHPC，2026 秋季纳新说明、HPC 题面及项目要求。核对版本 33dad592cd74。

https://github.com/LZUOSS/LZUHPC/tree/33dad592cd74d8cf36ae7921a29c0e8393034a70/assignments/2026/autumn

[2] PBRT 第四版，Bounding Volume Hierarchies。

https://pbr-book.org/4ed/Primitives_and_Intersection_Acceleration/Bounding_Volume_Hierarchies

[3] OpenMP 5.2 与 GCC 13.3 优化文档；oneTBB 调度、粒度与缓存亲和性说明；Google Benchmark 实验方法。精确链接及资料记录见光追 operations/community-research-*/ 和 WorkSteal docs/11-社区与本机评审.md。

OpenMP、BVH、SAH 和工作窃取都是已有方法。我做的是在题目约束下实现和调整这些方法，再通过实验选择配置。其他调度模型的理论结论是否适用于这个带锁、固定任务集的运行时，还需要另外论证。

AI 辅助包括资料搜集、备选方案梳理、部分代码编写和数据整理。
