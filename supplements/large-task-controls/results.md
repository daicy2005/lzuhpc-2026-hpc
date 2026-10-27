# 单任务大于 LLC 的补测

每任务 288 MiB（报告 LLC 的 8 倍），4 个任务共 1152 MiB，每条件五次计时。

|对照|配置|epoch 中位数 / ms|
|---|---|---|
|preread-target0|same|446.4460|
|preread-target0|other|450.6728|
|preread-target1|same|452.3544|
|preread-target1|other|446.7660|
|dynamic|off|458.6950|
|dynamic|on|127.4055|

动态诊断成功窃取 3 次，3/4 个任务由非 home 执行。

预读对照不能直接等同于纯缓存损失；工作窃取开关的时间差包含并行度和调度等共同影响。
