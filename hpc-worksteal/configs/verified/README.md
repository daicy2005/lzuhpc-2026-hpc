# 第四轮当前配置

默认仍串行核验；下表显式设置measurement.reference_workers。第四轮性能证据来自共享WSL1主机，存在其他32线程实验干扰；2026-10-21第五轮复用原二进制，在通过已定义门禁的观测窗口另用两个新输入完成确认。原JSON与builds.json保持第四轮封存内容，本轮确认状态单独记录于[第五轮结果](../../docs/22-第五轮结果与后续方向.md)。观测窗口不等于物理独占。

|任务|执行构建|执行worker/grain|核验线程|
|---|---|---|---|
|light|full_lanes8|16/512|1|
|uniform|lanes8|32/1024|32|
|skewed|full_lanes8|32/256|32|
|memory|full_lanes8|16/4|4|

使用builds.json记录的verification/evidence源码/二进制快照及CMake选项重新构建；核验线程数是运行时配置。构建后直接运行 `worksteal --config configs/verified/<任务>.json`。

[完整报告](../../report/verification/第四轮并行核验报告.md)。每个元素完整重算，最后顺序散列。此改进针对应用核验阶段；执行epoch计时边界不变。历史configs/refined和原始实验保持。

[第五轮确认报告](../../report/confirmation/第五轮空闲窗口确认报告-cdcc790a.md)：uniform32、skewed32、memory4均在两个新输入取得7/7对应用端到端胜出，中位数收益分别9.584/9.743倍、11.279/11.630倍、1.468/1.496倍；比较基准为同二进制reference_workers=1。light未复测，保留原选择。第五轮新输入的完整实际配置在confirmation-retry/results/frozen-plan.json和逐run config.json中，不用第四轮JSON冒充新输入。

第六轮[并行初始化确认](../../docs/24-第六轮初始化契约与结果.md)未过门槛，仍使用本目录原JSON及builds.json，不改变其二进制来源。当前开发源码支持可选initialization_workers，但新参数不能传给这里指定的旧二进制。第六轮实验构建及原始结果单独保留于initialization/，没有新的推荐配置。

第七轮[覆盖式分配确认](../../docs/26-第七轮存储契约与结果.md)亦未过双输入门槛，继续保留本目录全部原JSON及builds.json。当前开发源码省略data_allocation仍默认zeroed；旧二进制不识别该新参数。第七轮可选overwrite实现及allocation/数据只用于实验，不建立configs/overwrite，不替换历史二进制。

第八轮[内存执行交错](../../docs/28-第八轮内存执行契约与结果.md)通过epoch主门槛及app护栏，两个已测输入另存[configs/memory-interleaved](../memory-interleaved/README.md)。新参数memory_lanes=4必须使用该目录builds.json指定的新构建；本目录四份任务JSON及builds.json仍为历史原件，不将新配置传给旧二进制。省略memory_lanes的默认值仍为1。
