# 附录A 补充实验

## A.1 其他光追优化方案

以下方案先在宽 1200、32 spp 下测试，表现较好的再用 200 spp 比较。小图和专项测试用于检查正确性。表中 32 spp 的结果只说明初步测试的表现，不能直接推断 200 spp 下的速度。

|方案|每像素采样|实验结果|
|---|---|---|
|LTO|200 spp|中位数 23.762 → 17.327 秒，但只有 2/3 对更快，未采用|
|球体 SIMD|32 spp|初测没有通过筛选，继续使用标量计算|
|紧凑 BVH 节点|32 spp|节点更小，但耗时没有改善|
|用循环替代递归|200 spp|中位数略低，但没有同时满足配对次数和耗时要求|
|四叉 BVH|200 spp|没有满足筛选要求，继续使用二叉 BVH|

LTO 最初有七次运行没有正确传入编译和链接参数，因此表中使用修正后重测的结果。有些方案虽然中位数略低，但没有满足正文所述的配对次数和耗时要求，最终没有采用。完整结果在各项目的 report/ 和 results/ 中。

## A.2 WorkSteal 的其他优化

|方案|实验结果|
|---|---|
|执行内核与参数组合|按负载比较完成计数批处理、暂存、LTO 与独立计算链；收益也包含内核变化|
|完整核验并行化|换输入后仍有收益，保留；继续逐元素完整标量重算，缩短 app 时间|
|内存四路执行交错|两个输入的 epoch 时间比分别为 1.572 和 1.738，各 7 对比较全部更快，采用该方案|
|内存初始化与哈希计算|没有采用新方案；某一阶段变快，不一定缩短 app 总时间|
|空闲退避|没有同时满足目标性能和其他负载的退化限制，继续使用 immediate|
|随机 victim|两个集中输入分别为 6/7、2/7 对更快，收益不稳定，继续使用 round_robin|

分阶段计时发现，uniform 和 skewed 的完整核验耗时占比中位数约为 96.5% 和 97.1%，因此也尝试将核验并行化。这部分使用 12 次单独测试，没有并入性能对照。内存四路交错则改的是任务内核，仍保留各元素原有的递推和访问顺序，核验时逐元素标量重算。

退避实验曾因采集器缓存键没有区分 grain 而中止，修正后重新测试，中止的运行没有计入结果。随机 victim 实验包含 84 次性能计时；两个新输入上的结果不一致，最终仍采用 round_robin。

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

报告使用了 663 次 WorkSteal 性能计时和 12 次分阶段测试，其中随机 victim 的性能计时为 84 次。对应运行均可通过索引查找。

代码与复现环境通过配套仓库提供。官方要求的连续对话记录（Prompt File）另行保留，本次暂未上传。

## C.2 方法与资料来源

[1] LZUOSS/LZUHPC，2026 秋季纳新说明、HPC 题面及项目要求。使用版本 33dad592cd74。

https://github.com/LZUOSS/LZUHPC/tree/33dad592cd74d8cf36ae7921a29c0e8393034a70/assignments/2026/autumn

[2] PBRT 第四版，Bounding Volume Hierarchies。

https://pbr-book.org/4ed/Primitives_and_Intersection_Acceleration/Bounding_Volume_Hierarchies

[3] OpenMP 5.2 与 GCC 13.3 优化文档；oneTBB 调度、粒度与缓存亲和性说明；Google Benchmark 实验方法。链接见光追 operations/community-research-*/ 和 WorkSteal docs/11-社区与本机评审.md。

OpenMP、BVH、SAH 和工作窃取都是已有方法。我做的是在题目约束下实现和调整这些方法，再通过实验选择配置。其他调度模型的理论结论是否适用于这个带锁、固定任务集的运行时，还需要另外论证。

AI 辅助包括资料搜集、备选方案梳理、部分代码编写和数据整理。
