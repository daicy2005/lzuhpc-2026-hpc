"""Create a separate student-voice report; read but never rewrite frozen evidence."""
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import statistics
import sys

from PIL import Image, ImageDraw
import pdfplumber
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.graphics.shapes import Drawing, Rect, Line, Polygon, String
from reportlab.graphics import renderSVG
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image as PDFImage, PageBreak, Preformatted

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.cache/svg-render'))
from svglib.svglib import svg2rlg
from svglib.fonts import register_font as register_svg_font
from student_diagrams import runtime_diagram as designed_runtime, roadmap_diagram
OUT = ROOT / 'output/pdf'
REPORT = ROOT / 'report/student'
TMP = ROOT / 'tmp/pdfs/student-20261026-v9'
for folder in (OUT, REPORT, TMP):
    folder.mkdir(parents=True, exist_ok=True)
PDF = OUT / 'Mini-WorkSteal-学生实验报告-20261025.pdf'
MD = REPORT / 'Mini-WorkSteal-学生实验报告.md'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

inputs = read(ROOT / 'report/final/input-data.json')
verified = {}
for relative, expected in inputs['verified_raw_runs'].items():
    run = ROOT / relative
    hashes = read(run / 'checksums.json')
    assert set(hashes) == {p.name for p in run.iterdir() if p.is_file() and p.name != 'checksums.json'}
    for name, sha in hashes.items():
        assert digest(run / name) == sha, (relative, name)
    result, metadata = read(run / 'result.json'), read(run / 'metadata.json')
    assert digest(run / 'result.json') == expected['result_sha256']
    assert metadata['status'] == 'completed' and metadata['included'] and metadata['purpose'] == 'timing'
    assert metadata['binary_sha256'] == expected['binary_sha256']
    assert result['correctness']['pass']
    assert result == json.loads((run / 'stdout.log').read_bytes())
    assert not (run / 'stderr.log').read_bytes()
    assert result['timing']['epoch_seconds'] == expected['epoch']
    assert result['timing']['end_to_end_seconds'] == expected['app']
    assert all(e['correctness']['pass'] and e['correctness']['mismatches'] == 0
               and e['correctness']['compared_elements'] == result['resolved_config']['workload']['elements']
               for e in result['epochs'])
    verified[relative] = expected
assert len(verified) == 579
source_locations = {}
for relative, sha in inputs['source_sha256'].items():
    current = ROOT / relative
    actual = current if digest(current) == sha else ROOT / 'snapshots/source' / inputs['narrative_source_snapshot'] / relative
    assert digest(actual) == sha
    source_locations[relative] = actual.relative_to(ROOT).as_posix()

supplementary_paths = [
    'include/worksteal/policy.hpp', 'src/runtime/worker_pool.cpp',
    'src/workloads/workload.cpp', 'src/app/main.cpp',
    'tests/register_reverse.cpp', 'configs/runtime/diagnostic.json',
    'docs/44-第十五轮空闲退避结果.md', 'docs/46-第十六轮Victim选择结果.md',
    'docs/47-随机Victim序列相关性源码观察.md',
    'reference/upstream-20261025-api/verification.json',
    'submission/prompts/session-20261025-v16-resource-close/manifest.json',
    'submission/prompts/attachment-availability-20261025.json',
    'refinement/profiling/results/phase-summary.json',
    'report/student/工作说明与探究过程.md',
    'report/student/项目复盘.md',
    'report/student/图解.md',
    'tools/student_diagrams.py', 'tools/student_figures.py',
    'report/student/figures/design-provenance.json',
    'report/student/figures/chart-data.json',
    'report/student/figures/prompts/runtime-flow-20261026.txt',
    'report/student/figures/prompts/exploration-roadmap-20261026.txt',
]
supplementary_sources = {relative: digest(ROOT / relative) for relative in supplementary_paths}
session_dir = ROOT / 'submission/prompts/session-20261025-v16-resource-close'
session = read(session_dir / 'manifest.json')
assert session['visible_messages'] == 365 and session['roles'] == {'user': 47, 'assistant': 318}
assert session['no_reasoning_exported']
for filename, expected in session['files'].items():
    assert digest(session_dir / filename) == expected

# Recheck the historical phase observations separately; they are not timing samples.
phase_summary = read(ROOT / 'refinement/profiling/results/phase-summary.json')
assert phase_summary['pass'] and phase_summary['profiling_samples'] == 12
phase_evidence = {}
for kind, group in phase_summary['groups'].items():
    fractions, paths = [], []
    for sample in group['samples']:
        run = ROOT / 'refinement/profiling' / sample['path']
        checksums = read(run / 'checksums.json')
        assert set(checksums) == {p.name for p in run.iterdir() if p.is_file() and p.name != 'checksums.json'}
        for filename, expected in checksums.items():
            assert digest(run / filename) == expected
        result, metadata = read(run / 'result.json'), read(run / 'metadata.json')
        assert metadata['status'] == 'completed' and metadata['purpose'] == 'profiling' and not metadata['included']
        assert result == json.loads((run / 'stdout.log').read_bytes()) and not (run / 'stderr.log').read_bytes()
        assert result['correctness']['pass']
        assert result['timing']['end_to_end_seconds'] == sample['end_to_end_seconds']
        assert result['phase_seconds'] == sample['phase_seconds']
        fractions.append(sample['phase_seconds']['full_reference_verification'] / sample['end_to_end_seconds'])
        paths.append({'run_path': run.relative_to(ROOT).as_posix(), 'result_sha256': digest(run / 'result.json'),
                      'binary_sha256': metadata['binary_sha256']})
    assert len(paths) == 3 and statistics.median(fractions) == group['verification_fraction_median']
    phase_evidence[kind] = {'run_count': len(paths), 'purpose': 'profiling', 'included_in_timing': False,
                            'verification_fraction_median': statistics.median(fractions), 'runs': paths}
assert f"{phase_evidence['uniform']['verification_fraction_median']*100:.1f}" == '96.5'
assert f"{phase_evidence['skewed']['verification_fraction_median']*100:.1f}" == '97.1'

