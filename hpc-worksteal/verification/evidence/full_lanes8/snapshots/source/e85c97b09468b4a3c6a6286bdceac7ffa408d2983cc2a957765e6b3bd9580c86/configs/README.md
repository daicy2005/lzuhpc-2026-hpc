# 声明式配置

`runtime/` 是实际 CLI 配置样例；`recommended/{uniform,skewed,memory}.json` 是留出决策生成的完整可运行配置，均在最终 v3 执行核验过。它们使用本机允许的 [0,1,2,3] 掩码；其他机器运行前检查可用 CPU。选择及配置散列见 results/selection.json。下文 example/experiments 内容保留为历史设计。

example.json 是设计示例，不是已被可执行程序验证的配置；CPU编号省略，unbound不假定任何物理拓扑。实现时建立严格schema并拒绝未知字段。

experiments/first-batch-design.json是首批W00/W01设计草案，供将来生成冻结计划；包含校准规则、最大矩阵与停止预算，不是runtime配置或已执行plan.json。完整语义见 [首批协议](../docs/10-首批实验协议.md)。

计划分开 policies/（可组合策略预设）、workloads/（固定问题定义）、experiments/（冻结batch矩阵/重复/顺序）。只有需要时创建真实预设，不生成大量空配置。

运行前解析所有默认值并写resolved_config；不得只记录一个可能日后变化的预设名称。正式显式绑核列表来自实际允许集合，不复制光追的CPU编号到其他机器。
