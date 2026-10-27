# 第八轮内存交错推荐

本轮通过冻结的双输入epoch主门槛及app护栏，采用可选memory_lanes=4。仅另存已测候选输入，默认仍为1；其他任务继续使用[历史配置](../verified/README.md)，其JSON及构建来源保留。

|配置|输入|epoch中位数，1→4路(ms)|epoch胜对|app中位数，1→4路(ms)|
|---|---|---:|---:|---:|
|[memory.json](memory.json)|seed41011，88元素/44 MiB|9.0979→5.7864|7/7|120.6910→112.0181|
|[memory-large.json](memory-large.json)|seed47017，136元素/68 MiB|11.6156→6.6841|7/7|183.5315→175.0829|

配置逐字复制已完成candidate的config.json，散列及原始路径见[builds.json](builds.json)，未增加计时或验收进程。每元素512 KiB、16 passes，16 workers、grain4、完整标量核验4线程、zeroed分配、填充线程1。4路只交错任务内独立递推，不跳过计算或参考核验。

必须使用本轮新Release：测量源码ID为`4c9cdd0f4aacf04acc313a4dda6c2ed1bf2151b37bf3ffad12059a031f4bc6bb`，二进制SHA256为`3b98bf25474bfc27a1b3af44cce428cf1a9e16705d940d3df0c1cec32efef275`；旧configs/verified指定的二进制不认识memory_lanes及其他新增参数。测量后新增的本文和配置不属于该测量源码快照。

实际Linux可执行文件：`/root/lzuhpc-experiments/ws-20261021-memory-kernel-release/build-none/worksteal`。使用已归档来源重建（从项目根目录执行；重建不自动重跑实验）：

```sh
cmake -S memory-kernel/snapshots/source/4c9cdd0f4aacf04acc313a4dda6c2ed1bf2151b37bf3ffad12059a031f4bc6bb -B build/memory-interleaved -DCMAKE_BUILD_TYPE=Release -DWS_COMPLETION_BATCH=32 -DWS_STEAL_SCRATCH=ON -DWS_ENABLE_IPO=ON -DWS_COMPUTE_LANES=8
cmake --build build/memory-interleaved -j2
# 按需单独复现已测配置
./build/memory-interleaved/worksteal --config configs/memory-interleaved/memory.json
```

两组epoch中位数分别约快1.572×/1.738×；app中位数仅下降约7.2%/4.6%，各有2/7对变慢。采用门槛是epoch≥6/7胜出且中位数下降≥10%，app中位数只需不退化超过5%，不是对应用收益的显著性检验。参考核验、初始化和身份散列仍占主要应用时间；阶段中位数不能相加。

这是同一新二进制内的执行内核收益，不是工作窃取策略收益，不与旧轮加速倍数相乘，也不证明相对历史推荐二进制的应用加速。其他seed、规模、粒度或硬件需另设实验。资源观察通过不等于物理独占。

证据：[报告](../../report/memory-kernel/第八轮内存执行交错报告-424ce55a.md)、[契约及结果](../../docs/28-第八轮内存执行契约与结果.md)、[冻结协议](../../docs/27-第八轮内存执行交错协议.md)、[Windows审计](../../memory-kernel/results/audit-17ca23a49da34a6198c79dbbc8438cbd.json)。原始数据和所有慢成功样本完整保留。