source = (ROOT / 'report/final/技术报告.md').read_text(encoding='utf-8')
blocks = source.strip().split('\n\n')
changes = {
    '研究问题：': '我想回答的问题是：固定总工作量时，任务粒度和初始不均衡怎样决定工作窃取是否值得？为此，我在 AI 辅助下实现了一个 C++20 的小型运行时，采用持久线程池和带锁双端队列，并把策略独立注册。任务集合在执行前冻结，不支持递归产生子任务或 DAG。本项目在 Ubuntu 24.04 / WSL1 上评测，Windows 用于编辑、归档和报告排版。',
    '结论：': '我的主要观察是：窃取能缓解集中偏斜，但不能拆开过大的任务。第十三轮使用同一优化二进制和 16 个 worker，grain 为 8/256 时，集中布局两个输入的 epoch 耗时比约为 2.62-3.06；粗粒度下只有 4/6 个任务，没有稳定收益。即使分散布局中每个 worker 的工作单位相等，也不保证它们同时完成。',
    '优化需要按阶段解释。': '我把优化结果按作用阶段分别解释：独立计算链、完成发布批处理、窃取暂存与线程/粒度联合优化影响任务执行；完整参考核验并行化影响应用总耗时；四路 memory 交错影响任务内核。它们不是同一种窃取收益，跨轮倍数不能相乘。',
    '批量窃取在第十四轮': '在第十四轮中，批量窃取虽然减少了操作次数、改善了成本单位的分配，仍未通过新输入确认；第十五轮退避也没有通过采用门槛。我保留了这些负结果，没有用筛选最优或单个最快运行代替最终结论。',
    '本报告不宣称': '本文只说明已测候选和输入范围内的结果。我没有证明跨平台最优，也没有可靠证据把变化归因于物理核心、NUMA 或缓存 miss；检查通过也不是无数据竞争的形式证明。',
    '执行器包括': '为了看出调度本身的差别，我保留了直接串行、静态本地队列和集中队列对照。S3-off/on 则共用工作窃取执行器，队列、锁、任务顺序和完成协议相同，只切换窃取开关。还要注意一个差别：off 空闲时等待，on 空闲时 yield。因此，这组差值包含空闲处理方式的影响，不能全部算作搬运任务的费用。',
    'owner从队尾取': '本地线程（owner）从队尾取，窃取线程（thief）从队头取。迁移时先 try_lock 读取 victim 队列长度，解锁后调用策略，再次 try_lock，按此时剩余数量裁剪。这样策略回调不会占着队列锁，也不用同时持有两把队列锁。启用暂存优化后，偷到的第一个任务直接执行，多出的描述符进入本地队列。',
    '正式实验先冻结': '我把比较规则写在采样前：固定输入、候选、构建、执行顺序、样本数和停止条件，诊断、预热、正式计时各用不同 run_id。所有成功样本都参与中位数计算，慢的一次也保留。筛选选出候选后，再到预定的新输入确认；没通过就停止，不改选第二名。各轮采用标准是工程上的取舍规则，并不等于通过了统计显著性检验。',
    '硬件来源：': '本机是 i9-13900HX，CPUID leaf4 和 Windows 报告的 LLC 容量均约为 36 MiB。WSL1 下能核对请求的单 CPU 逻辑掩码，但无法稳定确认线程实际落在哪个物理核、是否共享缓存；也没有可用的 PMU 数据。这些条件限制了后面对缓存原因的解释。',
    '六个动态开启': '这一部分最关键的不足是：六个开启窃取的动态诊断都没有成功偷取。执行者与 home 不一致，也可能来自初始放置。我测到了远小于和远大于 LLC 的两个尺度，却还没测到动态偷取引起的缓存损失。题目允许局部性窗口接近零，但现有结果只能说证据不足，不能据此认定局部性没有代价。',
    '没有通吃所有负载': '我没有找到通吃所有负载的组合。对于已经均衡的工作或一次性很小的调用，应先比较串行、静态队列、集中队列和完整应用时间。这里的推荐只是预定候选范围内经过新输入确认的选择，不是所有执行器、所有机器的全局最优证明。',
    '本次干净Linux复现': '已有一次干净 Linux 功能复现：147 份源文件复制到新目录；默认、full、uniform 三种 Release 构建均完成真实 CTest，六个原推荐配置完整核验通过。命令、日志和新 binary 散列见 submission/reproduction/20261025/receipt.json。这是功能复现，不是旧耗时再现；本次整理报告没有重新构建、运行性能实验或新增 sanitizer 检查。',
    'DevContainer配置': '我提供了 DevContainer 配置，但本机没有可调用的容器引擎，尚未实际构建容器。原生 Linux 检查不能代替容器检查。官方是推荐使用 DevContainer，不应把我的项目验收计划扩大成官方硬性要求。',
    '连续Prompt File位于': '连续 Prompt File 保存在 submission/prompts/session-20261025-v16-resource-close，范围是同一真实 Session 从起点到 2026-10-25T02:28:05.332Z：47 条用户消息、318 条可见助手消息，含 JSON、Markdown 和来源前缀散列。这份快照只收录该时刻之前的可见对话，不含思维链，也没有拼接其他 Session。',
    '附件限制：': '两张早期临时截图的原路径已失效，持久日志只留下文本块。因此，对话文字可以核查，图片附件还不完整；缺失部分没有补写 OCR 或重造图片。记录见 submission/prompts/attachment-availability-20261025.json。',
    '官方要求提交PDF': '我在资料检索、代码实现、测试脚本、实验分析和报告整理中使用了 AI 辅助。性能数字以原始运行记录为依据，不能把 AI 解释当成测量证据。面试前，我还需要逐项检查自己能否解释关键代码和取舍；本报告不代替个人掌握情况的确认。材料尚未对外提交，提交前还需补齐个人信息并核对群内要求。',
    '每轮目录保存': '为方便复查，我保留了每轮的冻结计划、原始配置与结果、日志、环境、校验和、源码及二进制来源。原综合报告生成时核对了 579 份正式 run；这次学生稿再次只读核对这 579 份记录及 59 份当前或冻结输入，不改写样本。579 是该报告用到的正式记录数，不是十五轮全部研究进程的总数。',
    '原始数据在Linux': '原始数据在 Linux 与 Windows 镜像中分别验散列，但位于同一物理盘，不是独立故障备份。本次只新增学生正文稿和核查清单，没有修改既有候选 ZIP；旧包不会自动包含这份新稿。',
    '社区依据：': '方法来源包括 oneTBB 的 How Task Scheduler Works、Controlling Chunking、Bandwidth and Cache Affinity，Google Benchmark 的 User Guide 和 Random Interleaving，以及 Blumofe 的 Cilk 调度说明。精确链接在 docs/11。我借鉴的是已有队列规则和实验方法，不声称发明工作窃取，也不把 Cilk 递归依赖模型的理论保证套到本项目的固定任务、带锁队列上。',
}

updated = []
seen = set()
for block in blocks:
    if block.startswith('# Mini WorkSteal'):
        block = '# Mini WorkSteal：可组合工作窃取运行时的实现与实验分析'
    else:
        for prefix, replacement in changes.items():
            if block.startswith(prefix):
                block = replacement
                seen.add(prefix)
                break
    if block.startswith('|交付对象|'):
        block = block.replace('|交付对象|当前证据|', '|报告内容|已保存的材料|').replace('336条可见消息', '365条可见消息')
    if block.startswith('官方题面：'):
        block += ' 2026 年 10 月 25 日保存的 GitHub API 核查记录确认三份题目文档未变，见 reference/upstream-20261025-api/verification.json。'
    updated.append(block)
    if block.startswith('# 1. 架构'):
        updated.append('这里的 worker 是线程池中的工作线程；grain 是每个任务包含的元素数；victim 是被尝试窃取的线程。我的重点不是做一个通用任务系统，而是在固定工作量下比较策略，所以没有提前引入无锁队列、future 或分布式执行。')
    if block.startswith('# 2. 工作量'):
        updated.append('epoch 表示一次线程池执行阶段，app 表示应用内部总耗时，包含初始化和完整核验。报告同时列出两种时间，以区分执行阶段与完整应用的变化。')
    if block.startswith('采用结论：'):
        updated.append('第十六轮准备比较 round_robin 和 seeded_random，但两段等待后资源条件仍未满足，实际为 0 研究进程、0 计时。阅读源码时发现随机 victim 的同序号序列存在相关性，目前只把它记为待测问题：是否造成争抢、是否影响速度，还需要实验回答。记录见 docs/46、47。')
assert seen == set(changes), set(changes) - seen
text = '\n\n'.join(updated) + '\n'
assert '336条' not in text and '作为AI' not in text

