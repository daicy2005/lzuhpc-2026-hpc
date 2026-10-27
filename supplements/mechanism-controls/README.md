# WorkSteal 机制补测

[实验结果](results.md) · [逐次数据和诊断](summary.json) · [实验设计](protocol.md) · [完整记录与源码](experiment.zip)

这组实验单独保存，不替换早先的计时数据。完整记录压缩包含配置、命令、原始输出、预热、诊断、正式计时、源码快照及构建日志；summary.json 中的 run_path 是压缩包内路径。

[准备阶段记录](preflight.zip)保留了采集器校验错误导致中止的四次诊断及负载检测记录。这四次没有进入正式计时。

图表可由 `python3 figure.py summary.json balance.svg` 重新生成。

在仓库根目录运行 `python3 tools/verify_mechanism_supplement.py` 可检查压缩包、逐次数据和汇总。该检查不会运行性能实验。

解压 experiment.zip 后，从 results/summary.json 的 source_id 找到 snapshots/source/ 下对应的源码目录，在 Linux 环境执行：

```bash
python3 tools/mechanism_controls.py prepare --root /absolute/new-study
python3 /absolute/new-study/tools/mechanism_controls.py run --root /absolute/new-study
python3 /absolute/new-study/tools/mechanism_controls.py audit --root /absolute/new-study
```

复测会使用新的独立目录，不覆盖已有结果。当前采集器的空闲检测包含 Windows 主机负载检查，适用于本次 WSL 环境；换到原生 Linux 时需另行制定主机负载检查，不能直接删掉检查后声称复现了相同环境。

disabled_yield 只加入实验程序，原有 worksteal 的运行时和默认策略没有改动。固定线程的预读对照与动态窃取分别测试，不能据此把全部时间差归为缓存损失。
