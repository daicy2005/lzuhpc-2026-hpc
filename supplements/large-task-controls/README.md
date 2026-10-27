# 单任务大于 LLC 的补测

[结果](results.md) · [逐次数据](summary.json) · [实验设计](protocol.md) · [完整记录与源码](experiment.zip)

本组每任务为 288 MiB，约为报告 LLC 的 8 倍，4 个任务共 1152 MiB。六个条件各有一次诊断、一次预热、五次正式计时，共 42 次运行。固定执行线程的预读对照与四线程动态开关对照分别保存，不把全部时间差当缓存损失。

在仓库根目录运行 `python3 tools/verify_large_task_supplement.py` 可以检查压缩包，并从逐次数据重算汇总。

复测时，先解压本组压缩包并进入 summary.json 中 source_id 对应的 snapshots/source/ 目录。准备与前一组一致的程序并运行正确性检查后，再准备和运行本组：

```bash
python3 tools/mechanism_controls.py prepare --root /root/lzuhpc-experiments/ws-20261027-mechanism-controls-v3
python3 tools/large_task_controls.py prepare --root /absolute/new-large-study
python3 /absolute/new-large-study/tools/large_task_controls.py run --root /absolute/new-large-study
python3 /absolute/new-large-study/tools/large_task_controls.py audit --root /absolute/new-large-study
```

上述第一条仅构建并检查，不运行前一组性能测试；如果该目录已存在，应复用其经过检查的二进制，不覆盖旧目录。本采集器的主机负载检查用于 WSL，原生 Linux 复测需要另行记录主机负载条件。全部 C++ 源码、固定配置和原始命令均在压缩包中。