# Editorial revision is separate from the frozen narrative and experiment files.
polish = {
    'LZUHPC 2026': 'LZUHPC 2026 秋季 HPC 创意题实验报告 | 实验记录截至 2026-10-25，文字修订于 2026-10-26',
    '我想回答的问题是：': '本项目研究固定总工作量下，任务粒度和初始不均衡对工作窃取收益的影响。我采用 C++20 持久线程池和带锁双端队列，将六类策略独立注册，再用固定任务集开展对照实验。实验在 i9-13900HX、Ubuntu 24.04 / WSL1 上进行，Windows 用于编辑和整理材料。',
    '我的主要观察是：': '第十三轮固定优化后二进制和 16 个工作线程，在集中布局 grain=8/256 的两个新输入中，epoch 的 off/on 时间比为 2.62-3.06；粗粒度只剩 4/6 个任务时，没有稳定收益。窃取能够重新分配尚未开始的任务，但当前框架无法拆分单个任务。',
    '我把优化结果按作用阶段分别解释：': '实现优化按另一条路线推进：第二、三轮先改执行内核和配置，第四、五轮根据核验占比转向并行核验，第八轮再确认内存执行交错。它们改善了不同阶段，报告按各轮实际对照分别列结果，跨轮倍数不相乘。',
    '在第十四轮中，': '调度策略最终保留 round_robin、immediate 和 single。批量窃取与空闲退避均未通过新输入的采用标准。局部性实验的证据仍不充分：工作集覆盖了 LLC 两端，但动态诊断未发生成功窃取，尚无法量化窃取引起的缓存损失。',
    '本文只说明': '报告依次说明实现选择、实验过程、对照结果和保留配置。结论限于本机、已测输入及候选范围；跨平台表现和 WSL1 下的线程物理驻留仍需验证。',
    '这里的 worker': 'worker 是工作线程，grain 是每个任务包含的元素数，victim 是被尝试窃取的线程。任务集合在执行前固定，不支持递归产生子任务、DAG 或 future；这个范围便于在工作量相同的前提下比较调度策略。',
    '为了看出调度': '实验保留直接串行、静态本地队列和集中队列对照。S3-off/on 共用工作窃取执行器，队列、锁、任务顺序和完成协议相同。除窃取开关外，空闲处理也有差异：off 等待，on yield。因此，这组耗时差同时包含空闲处理方式的影响。',
    '本地线程（owner）': '本地线程（owner）从队尾取任务，窃取线程（thief）从队头取任务。迁移时先 try_lock 读取 victim 队列长度，解锁后调用策略，再次 try_lock，并按当前剩余数量裁剪。策略回调在锁外执行，迁移过程避免同时持有两把队列锁。启用暂存优化后，窃取的第一个任务直接执行，其余描述符进入本地队列。',
    '我把比较规则': '采样前固定输入、候选、构建、执行顺序、样本数和停止条件，诊断、预热、正式计时分别使用独立 run_id。全部成功样本参与中位数计算，包括较慢的运行。筛选所得候选在预定新输入上确认，未通过则停止，不改选第二名。采用标准属于工程选择规则，未进行统计显著性检验。',
    '这一部分最关键': '六个开启窃取的动态诊断均未发生成功窃取。执行者与 home 不一致也可能来自初始放置，因此无法将差异归因于动态迁移。现有工作集覆盖远小于、远大于 LLC 的两个尺度，但尚未测得动态窃取引起的缓存损失。题面允许局部性窗口接近零，现有结果仍不足以判断其代价。',
    '扩展验收：': '扩展检查在 tests/register_reverse.cpp 中新增注册 test_reverse，使 worksteal_extension 复用同一 ws_core。变更仅涉及新实现、注册单元和构建源清单。接口与执行入口见 include/worksteal/policy.hpp、src/runtime/worker_pool.cpp；非法配置在启动前拒绝。该方式属于静态注册扩展，第三方代码需遵守同一契约，未提供插件隔离。',
    'prepare冻结队列': '完成协议由队列准备、任务发布和阶段退出组成。prepare 准备队列，run 持状态锁记录 t0，再推进 generation 释放 worker。各任务写入独立结果槽位，remaining 通过 seq_cst 原子读改写链发布完成。batch32 暂存完成数，线程在无任务可取、准备等待前必须先发布，避免剩余计数无法归零。最后完成者通知控制线程，run 还需等待全部 worker 退出本次执行阶段。',
    'grain减小': '这组粒度条件的耗时差异较小，不足以支持普遍最优的选择。细粒度增加描述符、队列访问和完成通知，也可能引入假共享；粗粒度减少可分配任务数。图中呈现这些因素共同作用的耗时，现有计时无法分别量化队列锁等开销。',
    '第一轮W01': '第一轮 W01 固定 N=262144、K=1024，比较 1 与 4 个逻辑 worker，grain=1/64/4096。下图和表格展示 p=4，每条件 3 次正式计时的中位数；单线程结果保存在原始汇总中。',
    '机制：batch32': 'batch32 按批发布完成计数，scratch 复用窃取暂存，LTO 允许跨翻译单元优化；compute_lanes8 交错推进八个独立元素，以增加指令级并行的机会。各元素的迭代和核验保持不变，lanes 数量也不直接代表 SIMD 宽度。第三轮补充确认后，仅轻任务更换联合配置，重计算保留第二轮选择。',
    '上述历史确认推荐': 'ref 是完整参考核验的线程数，和执行任务的 worker 分开；compute_lanes8 / memory_lanes4 是任务内部交错的独立递推链数。这些配置都用 round_robin、immediate、single 和显式逻辑 CPU 掩码，输入规模看完整 JSON。第八轮第二输入在 memory-large.json；第十四、十五轮测的是 p16，不能据此重新选择表中的 p32 配置。',
    '当前源码新增过': '复现时需要区分功能和历史耗时。下一章的命令用于检查当前代码；要追溯表里的时间，还需对应的冻结源码、编译选项、环境和原二进制。下表给出定位用的短散列，完整 SHA256、选项和快照路径在 builds.json 与 evidence-index.json 中。',
    '我没有找到通吃': '配置选择随负载和调用方式变化。细粒度集中偏斜可以从任务重新分配中获益；均衡负载或一次性小任务仍需与串行、静态、集中队列比较应用总时间。输入规模、线程数或机器改变后，需要重新检查这些对照。',
    '我提供了 DevContainer': 'DevContainer 配置已写好，但本机没有可调用的容器引擎，尚未实际构建。现在完成的是原生 Linux 功能复现。题面推荐 DevContainer，也允许提供其他可复现环境说明。',
    '我在资料检索': 'AI 辅助包括资料搜集、备选方案梳理、部分代码编写和数据整理，具体过程见随附连续对话记录。',
    '为方便复查': '每轮的计划、配置、日志、环境、校验和及源码与二进制来源都保留在对应目录。这次整理重新核对了报告选用的 579 份正式 run、59 份当前或冻结输入，并另查 12 份历史阶段观测。观测不并入正式计时，579 也不是全部研究进程数。evidence-index.json 可以按章节找到计时组和原件散列。',
    '原始数据在 Linux': '版本与保存情况：这份报告由 tools/student_report.py 生成，可编辑正文、SVG 与索引位于 report/student/。10月26日只整理文字和图表，没有新增性能样本或重跑 sanitizer。Linux 与 Windows 镜像都验过散列，但仍在同一物理盘上，独立故障备份还没补齐。旧候选 ZIP 尚未更新，提交前需要加入本稿，补齐个人信息并核对群内要求。材料尚未对外提交。',
    '异常记录首个exception': '任务抛出异常时，线程池记下第一个 exception，停止开始新任务，等已开始的工作退出后再向调用者抛出。检查覆盖重复 epoch、异常恢复、关闭和拒绝并发提交。固定任务不允许等待池内其他任务，也不能在池内阻塞提交；析构会通知停止并 join，同步由锁和原子保证。',
    'compute_uniform按seed': 'compute_uniform 用 seed 和元素编号生成输入，每个元素做 K 次 uint64 混合递推。compute_skewed 把前 N/8 个元素改为 9K 次，其余仍为 K 次。grain 只改分组，layout 只重排同一组任务；相同输入的迭代次数和最终输出必须一致，mix、元素和完整核验都保留。',
    'memory_reuse按固定': 'memory_reuse 在固定的元素数据块上做带串行依赖的混合访问。指定 home 的线程先预读，预读单独计时；home 只是数据归属标记，不能保证数据实际留在缓存中。这个负载也尚未证明达到 DRAM 带宽饱和，不能直接当作 STREAM 类测试解释。',
    '小规模由独立Python': '正确性分两层核对：小规模用独立 Python uint64 参考重算输出和 FNV，应用每次完整标量重算所有元素。并行核验采用独立参考计算、固定归并，输出散列按原顺序生成。诊断另查 exact_once，并用 task_executor 重建任务、元素和成本分布；最终执行者记录不足以重建任务的全部迁移过程。',
    '资源门禁检查Windows': '每批运行前检查 Windows 负载和 WSL 中已知的冲突任务；条件不符时暂缓运行并保存记录。共享机器上的系统调度和频率变化仍可能影响计时，短 epoch 尤其敏感。运行前的负载检查只覆盖规定的观测窗口，不能证明物理独占。',
    'CS149联系：': '按 CS149 中的任务划分模型，在理想同速处理器上，完成时间的下界为 max(W/p,Cmax)，W 是总工作量，p 是处理器数，Cmax 是最大不可拆任务的工作量。粗粒度增大单个任务的影响，细粒度增加调度开销。本项目的 mix 为成本单位，不能直接换算为本机秒数，该模型用于定性分析。',
    '早期p4标量策略': '第一轮 p4 标量版本中，随机 victim、退避和 half 均未通过两个新输入的采用标准。后续内核、线程数和运行时已有变化，旧结果仅作为当时的选择依据；新版本仍需独立对照。',
    '第一轮集中布局中off/on': '第一轮集中布局的 off/on 约为 2.428，分散和打乱布局接近 1。独立诊断观察到任务迁移及 worker 成本分布变化，但诊断未并入正式计时，无法从总时间中单独量化负载均衡的贡献。该轮构建、参数与后续实验不同，结果分别保留。',
    '第十三轮在同一优化二进制': '第十三轮固定优化后二进制、p=16 和 K=256，在两个新输入上各做 5 对 off/on。集中布局 grain=8/256 均为 5/5 对胜出；grain=16384 时，两种输入分别只剩 4/6 个任务，最大任务占总 mix 成本的 62.5%/58.33%，没有稳定收益。当前运行时无法拆分任务，调整 victim 选择也无法消除单个大任务的限制。全部 60 对记录见 stealing-boundary 审计。',
    '粗粒度时两种布局': '粗粒度下，两种布局实际生成了相同初始队列。图上的点对应各自保存的计时组，但两组差别不能用布局来解释，也不能当作两个独立场景。',
    '分散布局初始每worker': '分散布局中，各 worker 的初始成本单位相等，开启窃取后仍观察到 epoch 缩短。成本单位相等未能保证完成时间一致；由于缺少独立核速度校准、稳定物理映射和 PMU 数据，现有结果尚无法确定原因。app 的改善较小，部分条件的变化方向也不一致。',
    '第二轮同时比较': '第二轮把构建选择和线程数、grain 一起筛选。下表是入选方案在两个新输入上相对该轮参数基线的结果，每组均 5/5 对胜出。这些倍数包含多项变化，不能全部归给窃取；适用范围也仍是当轮的候选和输入。',
    'memory_lanes4将': '第八轮把四个独立元素交错执行，两个输入的 epoch 都是 7/7 对胜出，达到至少 10% 改善并通过 app 退化限制。因此这项改动保留在该轮原构建的推荐中。数据生成、原 FNV 和完整标量核验都未省去，收益发生在任务内核。',
    '第四/五轮并行化': '第四、五轮改的是完整参考核验，其收益体现在应用总耗时，线程池执行的任务保持不变。第五轮三个类别在两个新输入上均为 7/7 对 app 胜出。这组对照与第二、八轮的基线不同，各轮倍数不能合并为共同基线上的总加速比。',
    '第十二轮独立noinline': '第十二轮用独立 noinline 探针补查初始化：zeroed 的 40/64 MiB 条件下，填充中位数约 3.25/5.32 ms，分配清零约 28.77/47.26 ms，完整 FNV 约 36.08/56.91 ms。overwrite 会把大量 minor faults 移到填充阶段。这些时间包含多种成本，不能直接算成应用收益；原 FNV 又有串行依赖，部分散列算完后也不能随意拼接成同一结果。',
    'cap4筛选中': 'cap4 在筛选中使 epoch 下降约 22.7%，但未在新输入上稳定改善，第二输入 app 中位数上升 8.01%。诊断显示成功 steals 减少、成本单位分配更均衡，同时描述符迁移总量增加。我按事前标准保留 single，并在确认失败后结束本轮选择，未改选其他候选。',
    '同一原Release': '第十五轮固定原 Release、p16、K256、round_robin 和 single，比较 immediate 与已有的 bounded_backoff。前者失败后 yield；后者从连续失败第 32 次起，请求固定 50 微秒的条件变量等待，取得任务后清零失败计数。本轮未测量实际等待时长、上下文切换或功耗。',
    '恢复批次20261025': '恢复批次 20261025T014536Z-V15-idle-backoff-f9520b 共运行 152 个进程，其中 112 份为正式计时。采用规则在采样前规定：两个输入的 grain=8 集中布局都至少 6/7 对胜出，候选 epoch 中位数不超过基线的 95%；其余条件 epoch 不超过基线的 110%，全部 app 不超过基线的 105%。结果未通过。这些是本项目的选择标准，不是统计显著性保证。',
    '首批因采集器身份缓存': '首批因采集器身份缓存未区分 grain，在第 5 个 control 停止，正式计时为 0。5 份应用输出独立复核均正确，重放共享缓存复现了该错误。保存原件后，修正 grain 缓存命名空间，按 docs/43 在新目录重跑完整流程；原协议见 docs/41，失败批次与恢复样本分开归档。',
    '诊断的attempts只': '诊断中，attempts 仅在第一处 victim 锁成功后增加，busy 包括两处取锁失败，因此 busy/attempts 不能解释为总失败率。empty、steals 描述窃取行为，其变化仍需结合耗时分析。逐对耗时、阶段时间和进程时间保存在 idle-backoff 审计与各 run 原件中。',
    '采用结论：': '退避未通过全部采用标准，因此保留 immediate 和既有推荐，未新增通用退避配置。',
    '第十六轮准备比较': '第十六轮计划比较 round_robin 与 seeded_random，两段等待后资源条件仍未满足，实际为 0 研究进程、0 计时。源码检查发现随机 victim 的同序号序列存在相关性，其对争抢和耗时的影响尚待实验验证。记录见 docs/46、47。',
    '依赖：': 'Linux 环境需要 CMake、C++20 编译器、pthread、Python3 和 nlohmann-json3-dev。Ubuntu 24.04 可安装 build-essential、cmake、python3、nlohmann-json3-dev。生成报告另需 report/requirements.txt 中的库，程序本身不依赖报告库。',
    '优化重建必须按': '要重建优化版本，还需按 builds.json 设置 WS_COMPLETION_BATCH、WS_STEAL_SCRATCH、WS_ENABLE_IPO、WS_COMPUTE_LANES。只编默认 Release 不会得到表里的优化内核。IPO 先做 CMake 能力检查；没有使用 fast-math 或 march=native。',
    '已有一次干净 Linux': '复现检查时，把 147 份源文件复制到新目录，默认、full、uniform 三种 Release 都运行了 CTest，六个原推荐配置也通过完整核验。命令、日志和新 binary 散列保存在 submission/reproduction/20261025/receipt.json。这检查的是程序功能；若要比较旧耗时，还需要还原当时的构建、输入和运行条件。',
    '并发检查覆盖': '并发检查覆盖空集合、单任务、少任务、多线程、重复 epoch、恰好一次执行、输出发布、异常恢复、退出和拒绝并发提交；扩展注册与非法 CLI 输入另查。第十一轮的 Release、ASan/UBSan、TSan 各有 2551 项 runtime 检查和 497 次 CLI 调用记录。这些数目对应各轮保存的构建，重新编译后的检查结果需要另记。',
    'CS149对应：': '本项目与 CS149 的任务划分、动态负载均衡和同步开销相对应。工作量与跨度用于分析大任务限制，独立依赖链用于理解 lanes；局部性实验还需考虑缓存容量与复用。epoch 大幅下降而 app 改善有限的结果，则体现了 Amdahl 定律对整体收益的约束。',
    '# 4. 偏斜任务：': '# 4. 偏斜任务：窃取收益与粗任务限制',
    '# 5. 局部性：': '# 5. 局部性：受控对照与证据限制',
    '# 6. 已确认优化': '# 6. 已确认优化及其作用阶段',
    '# 7. 负结果': '# 7. 未采用方案与验证结果',
    '# 9. 推荐组合': '# 9. 保留配置与构建来源',
    '# 10. 复现': '# 11. 复现方法与待完成事项',
    '若继续研究': '后续局部性实验需要能核实物理驻留的 Linux 环境，并固定重复访问、预读和实际迁移条件。新环境数据将独立保存，不与本机历史样本合并。',
}
polished, matched = [], set()
builds = read(ROOT / 'configs/verified/builds.json')
memory_builds = read(ROOT / 'configs/memory-interleaved/builds.json')
build_rows = []
for block in updated:
    for prefix, replacement in polish.items():
        if block.startswith(prefix):
            block = replacement
            matched.add(prefix)
            break
    if block.startswith('|报告内容|'):
        block = ('|题面要求|本文对应内容|\n|---|---|\n'
                 '|独立、可声明、可组合的策略|第1章：六类策略、注册扩展与并发生命周期|\n'
                 '|量化均衡、开销与局部性，覆盖 LLC 两端|第2-5章：固定工作量对照、512 KiB / 288 MiB 及证据限制|\n'
                 '|多种尝试后给出策略组合|第6-10章：确认结果、负结果、配置与项目复盘|\n'
                 '|代码、环境和连续 Prompt File|第11章与附录：功能复现、来源和附件状态|')
    if block.startswith('|模块|'):
        block = ('|策略|职责|当前实现|\n|---|---|---|\n'
                 '|Partition|划分任务粒度|fixed_grain、balanced_chunks|\n'
                 '|Placement|设置任务初始队列|按 home 或 round_robin 放置|\n'
                 '|Victim|选择窃取目标线程|round_robin、seeded_random|\n'
                 '|Timing|何时尝试、失败后如何等待|disabled、immediate、bounded_backoff|\n'
                 '|Migration|决定单次迁移的任务数量|single、capped_half|\n'
                 '|Affinity|配置线程逻辑 CPU 绑定|unbound、显式逻辑 CPU 列表|')
    if block.startswith('|范围|数据 / 解释入口|'):
        block = block.replace('|本报告可复算输入|report/final/input-data.json；figures/及tools/final_report.py|',
                              '|冻结综合输入|report/final/input-data.json；原图位于 report/final/figures/|\n'
                              '|本稿索引与生成器|report/student/evidence-index.json；tools/student_report.py|')
    if block.startswith('|seed / N|'):
        rows = ['|seed / N|grain|布局|epoch 前/后 ms|胜对|app 比|条件判定|',
                '|---|---|---|---|---|---|---|']
        for g in sorted(inputs['idle_confirmation']['groups'], key=lambda g: (not g['target'], g['grain'], g['layout'], g['seed'])):
            result_label = '主目标失败' if g['target'] else ('护栏通过' if g['pass'] else '护栏失败')
            assert not g['target'] or not g['pass']
            rows.append('|'+ '|'.join([
                f"{g['seed']} / {g['elements']}", str(g['grain']),
                '集中' if g['layout'] == 'concentrated' else '分散',
                f"{g['medians']['base']['epoch']*1000:.4f} / {g['medians']['candidate']['epoch']*1000:.4f}",
                f"{g['epoch_wins']}/7", f"{g['app_speedup']:.3f}", result_label])+'|')
        block = '\n'.join(rows)
    if re.match(r'^(light|uniform|skewed|memory) 原测量binary', block):
        kind = block.split()[0]
        record = builds[kind] if kind != 'memory' else {
            'build': 'Release / memory_lanes4',
            'binary_sha256': memory_builds['release_binary_sha256'],
            'source_id': memory_builds['measured_source_id'],
            'cmake_options': memory_builds['cmake_options'],
            'source_file': 'configs/memory-interleaved/builds.json',
            'original_record': memory_builds,
        }
        build_rows.append((kind, record))
        continue
    if block.startswith('![数据图](figures/w01'):
        block = '![数据图](figures/w01-overhead-styled.svg)'
    if block.startswith('![数据图](figures/v13'):
        block = '![数据图](figures/v13-boundary-styled.svg)'
    polished.append(block)
    if block.startswith('worker 是'):
        polished.append('运行流程与实验路线见前页图1a、图1b。本节说明策略接口和并发生命周期。')
    if block.startswith('我用 epoch'):
        polished.append('读后面的表格时，时间比都取两组全部成功样本的中位数之比。off/on 或基线/候选大于 1，表示开启窃取或候选更快；foreign/home 大于 1，则是换执行者后更慢。“胜对”另按预定重复编号逐对比较，数候选更快的次数，和中位数比值回答的问题不同。')
    if block.startswith('![数据图](figures/w01'):
        polished.append('图2：均匀任务的粒度对照（p=4，n=3/条件）。纵轴截取 205-213.3 ms 以显示细小差异，曲线起伏不能直接读成较大的百分比收益。')
    if block.startswith('![数据图](figures/v13'):
        polished.append('图3：优化后二进制的窃取开关对照（p=16，n=5/条件）。虚线 1 表示两组中位数相同；纵轴大于 1 表示开启窃取的 epoch 更短。')
    if block.startswith('第十五轮固定原 Release'):
        polished.append('表中 epoch 前/后依次为 immediate / backoff，app 比为 immediate/backoff。“护栏通过”表示该条件未超过预定退化限制；采用退避要求两个主要目标与全部护栏同时通过。')
    if block.startswith('表为固定工作集'):
        polished[-1] = '每个条件有 3 次正式计时。上表固定工作集、访问遍数和预读，只在两个 home 方向改变执行者。大工作集和中间工作集的两个方向没有一致趋势；仅凭这些墙钟时间，还无法知道 cache miss、DRAM 流量和缓存迁移各占多少。'
    if block.startswith('复现时需要区分'):
        assert len(build_rows) == 4
        polished.append('|任务|测量构建|binary / source 的 SHA256 前16位|\n|---|---|---|\n' + '\n'.join(
            f"|{kind}|{r['build']}|{r['binary_sha256'][:16]} / {r['source_id'][:16]}|" for kind, r in build_rows))
        polished.append('构建差异：full_lanes8 使用 batch32、scratch、LTO 和八路计算链；uniform 的 lanes8 使用 batch1、关闭 scratch，保留 LTO 与八路链。memory 的四路交错由配置指定。重建时要使用各自记录的选项。')
