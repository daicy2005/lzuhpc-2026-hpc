# 实现目录

尚无运行时代码。计划runtime/、executors/、policies/、workloads/、platform/、app/，模块职责见docs/02。Linux实现放独立项目工作目录，验散列后归档到这里，不复制光追的运行时或性能数据冒充新项目实现。
# 实现状态（2026-10-16）

已有 app/main.cpp、runtime/worker_pool.cpp、policies/register_defaults.cpp、workloads/workload.cpp、platform/probe.cpp。实际依赖边界以公共头文件为准；初版按模块聚合相关策略实现，新增策略可独立注册，不需修改核心。

