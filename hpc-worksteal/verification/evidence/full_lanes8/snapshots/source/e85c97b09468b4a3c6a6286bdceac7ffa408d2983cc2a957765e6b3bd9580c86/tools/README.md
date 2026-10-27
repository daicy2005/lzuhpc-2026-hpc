# 工具目录

正式路径：`bootstrap.py` 独立 Linux 构建与验收，`lab.py` 快照/有界批次/封存/验散列导出，`study.py` 机制筛选与留出确认，`analyze.py` 逐记录核验后生成统计，`closeout.py` 生成推荐配置、执行验收、审计归档，`make_report.py` 从统计生成 Markdown/图表/PDF 及逐页预览。参数用各工具 `--help` 查看。

第二轮路径：`optimize.py` 跨构建消融、线程/粒度筛选与新输入确认；`analyze_opt.py` 核对计划/配置/来源/身份/散列后生成统计和推荐；`audit_opt.py` 核验16份构建验证、当前生产源码、推荐复跑和preset参数；`report_opt.py` 生成第二轮Markdown/图表/PDF。第一轮 `closeout.py audit` 的v3源码一致性只描述当时状态，不用于当前源码。

旧 `run_matrix.py`、`summarize_matrix.py` 只用于早期开发 smoke，不再用作正式实验采集或排名。正式数据以有 completion.json 的不可变批次为准，诊断/预热/验收不进入计时样本。