assert matched == set(polish), set(polish) - matched
work_narrative = (REPORT / '工作说明与探究过程.md').read_text(encoding='utf-8').strip().split('\n\n')
# Summarize only already audited comparisons; no new measurements or shared baseline.
boundary_highlights = [g for g in inputs['boundary_groups']
                       if g['layout'] == 'concentrated' and g['grain'] in (8, 256)]
assert len(boundary_highlights) == 4 and all(g['epoch_wins'] == 5 for g in boundary_highlights)
boundary_ratios = [g['medians']['off']['epoch'] / g['medians']['on']['epoch'] for g in boundary_highlights]
uniform_highlights = read(ROOT / 'optimization/results/optimization-summary.json')['selection']['uniform']['heldout']
assert len(uniform_highlights) == 2 and all(g['wins'] == 5 for g in uniform_highlights)
uniform_epoch_ratios = [g['base']['epoch_seconds']['median'] / g['candidate']['epoch_seconds']['median']
                        for g in uniform_highlights]
uniform_app_ratios = [g['base']['end_to_end_seconds']['median'] / g['candidate']['end_to_end_seconds']['median']
                      for g in uniform_highlights]
memory_highlights = inputs['memory_groups']
assert len(memory_highlights) == 2 and all(g['wins'] == 7 for g in memory_highlights)
memory_epoch_ratios = [g['medians']['base']['epoch'] / g['medians']['candidate']['epoch'] for g in memory_highlights]
memory_app_reductions = [(1 - g['medians']['candidate']['app'] / g['medians']['base']['app']) * 100
                         for g in memory_highlights]
