# 工具目录

第八轮：`memory_kernel_study.py prepare/run/audit/export/report --root <新目录>`，冻结协议docs/27。先用bootstrap在`ws-20261021-memory-kernel-release/asan/tsan`三个新目录构建并完整验证，prepare要求三份源码ID一致。唯一候选memory_lanes4，对照1，同一新Release；12control+4预热+28计时，无追加。主要采用门槛是双输入epoch，app仅作≤5%退化护栏，不沿用第七轮app目标冒充调度优化。最多两次资源等待，已启动批次不能重试。Windows导出新目录memory-kernel/并独立report。通过才另存configs/memory-interleaved，默认1及旧推荐不改。

正式路径：`bootstrap.py` 独立 Linux 构建与验收，`lab.py` 快照/有界批次/封存/验散列导出，`study.py` 机制筛选与留出确认，`analyze.py` 逐记录核验后生成统计，`closeout.py` 生成推荐配置、执行验收、审计归档，`make_report.py` 从统计生成 Markdown/图表/PDF 及逐页预览。参数用各工具 `--help` 查看。

第二轮路径：`optimize.py` 跨构建消融、线程/粒度筛选与新输入确认；`analyze_opt.py` 核对计划/配置/来源/身份/散列后生成统计和推荐；`audit_opt.py` 核验16份构建验证、当前生产源码、推荐复跑和preset参数；`report_opt.py` 生成第二轮Markdown/图表/PDF。第一轮 `closeout.py audit` 的v3源码一致性只描述当时状态，不用于当前源码。

旧 `run_matrix.py`、`summarize_matrix.py` 只用于早期开发 smoke，不再用作正式实验采集或排名。正式数据以有 completion.json 的不可变批次为准，诊断/预热/验收不进入计时样本。

第五轮：`confirm_idle.py prepare/probe/run/audit/export --root <新Linux目录>`，复用第四轮二进制，以资源门禁保护新输入确认。`run --wait-seconds 300` 最多等待5分钟；忙时退出3，不启动研究进程；资源干扰/批次失败退出4并封存。默认等待0仅做一次资源检查，正常开始需给足三次观测预算（至少30秒）。协议见 docs/20，历史数据不覆盖。

运行使用新collector内冻结的脚本。采完后用当前项目的脚本执行 `audit` 和 `export --target /mnt/d/临时对话/hpc-worksteal/confirmation`：补充导出冻结计划原字节，验散列复制到Windows；再用Windows Python执行 `tools/confirm_idle.py report --root confirmation`，对导出文件及原始结果独立重算并生成报告。审计/报告支持导出目录布局，计时协议与采集脚本的冻结快照保留，后续归档工具变更不回写计时原件。

第五轮首批发生WSL1自有ps子进程的comm短暂为python3误报，保留4预热/0计时原件。修正版观测串行化，`tests/idle_guard_checks.py`可在Windows/Linux运行回归。collector `ws-20261016-idle-confirmation-v2`已完成96进程/84计时，导出目标`confirmation-retry/`；恢复命令和实际验证见docs/21、22，不向原中止批次追加样本。

第六轮：`init_study.py prepare/run/audit/export/report --root <目录>`，协议见docs/23。先在三个独立Linux目录构建Release、ASan/UBSan、TSan，prepare要求三份验证均通过且源码ID完全相同；再使用新collector内冻结脚本运行。首次run完成旧/新四类control及init1/2/4/8筛选；若胜者非1，再次run仅执行已冻结的新输入配对确认。资源等待期间未启动批次可重试；已启动的失败/干扰批次不能追加或补样。

采完依次audit、export到新的Windows `initialization/`目录，再在Windows调用report：逐导出文件验散列，从原始配置/结果重算选中线程数、两输入配对门槛及完整输入/输出/预读身份。仅全部确认通过才另存`configs/initialized`，默认init1及旧配置、数据和二进制保留。测量使用的源码快照与后续交付文档快照分开，后者不能冒充已测构建来源。

第七轮：`allocation_study.py prepare/run/audit/export/report --root <目录>`，冻结协议docs/25。使用bootstrap在`ws-20261021-allocation-release/asan/tsan`三个新目录分别构建并验证；prepare须三份source_id一致，再复制到新collector。固定overwrite候选，不筛选；12control+4预热+28计时。run等待≤600秒，最多两次未启动批次的资源等待，已启动后不得追加。导出新Windows `allocation/`，Windows report独立审计；只有双输入确认通过才另存configs/overwrite。第六轮脚本和全部封存记录不改写。

第七轮已完成44进程/28计时，accepted=false（两输入胜对6/7、5/7）；两次资源等待均已使用，无追加预算，不得再次run或追加样本求通过。默认zeroed及configs/verified保持，最新报告见report/allocation/第七轮覆盖式分配报告-7f045ca9.md。后续只读复核或report再生成均不得改写已封存原件。
