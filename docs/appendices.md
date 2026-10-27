# 附录A 补充探索与采用依据

## A.1 光线追踪的代表性未采用方案

除正文方案外，还比较了以下方向。筛选使用 1200 宽、32 spp，晋级后才使用正式 200 spp；小图与专项检查用于正确性。未通过筛选不等于已证明正式规模更慢。

|候选方向|阶段|结果与处理|
|---|---|---|
|当前内核 LTO|正式|中位数 23.762 → 17.327 秒，但仅 2/3 对更快，未采用|
|球体 SIMD|筛选|未通过，保留标量距离计算|
|紧凑 BVH 节点|筛选|节点更小，但筛选耗时未改善|
|路径去递归|正式|中位数略低，配对与范围未达保留条件|
|四子宽 BVH|正式|未达保留条件，保留二叉 BVH|

LTO 首批有七次运行未正确传入编译和链接参数，原记录单独保留；表中使用更正后的有效批次。候选中位数略低而配对与范围未通过时，仍按事前规则不采用。其他轮次保留于各项目的 report/ 和 results/，不逐项展开。

## A.2 WorkSteal 的其他阶段与策略尝试

|方向|观察与处理|
|---|---|
|执行内核与联合参数|完成计数批处理、暂存、LTO 与独立计算链按负载组合确认；不能全部归因于窃取|
|完整核验并行化|新输入确认后保留；仍逐元素完整标量重算，收益体现在 app|
|内存四路执行交错|两个输入 epoch 时间比 1.572 / 1.738，均 7/7 对更快，保留该轮配置|
|内存初始化与身份散列|多项候选未形成新推荐；阶段成本转移不足以证明 app 净收益|
|空闲退避|第十五轮未通过主目标与退化限制，保留 immediate|
|随机 victim|第十六轮 84 份正式计时完成；两个集中输入分别 6/7、2/7 对更快，未通过共同采用门槛，保留 round_robin|

第三轮另存的阶段观测显示，uniform/skewed 完整核验耗时占比中位数约为 96.5%/97.1%，因此第四、五轮转向核验并行化。这 12 份观测与正式计时分开。内存四路交错保留各元素原有递推与访问顺序，完整标量核验仍逐元素重算；其收益属于任务内核。

第十五轮首批因采集器缓存键未区分 grain 而中止，正式计时为 0；独立复核应用输出后，在新目录修正并恢复完整流程。第十六轮最初因资源条件未满足而未运行；10 月 27 日另建恢复批次，完成 114 个进程，其中正式计时 84 份。随机 victim 未达到两个新输入的共同采用门槛，继续保留 round_robin；最初的准备记录仍按原状态保存。

# 附录B 代码与环境复现

## B.1 光线追踪

最终源码位于 hpc-raytracing/implementation/ 下以 16fafcdc 开头的目录，完整身份与命令见 results/final-selection.json。环境为 Ubuntu 24.04、G++ 13.3、GNU Make 和 OpenMP。将环境变量 OFFICIAL 设为官方 HPC.RayTracing 目录的绝对路径，进入最终源码根目录后执行：

```bash
make -B -j4
./build/RayTracing 1200 200 out.ppm
python3 "$OFFICIAL/tools/check_psnr.py" \
  "$OFFICIAL/reference.ppm" out.ppm
```

默认编译为 C++20、O3、OpenMP，无 LTO、PGO、native 或 fast-math。上述命令用于构建和功能检查；历史成绩还需复用记录中的 32 线程、close 与显式 OMP_PLACES。CPU 编号依赖机器，换机需核实，不保证复现原耗时。

## B.2 Mini WorkSteal

Linux 环境需要 CMake、C++20 编译器、pthread、Python3 和 nlohmann-json3-dev。在 hpc-worksteal 根目录运行：

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
./build/worksteal --config configs/runtime/diagnostic.json
```

默认 Release 用于功能检查，不自动等同于优化测量构建。重建历史优化内核需按 builds.json 设置完成计数批次、窃取暂存、IPO 和计算链数。下表列出保留配置，ref 为完整参考核验线程数。

|任务|worker / grain|执行内核|ref|测量构建|
|---|---|---|---|---|
|light|16 / 512|compute_lanes8|1|full_lanes8|
|uniform|32 / 1024|compute_lanes8|32|lanes8|
|skewed|32 / 256|compute_lanes8|32|full_lanes8|
|memory|16 / 4|memory_lanes4|4|Release / memory_lanes4|

具体配置位于 configs/verified/，memory 位于 configs/memory-interleaved/。对应 builds.json 记录源码、二进制和编译选项。已有一次新目录 Linux 功能复现：三种 Release 运行 CTest，六个原推荐配置通过完整核验。DevContainer 配置已提供但未实际构建；官方推荐使用容器配置，本项目当前复现依据为原生 Linux 构建记录。

# 附录C 数据入口与参考资料

## C.1 对照与原始记录

以下路径分别相对于 hpc-raytracing/ 和 hpc-worksteal/。汇总可定位组和 run_id，原始目录保存实际配置、命令、日志、质量结果及版本来源。

|项目与内容|数据入口|
|---|---|
|光追整体成绩|results/round16-comparison.json|
|光追局部对照与其他尝试|results/round2-groups.json；results/round8-selection.json；各轮 selection|
|光追最终源码与全部运行|results/final-selection.json；runs/<run_id>/|
|WorkSteal 各章数据|report/student/evidence-index.json；results/study-summary.json|
|窃取边界与批量确认|stealing-boundary/results/；batch-migration/results/|
|内存内核与退避|memory-kernel/results/；idle-backoff/results/|
|功能复现|submission/reproduction/20261025/receipt.json|

WorkSteal 的综合输入包含原有 579 份正式记录和第十六轮新增的 84 份，共 663 份，另有 12 份独立阶段观测；这些数字不是全部历史研究进程数。完整记录保留在项目目录，本报告只选取代表性比较。原始数据的 Linux 与 Windows 镜像位于同一物理盘，尚非独立故障备份。

代码与复现环境通过配套仓库提供。官方要求的连续对话记录（Prompt File）另行保留，本次暂未上传。

## C.2 方法与资料来源

[1] LZUOSS/LZUHPC，2026 秋季纳新说明、HPC 题面及项目要求。核对版本 33dad592cd74。

https://github.com/LZUOSS/LZUHPC/tree/33dad592cd74d8cf36ae7921a29c0e8393034a70/assignments/2026/autumn

[2] PBRT 第四版，Bounding Volume Hierarchies。

https://pbr-book.org/4ed/Primitives_and_Intersection_Acceleration/Bounding_Volume_Hierarchies

[3] OpenMP 5.2 与 GCC 13.3 优化文档；oneTBB 调度、粒度与缓存亲和性说明；Google Benchmark 实验方法。精确链接及资料记录见光追 operations/community-research-*/ 和 WorkSteal docs/11-社区与本机评审.md。

OpenMP、BVH、SAH 和工作窃取均为已有方法。项目工作是针对题目约束实现、适配、比较和选择，不将既有算法或其他调度模型的理论保证直接视为本项目结论。

AI 辅助包括资料搜集、备选方案梳理、部分代码编写和数据整理。