assert f'{min(boundary_ratios):.2f}-{max(boundary_ratios):.2f}' == '2.62-3.06'
assert f'{min(uniform_epoch_ratios):.3f}-{max(uniform_epoch_ratios):.3f}' == '13.886-15.806'
assert f'{min(uniform_app_ratios):.3f}-{max(uniform_app_ratios):.3f}' == '1.264-1.273'
performance_table = ('|实验对照|任务执行表现|应用总时间表现|\n|---|---|---|\n'
    f'|第十三轮集中，p16，grain8/256；off→on|时间比 {min(boundary_ratios):.2f}-{max(boundary_ratios):.2f}；两个输入各条件 5/5 胜|改善小于 epoch；按条件报告，见第4章|\n'
    f'|第二轮 uniform；参数基线→联合配置|时间比 {min(uniform_epoch_ratios):.3f}-{max(uniform_epoch_ratios):.3f}；两个输入各 5/5 胜|时间比 {min(uniform_app_ratios):.3f}-{max(uniform_app_ratios):.3f}，见第6章|\n'
    f'|第八轮 memory；同二进制 1路→4路|时间比 {memory_epoch_ratios[0]:.3f} / {memory_epoch_ratios[1]:.3f}；各 7/7 胜|中位数降低 {memory_app_reductions[0]:.2f}% / {memory_app_reductions[1]:.2f}%；仅作退化护栏|')
