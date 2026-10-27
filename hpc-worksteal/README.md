# Mini WorkSteal

本目录提供报告使用的 C++20 工作窃取运行时、配置、检查与所选原始记录。

- 项目实现：`include/worksteal/`、`src/`。
- 功能与扩展检查：`tests/`。
- 历史推荐与测量构建：`configs/verified/`、`configs/memory-interleaved/`。
- [仓库统一构建说明](../docs/reproduction.md)。
- [实验附录](../docs/appendices.md)与[数据范围](../docs/data-scope.md)。
- [第十六轮实际结果](docs/50-第十六轮Victim选择恢复结果.md)。

原项目的完整历史阅读入口保存在 `docs/project-readme-original.md`，部分链接指向本次未公开的历史材料。是否完成与结果解释以具体记录为准，不将历史注记当作当前验收结果。

`.devcontainer` 未实际构建验证；已有原生 Linux 功能复现。策略和内核的性能结论限定于报告所列输入、构建和测量环境。
