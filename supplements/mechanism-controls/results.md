# WorkSteal 机制补测

35 个条件各测五次，预热和诊断另存。epoch 不含初始化、建队列和完整核验。

|对照|配置|epoch 中位数（ms）|
|---|---|---|
|overhead|g8|2.8658|
|overhead|g64|2.5319|
|overhead|g4096|2.3769|
|overhead|serial|2.3888|
|preread-4.5MiB-target0|same|1.5208|
|preread-4.5MiB-target0|other|1.5308|
|preread-288MiB-target1|same|102.9606|
|preread-288MiB-target1|other|100.3162|
|preread-512KiB-target1|same|0.2079|
|preread-512KiB-target1|other|0.1987|
|balance-s176023-g8-concentrated|off|9.6864|
|balance-s176023-g8-concentrated|on|3.6464|
|dynamic-4.5MiB|on|0.4739|
|balance-s170021-g8-spread|off|3.3574|
|balance-s170021-g8-spread|on|2.1635|
|preread-288MiB-target0|same|99.9010|
|preread-288MiB-target0|other|101.7545|
|balance-s170021-g256-concentrated|off|6.5914|
|balance-s170021-g256-concentrated|on|2.5823|
|balance-s176023-g256-spread|off|4.4460|
|balance-s176023-g256-spread|on|3.5359|
|preread-512KiB-target0|same|0.1957|
|preread-512KiB-target0|other|0.1998|
|balance-s176023-g256-concentrated|off|18.5922|
|balance-s176023-g256-concentrated|on|3.6639|
|balance-s176023-g8-spread|off|4.5241|
|balance-s176023-g8-spread|on|3.1788|
|dynamic-512KiB|on|0.0897|
|preread-4.5MiB-target1|same|1.6321|
|preread-4.5MiB-target1|other|1.6350|
|dynamic-288MiB|on|28.5735|
|balance-s170021-g256-spread|off|4.4058|
|balance-s170021-g256-spread|on|2.4106|
|balance-s170021-g8-concentrated|off|12.3399|
|balance-s170021-g8-concentrated|on|2.3391|

动态窃取诊断：

- dynamic-4.5MiB-on: 47 次成功窃取，47/64 个元素由非 home 执行。
- dynamic-512KiB-on: 46 次成功窃取，46/64 个元素由非 home 执行。
- dynamic-288MiB-on: 48 次成功窃取，48/64 个元素由非 home 执行。

固定执行线程的预读差异仍不能等同于纯缓存损失；WSL1 下物理缓存映射和 PMU 未确认。

逐次结果与 run_id 见 summary.json，每个原始目录保留命令、配置、标准输出及散列。
