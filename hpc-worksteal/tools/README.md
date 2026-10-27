# 工具目录

2026-10-27资源恢复：`recover_victim_selection.py`复用原采集器，`prepare/run/audit/export/report --root <新目录>`，协议docs/49。原study/build相等、旧两次0进程等待原件校验后，只允许一个600秒资源窗口；已完成114进程/84计时，禁止再run。`close_victim_recovery.py`核对新旧原件、双端审计和交付链接；`victim_report_update.py --font <中文TTF>`生成本轮图表、复算输入与三页补充后合并旧PDF，必须目视验页。`audit_local_delivery.py`在实际打包解包后核对当前本机交付，区分本机完成与容器暂缓。原close_victim_selection.py仍只对应旧目录，不运行它回写旧准备。

对话格式兼容：旧`export_prompt_session.py`保持原字节；新`export_prompt_session_v2.py`沿用其输出流程，只额外接受未在response_item出现、但由原始item_completed记录保全的可见异步询问。原Text逐字映射output_text，保留来源行号、item id和原block；其他未匹配消息仍报错。已验证旧365条前缀与旧提取完全相等，本轮增加一条真实界面问题，不以工具内部日志或摘要补写。原始导出失败发生在创建目录之前，无不完整交付目录。

最终复核：`check_official_reference.py --out <新目录>`通过公共GitHub API固定HEAD并核对三份文档，已确认仍为33dad592、内容未变。`package_submission.py`新候选排除所有旧submission/unpacked-*副本，旧包/副本不删。`audit_delivery_state.py --package-receipt <收据> --out <新审计文件>`只读核对代码与原生Linux证据、报告原始run、PDF/Session、来源和实际解包副本，明确goal_complete=false及环境待办；不会运行新构建、测试或计时。范围见docs/48。

第十六轮：`victim_selection_study.py selfcheck/prepare/run/audit/export/report`，协议docs/45。原第四轮p32/g256/K1024推荐二进制只改victim，固定114进程/84计时；独立`shuffle_oracle.cpp`的50组对照通过。两段资源等待均deferred_busy，实际0研究进程/0计时，预算已耗尽，不第三次run或放宽门槛。256文件导出victim-selection/，用`archive_victim_preparation.py`检查未采样准备归档；完整批次audit/report尚不适用，`close_victim_selection.py`只适用于真正完成采样后的交付。`validate_victim_collector.py`已只读回放一份真实p32记录并拒绝六种损坏；不重复覆盖原收据。当前状态docs/46，随机序列源码观察docs/47。

第十五轮：`idle_backoff_study.py selfcheck/prepare/run/audit/export/report`，协议docs/41、恢复docs/43、结果docs/44。immediate/backoff两输入×两grain×两布局，固定152进程/112计时，accepted=false。首批5control/0计时因grain缓存键遗漏封存，恢复从头执行；分别归档idle-backoff-collector-failure和idle-backoff，禁止混合或补样。`close_idle_backoff.py --report <报告>`核对双平台审计、旧原件、AST报告链接修正及交付来源。只读复核：`python tools/idle_backoff_study.py report --root idle-backoff`。

交付工具：`verify_submission.py --destination <新Linux目录> --export-target <新目录>`实际构建默认/full/uniform并执行CTest与六个原推荐配置；已完成目录不覆盖。`export_prompt_session.py`连续导出真实Session可见文本，核对UI消息事件覆盖、排除思维链。`final_report.py --font <中文TTF>`从原始run复核后生成综合报告/图表/PDF，另做目视检查。`package_submission.py`创建并实际解包复核代码、证据与报告，排除缓存和包自身；容器实建状态独立记录。

第十四轮：`batch_migration_study.py prepare/run/audit/export/report --root <新目录>`，协议docs/39。复用原第十一轮二进制，single对照cap4/16/64，48进程筛选后仅唯一cap4进入72进程新输入确认。实际120进程/80计时、accepted=false；不得补样或换第二名确认。批量诊断区分累计moved与最终异主任务数，复用第十三轮独立任务模型。只读复核：`python tools/batch_migration_study.py report --root batch-migration`，先验1119个导出文件；`close_batch_migration.py`验证历史原件、源码、链接和交付收据。结果见docs/40，无新推荐配置。

