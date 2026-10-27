# 第二轮确认配置

每个 JSON 仅表示运行时配置；必须同时使用 builds.json 中该类的构建参数。第一轮 recommended/ 是历史基线，保留原件。本轮四类候选均通过两个新输入的预定晋升门槛。

| 配置 | 构建 preset | worker | grain |
|---|---|---|---|
| light.json | optimized-light | 16 | 256 |
| uniform.json | optimized-uniform | 32 | 1024 |
| skewed.json | optimized-skewed | 32 | 256 |
| memory.json | optimized-skewed | 16 | 4 |

从项目根目录在 Linux 执行（preset 需要 CMake 3.21+；实际验证工具为3.28）：

```sh
cmake --preset optimized-skewed
cmake --build --preset optimized-skewed
ctest --preset optimized-skewed
./build/optimized-skewed/worksteal --config configs/optimized/skewed.json
./build/optimized-skewed/worksteal --config configs/optimized/memory.json
```

light/uniform 使用对应 preset、build 子目录和 JSON。preset 参数对应实际已测构建；preset 文件只通过解析和参数一致性检查，不另称从该 preset 全新编译计时通过。保留原 flags 路径亦可：`cmake -S . -B build/custom -DCMAKE_BUILD_TYPE=Release` 加 builds.json 的 `-DWS_...` 选项。

CPU 掩码按本机逻辑 CPU 列表声明，其他机器运行前需核对可用 CPU。收益是实现、线程数和粒度的联合收益，不是同线程数单一策略加速，也不是跨机器保证。详见 report/optimization/第二轮优化报告.md 和 optimization/results/optimization-summary.json。
