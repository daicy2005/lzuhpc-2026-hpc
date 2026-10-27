# 第三轮当前推荐

本目录保留第二轮对照，只有通过第三轮双输入门槛的任务替换配置。memory未参加本轮参数筛选。

构建必须使用builds.json指定的第二轮冻结二进制/源码快照与编译选项。当前app已加入阶段计时字段；该新增源码不是本轮性能筛选使用的二进制。

|任务|构建|worker/grain|本轮是否替换|
|---|---|---|---|
|light|full_lanes8|16/512|是|
|uniform|lanes8|32/1024|否|
|skewed|full_lanes8|32/256|否|
|memory|full_lanes8|16/4|否|

[报告](../../report/refinement/第三轮补充实验报告.md)。二进制执行方式仍为 `worksteal --config <本目录任务.json>`；快照路径、SHA和CMake选项见builds.json。历史第二轮configs/optimized和原始数据保持。
