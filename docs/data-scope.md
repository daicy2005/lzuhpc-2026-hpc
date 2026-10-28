# 实验记录说明

仓库收录了报告引用的 24 次光追计时、868 次 WorkSteal 计时，以及 12 次分阶段测试。WorkSteal 包括原有 663 次、机制补测的 175 次和单任务大于 LLC 的 30 次；随机 victim 的 84 次属于原有记录。

可以通过 `report/evidence-index-v2.json` 找到文中结果对应的运行目录，查看参数、命令、日志和输出检查。机制补测的逐次记录位于 [experiment.zip](../supplements/mechanism-controls/experiment.zip)，summary.json 中的 run_path 是压缩包内路径。未被报告引用的其他历史实验仍保存在本地。

`MATERIALS-MANIFEST.json` 列出了原项目文件和图表的路径、大小和 SHA256。运行 `python3 tools/verify_materials.py` 可检查这些文件是否完整，并核对原有的 24 次光追和 663 次 WorkSteal 计时；这个脚本不会重新跑性能实验。图表改版后更新对应图表的校验值，原始实验记录及其校验值保持不变。

机制补测另外运行了 35 次诊断、35 次预热；准备阶段中止的四次诊断保存在 preflight.zip，未计入正式计时。补测的 175 次计时及相关文件由独立的 manifest.json 和 `python3 tools/verify_mechanism_supplement.py` 检查。

单任务大于 LLC 的补测另有 6 次诊断和 6 次预热，保存在 supplements/large-task-controls/experiment.zip，使用 `python3 tools/verify_large_task_supplement.py` 检查。

PDF 中的链接指向与报告对应的代码和数据版本。