retrospective = (REPORT / '项目复盘.md').read_text(encoding='utf-8').strip()
assert retrospective.count('@@PERFORMANCE_SUMMARY@@') == 1
retrospective_blocks = retrospective.replace('@@PERFORMANCE_SUMMARY@@', performance_table).split('\n\n')
performance_highlights = {
    'boundary_epoch_ratios': boundary_ratios,
    'uniform_epoch_ratios': uniform_epoch_ratios,
    'uniform_app_ratios': uniform_app_ratios,
    'memory_epoch_ratios': memory_epoch_ratios,
    'memory_app_median_reductions_percent': memory_app_reductions,
    'basis': 'Existing audited groups only; comparisons have separate baselines and cannot be multiplied.',
}
updated = []
for block in polished:
    if block.startswith('# 1. 架构'):
        updated.extend(work_narrative)
        updated.extend((REPORT / '图解.md').read_text(encoding='utf-8').strip().split('\n\n'))
    if block.startswith('# 11. 复现方法'):
        updated.extend(retrospective_blocks)
    if block.startswith('# 3. 均匀任务'):
        updated.append(block)
        updated.append('均匀负载中，各元素的工作量相同。本节通过改变分组粒度和执行器，观察任务划分对完成时间的影响。')
        continue
    if block.startswith('# 4. 偏斜任务'):
        updated.append(block)
        updated.append('偏斜负载保持总工作量不变，通过集中放置重任务检验窃取的均衡效果，再增大 grain 检查粗任务限制。布局决定初始分配，粒度决定可重新分配的任务数量。')
        continue
    if block.startswith('# 5. 局部性'):
        updated.append(block)
        updated.append('局部性实验固定数据 home、访问遍数和预读，受控改变执行者，并检查动态运行中的实际窃取。缓存迁移的归因还需要线程驻留和硬件观测，不能仅依据工作集大小判断。')
        continue
    updated.append(block)
    if block.startswith('第四、五轮改的是'):
        updated.append('四路交错的等价性也单独检查过。memory 中每个元素的下一步依赖当前 x，但不同元素的 x 和数据区间独立。新实现轮流推进四个元素，对每个元素仍保留原来的 pass、word 顺序，尾部不足四个就退回标量；完整标量参考还会逐元素重算。具体实现和边界检查见 docs/28。')
    if block.startswith('cap4 在筛选中'):
        updated.append('一次窃取可以转移多个描述符，同一任务也可能多次迁移，因此最终执行者不足以重建完整迁移过程。新输入的耗时不支持采用 cap4；锁竞争、等待和重复迁移的各自贡献，现有诊断尚无法量化。')
    if block.startswith('构建差异：'):
        updated.append('策略层采用 fixed_grain、round_robin victim、immediate、single 和显式逻辑掩码。初始队列还同时受 placement 与 layout 控制：skewed 配置使用 concentrated，memory 使用 policy。因此复现必须读取完整 JSON，仅照抄 worker/grain 不足以还原实验。')
text = '\n\n'.join(updated) + '\n'

# A machine-readable map from report sections to the exact frozen timing runs.
def run_references(obj, area=''):
    refs = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == 'run_path':
                refs.append('/'.join(x for x in (area, value.replace('\\', '/')) if x))
            elif key == 'run_paths':
                refs.extend('/'.join(x for x in (area, p.replace('\\', '/')) if x) for p in value)
            else:
                refs.extend(run_references(value, area))
    elif isinstance(obj, list):
        for item in obj:
            refs.extend(run_references(item, area))
    return sorted(set(refs))

first = read(ROOT / 'results/study-summary.json')
second = read(ROOT / 'optimization/results/optimization-summary.json')
evidence_sections = {}
def evidence_section(key, source_file, groups, area='', modes=None):
    records = []
    for number, g in enumerate(groups, 1):
        refs = run_references(g['pairs'] if modes else g, area)
        assert refs and all(ref in verified for ref in refs), (key, number)
        record = {'group': number, **{k: g[k] for k in ('experiment', 'condition', 'seed', 'elements', 'grain', 'layout', 'target') if k in g},
                  'run_paths': refs, 'timing_run_count': len(refs)}
        if modes:
            recomputed = {}
            for mode in modes:
                paths = run_references([p[mode] for p in g['pairs']], area)
                recomputed[mode] = {metric: statistics.median(verified[p][metric] for p in paths) for metric in ('epoch', 'app')}
                assert recomputed[mode] == {metric: g['medians'][mode][metric] for metric in ('epoch', 'app')}
            record['recomputed_medians_seconds'] = recomputed
        elif 'run_paths' in g:
            recomputed = {metric: statistics.median(verified[p][metric] for p in refs) for metric in ('epoch', 'app')}
            assert recomputed == {'epoch': g['epoch_seconds']['median'], 'app': g['end_to_end_seconds']['median']}
            record['recomputed_medians_seconds'] = recomputed
        else:
            recomputed = {}
            for mode in ('base', 'candidate'):
                paths = run_references(g[mode])
                recomputed[mode] = {metric: statistics.median(verified[p][metric] for p in paths) for metric in ('epoch', 'app')}
                assert recomputed[mode] == {'epoch': g[mode]['epoch_seconds']['median'], 'app': g[mode]['end_to_end_seconds']['median']}
            assert g['base_over_candidate'] == recomputed['base']['epoch'] / recomputed['candidate']['epoch']
            record['recomputed_medians_seconds'] = recomputed
        records.append(record)
    evidence_sections[key] = {'source': source_file, 'source_sha256': digest(ROOT / source_file), 'groups': records}

evidence_section('chapters_3_to_5_first_round', 'results/study-summary.json',
                 [g for g in first['groups'] if g['experiment'] in ('W00_W01', 'W02', 'W03')])
