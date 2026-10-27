# 检查目录

第八轮新增任务内四路memory递推的独立Python oracle及标量参考对照：空/4路边界、非零任务起点与尾部、8/136/8192字节、种子回绕、两种分配、重复epoch、非法memory_lanes和compute不使用该参数。正式验证计数以本轮各新构建validation.json为准，尚未宣称通过。

第七轮新增zeroed/overwrite两种存储、8/136/8192字节宽度、空存储元数据、非法分配参数及其validate-config拒绝检查；独立Python还重算memory完整输出和预读散列。Release、ASan/UBSan、TSan各实际通过1927项runtime检查和275次CLI调用，诊断stderr均为空，构建无warning；证据见allocation/snapshots/builds内对应validation.json。ASan/UBSan与TSan不检测所有未初始化读取，未运行MSan；覆盖式分配的安全性同时依赖完整写入区间及join发布契约。

`runtime_checks.cpp` 覆盖固定任务的恰好一次、结果发布、最后任务竞争、空/重复 epoch、异常恢复、关闭及并发提交拒绝。`cli_checks.py` 用独立 Python uint64 参考核验输出，并检查非法配置和测试专用 `test_reverse` 扩展。CMake 将新增注册文件只链接进 `worksteal_extension`，复用同一个核心库。

Release、ASan/UBSan 与 TSan 的真实执行记录分别归档到各构建的 validation.json。检查通过不等于无竞争的形式证明；性能实验不放在普通单元检查中，不以固定秒数作为跨机通过条件。

第六轮内存初始化：三种构建各通过1847项runtime检查和213次CLI调用。新增分块检查覆盖N=0/1、非整除尾块、请求线程数大于块数、compute不启动填充线程及非法线程数。CLI用独立Python逐word计算FNV，覆盖uint64种子回绕，并比较不同初始化线程数、连续epoch的完整身份、输出和预读散列。初始化线程创建失败未做故障注入；生命周期保证依据jthread的RAII语义。原始验证收据在第六轮导出的snapshots/builds中；性能结论以独立实验报告为准。
