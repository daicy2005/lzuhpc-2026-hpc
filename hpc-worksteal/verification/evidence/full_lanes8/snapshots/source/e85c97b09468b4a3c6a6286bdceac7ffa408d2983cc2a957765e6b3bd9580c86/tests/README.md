# 检查目录

`runtime_checks.cpp` 覆盖固定任务的恰好一次、结果发布、最后任务竞争、空/重复 epoch、异常恢复、关闭及并发提交拒绝。`cli_checks.py` 用独立 Python uint64 参考核验输出，并检查非法配置和测试专用 `test_reverse` 扩展。CMake 将新增注册文件只链接进 `worksteal_extension`，复用同一个核心库。

Release、ASan/UBSan 与 TSan 的真实执行记录分别归档到各构建的 validation.json。检查通过不等于无竞争的形式证明；性能实验不放在普通单元检查中，不以固定秒数作为跨机通过条件。