evidence_section('chapter_4_figure_3_v13', 'stealing-boundary/results/audit-6508b2892aa3457087dda02bd6d45825.json', inputs['boundary_groups'], 'stealing-boundary', ('off', 'on'))
evidence_section('chapter_6_v2', 'optimization/results/optimization-summary.json',
                 [dict(h, condition=kind) for kind, selection in second['selection'].items() for h in selection['heldout']])
evidence_section('chapter_6_v8', 'memory-kernel/results/audit-17ca23a49da34a6198c79dbbc8438cbd.json', inputs['memory_groups'], 'memory-kernel', ('base', 'candidate'))
evidence_section('chapter_7_v14', 'results/batch-migration-delivery-20261025.json', inputs['batch_confirmation']['groups'], 'batch-migration', ('base', 'candidate'))
evidence_section('chapter_8_v15', 'idle-backoff/results/audit-4d557c92373243ae950026e6bb6c2e5a.json', inputs['idle_confirmation']['groups'], 'idle-backoff', ('base', 'candidate'))
indexed = set(p for section in evidence_sections.values() for g in section['groups'] for p in g['run_paths'])
assert indexed == set(verified), (len(indexed), len(verified))
evidence_index = {
    'scope': 'Timing groups used by the consolidated report and this student revision; not every historical process.',
    'sections': evidence_sections, 'unique_timing_runs': len(indexed),
    'runs': verified, 'recommended_builds': {kind: record for kind, record in build_rows},
    'historical_phase_observations': {
        'source': 'refinement/profiling/results/phase-summary.json',
        'source_sha256': digest(ROOT / 'refinement/profiling/results/phase-summary.json'),
        'groups': phase_evidence, 'run_count': sum(g['run_count'] for g in phase_evidence.values()),
        'included_in_timing': False,
    },
    'exploration_narrative': {
        'source': 'report/student/工作说明与探究过程.md',
        'sha256': digest(REPORT / '工作说明与探究过程.md'),
        'basis': 'Retrospective account based on dated protocols, results and decisions; no invented contemporaneous diary.',
    },
    'project_retrospective': {
        'source': 'report/student/项目复盘.md',
        'sha256': digest(REPORT / '项目复盘.md'),
        'performance_highlights': performance_highlights,
        'timing_section_keys': ['chapter_4_figure_3_v13', 'chapter_6_v2', 'chapter_6_v8'],
        'functional_reproduction_source': 'submission/reproduction/20261025/receipt.json',
        'functional_reproduction_sha256': digest(ROOT / 'submission/reproduction/20261025/receipt.json'),
        'not_an_external_ranking': True,
    },
    'visual_design': {
        'provenance': 'report/student/figures/design-provenance.json',
        'provenance_sha256': digest(REPORT / 'figures/design-provenance.json'),
        'chart_data': 'report/student/figures/chart-data.json',
        'chart_data_sha256': digest(REPORT / 'figures/chart-data.json'),
        'scope': 'Two generated concept designs reconstructed as editable SVG; numeric charts redrawn from frozen data.',
        'new_performance_samples': 0,
    },
    'new_performance_samples': 0,
}
(REPORT / 'evidence-index.json').write_text(json.dumps(evidence_index, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

pdfmetrics.registerFont(TTFont('StudentSong', 'C:/Windows/Fonts/simsun.ttc', subfontIndex=0))
pdfmetrics.registerFont(TTFont('StudentHei', 'C:/Windows/Fonts/simhei.ttf'))
pdfmetrics.registerFont(TTFont('Microsoft YaHei', 'C:/Windows/Fonts/msyh.ttc', subfontIndex=0))
pdfmetrics.registerFont(TTFont('DejaVu Sans', str(ROOT / '.cache/report-python/matplotlib/mpl-data/fonts/ttf/DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('DejaVu Sans Bold', str(ROOT / '.cache/report-python/matplotlib/mpl-data/fonts/ttf/DejaVuSans-Bold.ttf')))
pdfmetrics.registerFontFamily('DejaVu Sans', normal='DejaVu Sans', bold='DejaVu Sans Bold',
                              italic='DejaVu Sans', boldItalic='DejaVu Sans Bold')
pdfmetrics.registerFontFamily('Microsoft YaHei', normal='Microsoft YaHei', bold='Microsoft YaHei',
                              italic='Microsoft YaHei', boldItalic='Microsoft YaHei')
# svglib 2.3 uses a separate SVG font registry, independent of pdfmetrics.
for family in ('Microsoft YaHei', 'DejaVu Sans'):
    for weight in ('normal', 'bold'):
        target = 'DejaVu Sans Bold' if family == 'DejaVu Sans' and weight == 'bold' else family
        font_path = ('C:/Windows/Fonts/msyh.ttc' if family == 'Microsoft YaHei' else
                     str(ROOT / '.cache/report-python/matplotlib/mpl-data/fonts/ttf' /
                         ('DejaVuSans-Bold.ttf' if weight == 'bold' else 'DejaVuSans.ttf')))
        for style in ('normal', 'italic'):
            registered, exact = register_svg_font(family, font_path=font_path, weight=weight,
                                                   style=style, rlgFontName=target)
            assert registered and exact
width = A4[0] - 88
styles = {
    'body': ParagraphStyle('body', fontName='StudentSong', fontSize=9.6, leading=14.8, wordWrap='CJK', spaceAfter=7),
    'head': ParagraphStyle('head', fontName='StudentHei', fontSize=15, leading=22, textColor=colors.HexColor('#263d55'), spaceAfter=13),
    'cell': ParagraphStyle('cell', fontName='StudentSong', fontSize=8.5, leading=12.1, wordWrap='CJK'),
    'caption': ParagraphStyle('caption', fontName='StudentSong', fontSize=8.5, leading=12.3, textColor=colors.HexColor('#526477'), wordWrap='CJK', spaceAfter=8),
    'subhead': ParagraphStyle('subhead', fontName='StudentHei', fontSize=10.5, leading=15, textColor=colors.HexColor('#263d55'), spaceBefore=7, spaceAfter=5, keepWithNext=True),
    'code': ParagraphStyle('code', fontName='Courier', fontSize=8, leading=12, spaceAfter=8),
}

def runtime_diagram():
    drawing = Drawing(width, 88)
    box_width, gap, box_y = (width - 30) / 4, 10, 30
    labels = [('配置与策略', 'JSON / Registry'), ('冻结与分发', 'Partition / Placement'),
              ('执行与窃取', 'Victim / Timing / Migration'), ('发布与核验', '完成计数 / 逐元素参考')]
    for i, (title, detail) in enumerate(labels):
        x = i * (box_width + gap)
        drawing.add(Rect(x, box_y, box_width, 45, rx=4, ry=4, fillColor=colors.HexColor('#edf3f8'), strokeColor=colors.HexColor('#a3b5c4'), strokeWidth=.6))
        drawing.add(String(x + box_width / 2, box_y + 28, title, fontName='StudentHei', fontSize=10, textAnchor='middle', fillColor=colors.HexColor('#263d55')))
        drawing.add(String(x + box_width / 2, box_y + 12, detail, fontName='StudentSong', fontSize=7.1, textAnchor='middle'))
        if i < 3:
            end = x + box_width + gap - 1
            drawing.add(Line(x+box_width+1, box_y+22, end, box_y+22, strokeColor=colors.HexColor('#526477')))
            drawing.add(Polygon([end,box_y+22,end-3,box_y+24,end-3,box_y+20], fillColor=colors.HexColor('#526477'), strokeColor=None))
    drawing.add(String(width/2, 12, 'Affinity 约束工作线程的逻辑 CPU 请求；迁移对象是任务描述符。', fontName='StudentSong', fontSize=8.2, textAnchor='middle', fillColor=colors.HexColor('#526477')))
    return drawing

figure_dir = REPORT / 'figures'
figure_dir.mkdir(exist_ok=True)
native_diagrams = {'runtime-flow-designed.svg': designed_runtime(),
                   'exploration-roadmap-designed.svg': roadmap_diagram()}
design_provenance = read(figure_dir / 'design-provenance.json')
for asset in design_provenance['assets'].values():
    for field in ('source_image', 'prompt', 'vector'):
        assert digest(ROOT / asset[field]) == asset[field+'_sha256']
    assert asset['embedded_raster_images'] == 0
    assert '<image' not in (ROOT / asset['vector']).read_text(encoding='utf-8')
story = []
for block in updated:
    if block.startswith('# '):
        if story:
            story.append(PageBreak())
        story.append(Paragraph(html.escape(block[2:]), styles['head']))
    elif block.startswith('## '):
        story.append(Paragraph(html.escape(block[3:]), styles['subhead']))
    elif block.startswith('|'):
        rows = [[x.strip() for x in line.strip('|').split('|')] for line in block.splitlines()]
        rows = [rows[0]] + rows[2:]
        n = len(rows[0])
        weights = ([1.55, 3.05] if rows[0][0] == '题面要求' else [1.1, 3.5] if n == 2
                   else [1.1, 1.1, 1.8, 2.6] if n == 4 and rows[0][0] == '任务'
                   else [1.05, 1.75, 2.8] if rows[0][0] == '策略'
                   else [.4, 1.5, 2.7] if rows[0][0] == '轮次'
                   else [.9, 3.1, 1.6] if rows[0][0] == '工作内容'
                   else [1.5, 1.7, 1.8] if rows[0][0] == '实验对照'
                   else [1.1, .55, .6, 1.9, .5, .6, .9] if n == 7
                   else [1, 1.3, 3] if rows[0][0] == '任务' and n == 3 else [1] * n)
        col_widths = [width * v / sum(weights) for v in weights]
        table = Table([[Paragraph(html.escape(x), styles['cell']) for x in row] for row in rows], colWidths=col_widths, repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eaf0f5')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7f9fb')]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEABOVE', (0, 0), (-1, 0), .6, colors.HexColor('#263d55')),
            ('LINEBELOW', (0, -1), (-1, -1), .5, colors.HexColor('#263d55')),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.extend([table, Spacer(1, 9)])
    elif block.startswith('!['):
        rel = re.search(r'\((.*?)\)', block).group(1)
        original = REPORT / rel
        assert original.is_file()
        assert original.suffix == '.svg'
        im = native_diagrams.get(original.name)
        if im is None:
            im = svg2rlg(str(original))
        assert im is not None
        factor = width / im.width
        original_height = im.height
        im.scale(factor, factor)
        im.width, im.height = width, original_height * factor
        story.extend([im, Spacer(1, 8)])
    elif block.startswith(('cmake ', 'ctest ', './build/')):
        story.append(Preformatted(block, styles['code']))
    elif re.match(r'^图[123][ab]?：', block):
        story.append(Paragraph(html.escape(block), styles['caption']))
    else:
        story.append(Paragraph(html.escape(block), styles['body']))

def footer(canvas, document):
    canvas.saveState()
    canvas.setFont('StudentSong', 8)
    canvas.setFillColor(colors.HexColor('#596579'))
    canvas.drawString(44, 24, 'HPC 创意项目 · Mini WorkSteal · 2026-10-26 修订')
    canvas.drawRightString(A4[0] - 44, 24, str(document.page))
    canvas.restoreState()

SimpleDocTemplate(str(PDF), pagesize=A4, rightMargin=44, leftMargin=44,
                  topMargin=44, bottomMargin=43,
                  title='Mini WorkSteal：可组合工作窃取运行时的实现与实验分析', author='').build(story, onFirstPage=footer, onLaterPages=footer)
# Repoint image references for this separate editable copy; the original report remains untouched.
MD.write_text(text, encoding='utf-8')
pages = PdfReader(PDF).pages
expected_pages = sum(block.startswith('# ') for block in updated)
assert expected_pages == 16
assert len(pages) == expected_pages, f'Unexpected overflow: {len(pages)} pages'
with pdfplumber.open(PDF) as doc:
    bounds = []
    for i, page in enumerate(doc.pages, 1):
        words = page.extract_words()
        assert len(page.extract_text() or '') > 200, f'Sparse page {i}'
        bad = [w for w in words if w['x0'] < 38 or w['x1'] > page.width - 35 or w['top'] < 15 or w['bottom'] > page.height - 15]
        assert not bad, (i, bad[:2])
        page_text = page.extract_text() or ''
        bounds.append({'page': i, 'characters': len(page_text)})
    assert '工作说明' in doc.pages[1].extract_text() and '探究过程' in doc.pages[2].extract_text()
    assert '96.5%' in doc.pages[2].extract_text() and '97.1%' in doc.pages[2].extract_text()
    assert '项目复盘' in doc.pages[13].extract_text()
    assert '13.886-15.806' in doc.pages[13].extract_text()
    assert '运行流程与实验路线' in doc.pages[3].extract_text()
    assert '静态队列' in doc.pages[6].extract_text()
    assert '每任务元素数' in doc.pages[6].extract_text()
    assert 'epoch 时间比 off / on' in ''.join(c['text'] for c in doc.pages[7].chars)
    assert not any(page.images for page in doc.pages), 'Expected vector-only report figures'
    assert '@@PERFORMANCE_SUMMARY@@' not in text
poppler = 'C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe'
subprocess.run([poppler, '-r', '100', '-png', str(PDF), str(TMP / 'page')], check=True)
sheet = Image.new('RGB', (1200, ((len(pages)+3)//4)*440), '#e8edf2')
for i in range(len(pages)):
    im = Image.open(TMP / f'page-{i+1:02}.png').convert('RGB')
    im.thumbnail((280, 398))
    x, y = (i % 4) * 300, (i // 4) * 440
    sheet.paste(im, (x + (300 - im.width) // 2, y + 12))
    ImageDraw.Draw(sheet).text((x + 145, y + 420), str(i+1), fill='#263d55')
sheet.save(TMP / 'contact-sheet.png')
manifest = {
    'report_date': '2026-10-25', 'revision_date': '2026-10-26',
    'pdf': PDF.name, 'pdf_sha256': digest(PDF), 'markdown_sha256': digest(MD),
    'pages': len(pages), 'page_text_checks': bounds,
    'verified_raw_run_count': len(verified), 'verified_source_count': len(source_locations),
    'verified_historical_profiling_count': sum(g['run_count'] for g in phase_evidence.values()),
    'supplementary_source_sha256': supplementary_sources,
    'verified_session_file_sha256': session['files'],
    'source_locations_current_or_frozen': source_locations,
    'source_report_sha256': digest(ROOT / 'report/final/技术报告.md'),
    'source_manifest_sha256': digest(ROOT / 'report/final/input-data.json'),
    'generator_sha256': digest(Path(__file__)),
    'revision': 'polished-v9-professional-student',
    'evidence_index_sha256': digest(REPORT / 'evidence-index.json'),
    'figure_sha256': {p.relative_to(ROOT).as_posix(): digest(p) for p in
                      [figure_dir / name for name in ('runtime-flow-designed.svg', 'exploration-roadmap-designed.svg',
                                                      'w01-overhead-styled.svg', 'v13-boundary-styled.svg')]},
    'vector_only_figures': True,
    'new_performance_samples': 0, 'raw_evidence_modified': False,
    'visual_review': 'pending; manually inspect all rendered pages',
    'existing_packages_updated': False, 'external_submission_sent': False,
}
(REPORT / 'student-report-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in manifest.items() if k != 'source_locations_current_or_frozen'}, ensure_ascii=False))