第十三轮：`stealing_boundary_study.py prepare/run/audit/export/report --root <新目录>`，冻结协议docs/37。复用第十一轮二进制，180进程/120计时已完成，禁止补样或重复run。原冻结审计错误地将compute的预读null当全零FNV，当前仅audit函数修正，原采集脚本和快照保留；变化与来源见docs/38。只读复核：`python tools/stealing_boundary_study.py report --root stealing-boundary`，先验1534个导出文件再重算；`close_stealing_boundary.py`负责AST变更范围、历史原件、链接和交付快照核对，无新策略或推荐。

第十二轮：`init_cost_study.py prepare/run/audit/export/report --root <新目录>`配合`init_cost_probe.cpp`做独立单线程成本诊断。协议docs/35、结果docs/36；2原应用控制+4预热+20profiling，另两构建各36例自检。已完成，不能重跑补样；没有候选采用结论。Windows只读复核：`python tools/init_cost_study.py report --root init-cost`，先验证466个导出文件，再重算审计与新报告。首次准备警告另存init-cost-preparation-warning，不改旧工具或生产构建。

第十一轮：`fill_interleaved_study.py prepare/run/audit/export/report --root <新目录>`，冻结协议docs/33。三份新构建检查后prepare，同时封存旧/新Release完整objdump。固定fill1/4、12诊断control+4预热+28计时，app主要门槛、epoch护栏；已完整完成44进程且未通过，不得再次run求通过。Windows逐项核对602个导出文件并独立重算；只读复核：`python tools/fill_interleaved_study.py report --root fill-interleaved`。没有新推荐，原配置/构建身份保留；结果分析见docs/34。

第十轮：`blocked_identity_study.py prepare/run/audit/export/report --root <新目录>`，冻结协议docs/31。三份新构建完整验证后prepare，唯一候选data_identity=blocked，对照separate；12诊断control+4预热+28计时，整批44进程，app为主门槛、epoch为退化护栏。已完成且未通过采用门槛，全部慢成功样本保留，默认separate和第八轮推荐不变，不得再次run追加样本。Windows核对587个导出文件，独立重算4/7、2/7 app胜对；只读复核：`python tools/blocked_identity_study.py report --root blocked-identity`。不要把identity_hashes阶段消失当成收益，实际散列移入初始化；需看逐run两阶段之和及app。

第九轮：`memory_tuning_study.py prepare/run/audit/export/report --root <新目录>`，协议docs/29。直接复用第八轮Release与validation，不重编译。一次run先执行12诊断、12预热和36计时，若筛选有唯一合格候选才执行冻结的32进程确认分支；最多92进程，不追加。实际已完成60进程，没有合格候选，Linux/Windows审计accepted=false，667个导出文件验散列通过；保留第八轮推荐，不得再次run求通过。结果见docs/30，Windows只读复核：`python tools/memory_tuning_study.py report --root memory-tuning`。报告中的confirmable表示完整且资源观察通过，并不表示候选通过筛选或采用门槛。

第八轮：`memory_kernel_study.py prepare/run/audit/export/report --root <新目录>`，冻结协议docs/27。先用bootstrap在`ws-20261021-memory-kernel-release/asan/tsan`三个新目录构建并完整验证，prepare要求三份源码ID一致。唯一候选memory_lanes4，对照1，同一新Release；12control+4预热+28计时，无追加。主要采用门槛是双输入epoch，app仅作≤5%退化护栏，不沿用第七轮app目标冒充调度优化。最多两次资源等待，已启动批次不能重试。Windows导出新目录memory-kernel/并独立report。通过才另存configs/memory-interleaved，默认1及旧推荐不改。

第八轮已完成44进程/28计时，Linux/Windows独立审计accepted=true；两输入epoch均7/7胜出且中位数下降超过10%，app护栏通过。仅使用第一段资源等待（18次观测、300.4514824秒），批内101次观测全clear。574个导出文件验散列通过；已另存configs/memory-interleaved，对应原始candidate配置及新Release来源，不追加验收或计时。最新入口为report/memory-kernel/第八轮内存执行交错报告-424ce55a.md；后续report只读原件并生成新审计/报告，不再run。

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
