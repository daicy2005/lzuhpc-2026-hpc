# 检查目录

第十五轮152进程完整参考核验均通过，其中24diagnostic检查exact_once、执行归属、迁移身份及实际affinity，112计时不带逐任务诊断；退避性能门槛未过。采集器grain缓存错误在首批第5control暴露，以原件重放复现并修正；失败批次0计时独立保留。同期干净Linux默认/full/uniform三份Release各实际通过2551项runtime/497项CLI，六个原推荐配置完整核验通过，72个导出文件验散列。这是功能复现，未新增sanitizer或容器检查。见[结果](../docs/44-第十五轮空闲退避结果.md)。

第十四轮无C++或生产测试修改，无新增sanitizer构建。8个小control由Python独立重算全输出及输入/成本/任务/队列FNV；筛选及确认另16个完整规模diagnostic，重建每worker实际任务/元素/成本。批量路径核对steals≤moved≤cap×steals，最终异主任务数≤moved，不把累计搬运次数误当不同任务数。120进程均完整参考核验通过、stderr空；16预热与24诊断不进入80正式计时。选择逻辑合成检查与性能样本分开，见[第十四轮结果](../docs/40-第十四轮批量窃取结果.md)。

第十三轮无生产/测试代码变更、无新sanitizer构建。12个N1031/K7小control由Python独立重算全部输出、输入/成本/任务/队列FNV；24完整规模diagnostic从task_executor独立重建工作归属、成本、迁移与steals，检查exact_once和affinity。全部180进程完整核验通过、stderr空；120计时不启用逐任务诊断。审计原先误要求compute预读等于全零FNV，现修为null；该只读工具错误与运行时核验分开，冻结采集和原件保留，见[第十三轮分析](../docs/38-第十三轮窃取边界结果.md)。

第十二轮未改runtime或测试代码，不重跑历史runtime/TSan。独立顺序探针Release、ASan/UBSan各36例自检，Python独立重算全部自检word与FNV，覆盖0/1/2/3/17/4097word及uint64种子回绕、两种分配和zeroed查零。26研究进程均通过；大数组探针每次逐word检查，完整FNV与原应用control一致；控制进程完整参考核验、exact_once、affinity通过。详见[第十二轮结果](../docs/36-第十二轮成本诊断结果.md)，不把探针验证写成新的生产runtime检查。

第十一轮新增data_fill_lanes=4的word尾部0/1/2/3、8/136/8192字节、空/单元素、种子回绕、zeroed/overwrite、重复epoch、compute不使用数据填充及非法值/不兼容组合。独立Python重算data/output/pretouch FNV，C++对照原填充与完整标量核验；Release、ASan/UBSan、TSan各通过2551项runtime检查和497次CLI，stderr空、build无warning。44研究进程正确性均通过，性能未达门槛，见[第十一轮结果](../docs/34-第十一轮数据生成契约与结果.md)。

第十轮新增分块实际存储FNV：256 KiB±8、跨块跨元素、空/单元素、奇数word、种子回绕、两种分配、重复epoch、identity在执行前后保持一致、compute及非法data_identity/不兼容填充线程。C++比较原路径，Python独立重算data/output/预读FNV；Release、ASan/UBSan、TSan各真实通过2401项runtime检查和417次CLI调用，stderr为空、构建无warning。44研究进程数值核验全部通过，但性能门槛未过，见[第十轮契约与结果](../docs/32-第十轮分块散列契约与结果.md)。

第九轮无C++修改、无新构建，沿用第八轮验证来源。12组线程/粒度各跑一次N37/128字节诊断，独立Python重算输出/data/预读散列、任务和queue身份、执行元素/工作量，并检查exact_once与实际affinity；其余48进程均完整标量参考核验。共60进程，正式计时36，不把筛选负结果写成正确性失败。见[结果与证据](../docs/30-第九轮参数筛选结果.md)。

第八轮新增任务内四路memory递推的独立Python oracle及标量参考对照：空/4路边界、非零任务起点与尾部、8/136/8192字节、种子回绕、两种分配、重复epoch、非法memory_lanes和compute不使用该参数。Release、ASan/UBSan、TSan各实际通过2308项runtime检查与367次CLI调用，诊断stderr为空、构建无warning，三份source_id一致。证据及限制见[第八轮契约](../docs/28-第八轮内存执行契约与结果.md)。

第七轮新增zeroed/overwrite两种存储、8/136/8192字节宽度、空存储元数据、非法分配参数及其validate-config拒绝检查；独立Python还重算memory完整输出和预读散列。Release、ASan/UBSan、TSan各实际通过1927项runtime检查和275次CLI调用，诊断stderr均为空，构建无warning；证据见allocation/snapshots/builds内对应validation.json。ASan/UBSan与TSan不检测所有未初始化读取，未运行MSan；覆盖式分配的安全性同时依赖完整写入区间及join发布契约。

`runtime_checks.cpp` 覆盖固定任务的恰好一次、结果发布、最后任务竞争、空/重复 epoch、异常恢复、关闭及并发提交拒绝。`cli_checks.py` 用独立 Python uint64 参考核验输出，并检查非法配置和测试专用 `test_reverse` 扩展。CMake 将新增注册文件只链接进 `worksteal_extension`，复用同一个核心库。

Release、ASan/UBSan 与 TSan 的真实执行记录分别归档到各构建的 validation.json。检查通过不等于无竞争的形式证明；性能实验不放在普通单元检查中，不以固定秒数作为跨机通过条件。

第六轮内存初始化：三种构建各通过1847项runtime检查和213次CLI调用。新增分块检查覆盖N=0/1、非整除尾块、请求线程数大于块数、compute不启动填充线程及非法线程数。CLI用独立Python逐word计算FNV，覆盖uint64种子回绕，并比较不同初始化线程数、连续epoch的完整身份、输出和预读散列。初始化线程创建失败未做故障注入；生命周期保证依据jthread的RAII语义。原始验证收据在第六轮导出的snapshots/builds中；性能结论以独立实验报告为准。
