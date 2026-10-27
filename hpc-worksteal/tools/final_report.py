#!/usr/bin/env python3
"""Build one consolidated technical report from audited, rechecked raw evidence."""
import argparse
import collections
import html
import json
import pathlib
import statistics
import sys

import lab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(lab.ROOT))
    ap.add_argument('--font', required=True)
    a = ap.parse_args()
    root = pathlib.Path(a.root).resolve()
    lab.ROOT = root
    cache = root/'.cache/report-python'
    if cache.exists():
        sys.path.insert(0, str(cache))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image, PageBreak

    out, figures = root/'report/final', root/'report/final/figures'
    figures.mkdir(parents=True, exist_ok=True)
    sources, verified = {}, {}
    # Narrative explanations and protocol/history references are inputs too.
    for source in sorted((root/'docs').glob('*.md')):
        sources[source.relative_to(root).as_posix()] = lab.digest(source)
    def read(rel):
        p = root/rel
        sources[rel] = lab.digest(p)
        return json.loads(p.read_text(encoding='utf-8-sig'))
    def raw(area, rel):
        p = root/area/pathlib.Path(rel.replace('\\', '/'))
        key = p.relative_to(root).as_posix()
        if key not in verified:
            hashes = json.loads((p/'checksums.json').read_text(encoding='utf-8-sig'))
            assert set(hashes) == {f.relative_to(p).as_posix() for f in p.iterdir() if f.is_file() and f.name != 'checksums.json'}
            for name, sha in hashes.items():
                assert lab.digest(p/name) == sha
            r = json.loads((p/'result.json').read_text(encoding='utf-8-sig'))
            m = json.loads((p/'metadata.json').read_text(encoding='utf-8-sig'))
            assert m['status'] == 'completed' and m['included'] and m['purpose'] == 'timing'
            assert r['correctness']['pass'] and json.loads((p/'stdout.log').read_bytes()) == r
            assert not (p/'stderr.log').read_bytes()
            for e in r['epochs']:
                assert e['correctness']['pass'] and e['correctness']['mismatches'] == 0
                assert e['correctness']['compared_elements'] == r['resolved_config']['workload']['elements']
            verified[key] = {'epoch': r['timing']['epoch_seconds'], 'app': r['timing']['end_to_end_seconds'],
                             'binary_sha256': m['binary_sha256'], 'result_sha256': lab.digest(p/'result.json')}
        return verified[key]
    def group_first(g):
        rr = [raw('', p) for p in g['run_paths']]
        assert all(r['binary_sha256'] == g['binary_sha256'] for r in rr)
        assert statistics.median(r['epoch'] for r in rr) == g['epoch_seconds']['median']
        assert statistics.median(r['app'] for r in rr) == g['end_to_end_seconds']['median']
    def pairs_check(area, groups, modes):
        for g in groups:
            for mode in modes:
                rr = [raw(area, p[mode]['run_path']) for p in g['pairs']]
                assert statistics.median(r['epoch'] for r in rr) == g['medians'][mode]['epoch']
                assert statistics.median(r['app'] for r in rr) == g['medians'][mode]['app']
                for row, pair in zip(rr, g['pairs']):
                    assert row['epoch'] == pair[mode]['epoch'] and row['app'] == pair[mode]['app']
    first = read('results/study-summary.json')
    assert first['complete']
    claims = {c['id']: c for c in first['claims']}
    for g in first['groups']:
        if g['experiment'] in ('W00_W01', 'W02', 'W03'):
            group_first(g)
    boundary_path = 'stealing-boundary/results/audit-6508b2892aa3457087dda02bd6d45825.json'
    boundary = read(boundary_path)
    assert boundary['audit_pass'] and boundary['complete']
    pairs_check('stealing-boundary', boundary['groups'], ('off', 'on'))
    memory_receipt = read('results/memory-kernel-delivery-20261021.json')
    memory = read(memory_receipt['windows_audit'])
    assert memory['audit_pass'] and memory['accepted']
    pairs_check('memory-kernel', memory['heldout'], ('base', 'candidate'))
    batch = read('results/batch-migration-delivery-20261025.json')
    pairs_check('batch-migration', batch['confirmation']['groups'], ('base', 'candidate'))
    paths = sorted((root/'idle-backoff/results').glob('audit-*.json'))
    assert paths, 'V15 must have archived results before consolidation'
    idle = read(paths[0].relative_to(root).as_posix())
    assert idle['audit_pass'] and idle['complete']
    pairs_check('idle-backoff', idle['confirmation']['groups'], ('base', 'candidate'))
    second = read('optimization/results/optimization-summary.json')
    assert second['complete']
    opt_rows = []
    for kind, selection in second['selection'].items():
        for h in selection['heldout']:
            for mode in ('base', 'candidate'):
                rr = [raw('', p) for p in h[mode]['run_paths']]
                assert statistics.median(r['epoch'] for r in rr) == h[mode]['epoch_seconds']['median']
                assert statistics.median(r['app'] for r in rr) == h[mode]['end_to_end_seconds']['median']
            b, c = h['base'], h['candidate']
            opt_rows.append([kind, str(h['seed']), f"{h['base_over_candidate']:.3f}",
                f"{b['end_to_end_seconds']['median']/c['end_to_end_seconds']['median']:.3f}", f"{h['wins']}/5"])
    cfgs = {kind: read('configs/verified/'+kind+'.json') for kind in ('light', 'uniform', 'skewed')}
    cfgs['memory'] = read('configs/memory-interleaved/memory.json')
    builds = read('configs/verified/builds.json')
    memory_build = read('configs/memory-interleaved/builds.json')
    session = read('submission/prompts/session-20261025-v15-preparation/manifest.json')
    for rel, sha in session['files'].items():
        assert lab.digest(root/'submission/prompts/session-20261025-v15-preparation'/rel) == sha
    reproduction_path = root/'submission/reproduction/20261025/receipt.json'
    reproduction = read(reproduction_path.relative_to(root).as_posix()) if reproduction_path.exists() else None

    font = FontProperties(fname=a.font)
    plt.rcParams.update({'axes.spines.top': False, 'axes.spines.right': False, 'font.size': 9})
    def finish_fig(fig, name):
        fig.tight_layout()
        for ext in ('png', 'svg'):
            fig.savefig(figures/(name+'.'+ext), dpi=180, bbox_inches='tight')
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 2.8))
    for mode, label in (('static', '静态队列'), ('central', '集中队列'), ('off', '禁止窃取'), ('on', '允许窃取')):
        gs = [next(g for g in first['groups'] if g['experiment'] == 'W00_W01' and g['condition'] == f'{mode}-p4-g{x}') for x in (1,64,4096)]
        ax.plot((1,64,4096), [g['epoch_seconds']['median']*1000 for g in gs], marker='o', label=label)
    ax.set_xscale('log', base=2)
    ax.set_xticks((1,64,4096), labels=('1','64','4096'))
    ax.set_xlabel('每任务元素数 grain', fontproperties=font)
    ax.set_ylabel('epoch 中位数 / ms', fontproperties=font)
    ax.legend(prop=font, ncol=2)
    finish_fig(fig, 'w01-overhead')
    fig, axes = plt.subplots(1, 2, figsize=(7, 2.8), sharey=True)
    for ax, seed in zip(axes, (100003,106013)):
        for layout, label in (('concentrated','集中'),('spread','分散')):
            gs = sorted([g for g in boundary['groups'] if g['seed']==seed and g['layout']==layout], key=lambda g:g['grain'])
            ax.plot([str(g['grain']) for g in gs], [g['epoch_speedup'] for g in gs], marker='o', label=label)
        ax.axhline(1, color='#888888', linestyle='--', linewidth=.8)
        ax.set_title(f'seed {seed}')
        ax.set_xlabel('grain', fontproperties=font)
        ax.legend(prop=font)
    axes[0].set_ylabel('epoch: off / on', fontproperties=font)
    finish_fig(fig, 'v13-boundary')

    sections = []
    def h(title): sections.append(('h', title))
    def p(text): sections.append(('p', text))
    def table(headers, rows, widths=None): sections.append(('table', (headers, rows, widths)))
    def image(name): sections.append(('image', name))
    def page(): sections.append(('page', None))
    h('Mini WorkSteal：可组合策略与可解释性能')
    p('LZUHPC 2026 秋季 HPC 创意项目技术报告 | 2026-10-25')
    p('研究问题：固定总工作量时，任务粒度和初始不均衡怎样决定工作窃取是否值得？实现采用C++20、持久线程池和带锁双端队列，策略独立注册；任务集合在执行前冻结，不支持递归spawn或DAG。正式评测来自Ubuntu 24.04 / WSL1，Windows仅用于编辑、归档与报告排版。')
    p('结论：动态调度能缓解本项目的集中偏斜，但不能拆开过大的任务。第十三轮相同优化二进制、16worker下，grain8/256集中布局两个输入的epoch约快2.62-3.06倍；粗粒度仅4/6任务，没有稳定收益。分散布局的工作单位相等也不保证同时完成。')
    p('优化需要按阶段解释。八路独立计算链、完成发布批处理、窃取暂存和线程/粒度联合优化获得过确认收益；完整参考核验并行化改善的是应用端到端；四路memory执行交错改善的是任务内核。它们不是同一种窃取收益，跨轮倍数不能相乘。')
    p('批量窃取在第十四轮减少操作次数、改善单位均衡度，仍未通过新输入确认；第十五轮退避结果见后文。负结果保留并参与方案选择，不把筛选最优或单个最快运行作为结论。')
    table(['交付对象','当前证据'], [
        ['运行时、策略、完整核验','源代码、独立扩展入口、真实构建/检查记录及逐run来源'],
        ['实验与推荐','十五轮研究；历史配置与测量二进制分别追溯，全部慢成功样本保留'],
        ['复现与环境','原生Linux重建状态见复现章节；DevContainer实建未证明'],
        ['Prompt File', f"真实同一连续Session截至快照时刻：{session['visible_messages']}条可见消息，不含思维链"]])
    p('本报告不宣称跨平台最优、物理核心映射、NUMA效应或缓存miss因果；检查通过也不是无数据竞争的形式证明。')
    page()
    h('1. 架构与并发生命周期')
    table(['模块','职责与边界'], [
        ['Partition','按逻辑区间生成固定TaskId集合；fixed_grain、balanced_chunks'],
        ['Placement','决定初始队列；独立于任务切分及数据home'],
        ['Victim','只选择被尝试的worker；round_robin、seeded_random'],
        ['Timing','disabled、immediate、bounded_backoff决定空闲行为'],
        ['Migration','single或capped_half决定描述符转移数量，不迁移数据页'],
        ['Affinity','unbound或显式逻辑CPU列表；记录请求和实际掩码']])
    p('执行器包括直接串行、静态本地队列、集中队列和工作窃取；S3-off/on是同一工作窃取执行器的策略开关，保留本地队列、锁、任务顺序和完成协议。off的idle wait与on的idle yield也不同，所以off/on是整套决策的净效果，而不是纯粹搬运指令的费用。')
    p('owner从队尾取，thief从队头取。策略回调不在队列锁内执行：先try_lock取victim长度快照，释放锁后调用迁移策略，再次try_lock并按当前剩余任务数裁剪。不会同时持有两把队列锁。single在暂存优化下直接返回第一个任务，多余任务才进入本地队列。')
    p('prepare冻结队列；run在状态锁下记录t0并推进generation，worker释放后执行。完成任务的结果独立写入；remaining使用seq_cst原子RMW链发布。batch32将本worker完成数暂存，但进入idle/wait前必须flush，避免所有worker都持有未发布完成数而无法结束。最后完成者在状态锁下设置finished并通知，控制线程还等待所有worker返回本epoch。')
    p('异常记录首个exception，停止继续开始新任务，等待已开始工作退出后向调用者抛出；线程池有重复epoch、异常恢复、关闭和并发提交拒绝检查。固定任务不能等待其他任务或在池内阻塞提交。析构通知停止并join，不把volatile当同步。')
    p('扩展验收：tests/register_reverse.cpp在新文件注册test_reverse；只链接进worksteal_extension并复用同一ws_core。新增策略不要求修改旧策略实现或核心运行时；配置未知键、非法数值及CPU请求在运行前拒绝。当前不提供恶意插件隔离，也没有对任意第三方Partition逐项作防御性验证。')
    page()
    h('2. 工作量、核验与实验方法')
    p('compute_uniform按seed/元素ID生成输入，每个元素固定K次uint64混合递推。compute_skewed前N/8元素为9K，其余K；改变grain只改变分组，改变布局只重排同一任务集合。相同输入和迭代次数的所有条件最终输出必须一致；不减少mix、不删元素、不复用核验结果。')
    p('memory_reuse按固定元素数据块执行带串行依赖的混合访问；数据home不等于缓存实际驻留。预读由指定home执行，单独计时。它不是已经证明达到DRAM带宽饱和的STREAM类测试。')
    table(['量','定义与用途'], [
        ['epoch_seconds','线程池准备好后的统一释放到控制线程确认完成；含调度、同步、计算及唤醒'],
        ['end_to_end_seconds','应用内部初始化、身份散列、分发、执行、完整核验及关闭的总墙钟'],
        ['elapsed_process_seconds','采集器看到的进程墙钟；另含启动和最终序列化等'],
        ['identity / output FNV','校验输入、成本、任务、初始队列及输出身份；不取代逐元素参考比较'],
        ['diagnostic','额外逐任务计数、执行者和worker成本；与正式timing进程分开']])
    p('正式实验先冻结输入、候选、构建、执行顺序、数量、门槛和停止条件；诊断、预热和正式计时有独立run_id。采用全部成功样本的中位数，保存min/max、IQR或配对原值；不按观察结果删慢样本。先筛选再用预定新输入确认，确认失败不改选第二名。各轮门槛不同，均为工程规则而非显著性检验。')
    p('小规模由独立Python uint64参考重算输出与FNV；应用每次完整标量重算所有元素。并行核验使用独立参考计算和固定归并，输出散列仍按顺序生成。诊断要求exact_once；从最终task_executor重建任务/元素/成本，不能从最终执行者虚构完整迁移路径。')
    p('资源门禁检查Windows负载和WSL已知冲突任务，失败停止并封存；不停止用户其他任务。本机非独占，短epoch仍可能受系统调度与频率影响。门禁通过不证明整个主机在物理上独占。')
    page()
    h('3. 均匀任务：粒度与框架开销')
    p('第一轮W01使用固定N=262144、K=1024，比1与4个逻辑worker，grain为1/64/4096。图为每条件3次正式计时的中位数；没有从这三个点宣称找到全局最优。源：results/study-summary.json，W00_W01批次。')
    image('w01-overhead')
    table(['grain','static ms','central ms','off ms','on ms'], [[str(g)]+[
        f"{next(x for x in first['groups'] if x['experiment']=='W00_W01' and x['condition']==f'{m}-p4-g{g}')['epoch_seconds']['median']*1000:.2f}"
        for m in ('static','central','off','on')] for g in (1,64,4096)])
    p('grain减小会同时增加任务描述符、锁访问、完成计数发布和潜在输出假共享；grain增大又会降低可用并行度。曲线是这些因素的合并表现，不能把时间差全部归给deque锁，也不能用单线程/多线程比值证明物理核扩展效率。')
    p('CS149联系：任务划分决定可用并行度，调度决定如何分配现有任务。理想同速处理器上max(W/p,Cmax)有助于理解不可分任务的限制，但mix成本单位不是本机秒数，不把它当成异构或受干扰执行者上的实测时间下界。')
    p('早期p4标量策略筛选中的随机victim、退避和half没有通过两输入采用门槛。后续运行时、内核与线程数变化后需要新的冻结实验，不能把旧负结果提升成“所有版本都不会受益”。')
    page()
    h('4. 偏斜任务：均衡净收益与粗任务限制')
    table(['第一轮布局','off ms','on ms','off/on'], [[l,
        f"{claims['W02_'+l]['off_seconds']*1000:.2f}", f"{claims['W02_'+l]['on_seconds']*1000:.2f}",
        f"{claims['W02_'+l]['speedup_off_over_on']:.3f}"] for l in ('concentrated','spread','shuffled')])
    p('第一轮集中布局中off/on约2.428，分散和打乱布局接近1。独立诊断观察到实际迁移及worker成本分布变化；诊断未插入正式计时，不用于逐项扣除纯均衡时间。第一轮和后续轮次使用不同构建及参数，不混成重复。')
    image('v13-boundary')
    p('第十三轮在同一优化二进制、p16、K256下，用两个新输入、每条件5对off/on复核。集中布局grain8/256两个输入均5/5对胜出；粗grain16384只有4/6个任务，最大任务占总mix成本62.5%/58.33%，窃取也无法把任务内部拆开，因此没有稳定收益。源：stealing-boundary审计及全部60对原件。')
    p('粗粒度时两种布局的实际初始队列相同，不能作为两份独立场景证据；图上对应点仍是分别保留的计时组，不将其差异归因于布局。')
    p('分散布局初始每worker成本单位完全相等，允许窃取仍有epoch收益。这不证明某类物理核更快：相等工作单位不保证相等运行时间。本轮无独立核速度校准、稳定物理映射或PMU，不能指定P/E核或缓存为原因。app收益比epoch小且有方向不一致的条件。')
    page()
    h('5. 局部性：覆盖尺度与因果边界')
    p('硬件来源：i9-13900HX；CPUID leaf4与Windows容量报告均支持36 MiB LLC尺度。WSL1可验证请求的单CPU逻辑掩码，但CPUID APIC映射未随掩码稳定对应，无法证明执行者物理驻留或共享缓存域；没有可用PMU测量证据。')
    table(['每任务工作集','相对36 MiB LLC','受控foreign/home：方向0','方向1'], [[
        size, ratio, f"{claims['W03a_'+label+'_home0']['foreign_over_home']:.3f}",
        f"{claims['W03a_'+label+'_home1']['foreign_over_home']:.3f}"]
        for label,size,ratio in (('small','512 KiB','1/72'),('middle','4.5 MiB','1/8'),('large','288 MiB','8'))])
    p('表为固定工作集、固定访问遍数和预读步骤下，两个home方向的受控执行者变化。大工作集和中间工作集两个方向没有一致趋势；数值是墙钟时间关联，不是cache miss次数、DRAM流量或迁移缓存的纯代价。')
    table(['动态布局','512 KiB off/on','4.5 MiB off/on','288 MiB off/on'], [[layout]+[
        f"{claims['W03_'+size+'_'+layout]['speedup_off_over_on']:.3f}" for size in ('small','middle','large')]
        for layout in ('policy','concentrated')])
    p('六个动态开启窃取诊断均未发生成功偷取；home不匹配可能只是初始放置造成，不能当作偷取。实验完成了题目要求的远小于/远大于LLC尺度覆盖，但没有得到动态窃取导致缓存损失的证据。局部性窗口接近零是允许的结果，不能据此宣称所有工作负载都不存在局部性代价。')
    p('若继续研究，需要能核实物理驻留的Linux环境，并冻结重复访问、预读、实际迁移与对照。换环境会形成新实验，不与本机原始样本混合。')
    page()
    h('6. 已确认优化：分别解释作用阶段')
    p('第二轮同时比较编译/内核路径并联合选择线程数和grain；下面是相对该轮参数基线的两新输入结果。倍数包含多种变化，不是纯窃取策略收益。全部5对胜出仍只支持该轮候选和输入范围。')
    table(['类别','seed','epoch基线/候选','app基线/候选','胜对'], opt_rows)
    p('机制：batch32摊薄全局完成原子更新；scratch复用每worker转移暂存；LTO允许编译器跨翻译单元优化；compute_lanes8交错八个独立元素的依赖链，以增加指令级并行，不减少每个元素迭代数，也不自动等同SIMD。第三轮仅轻任务进一步通过联合配置确认，重计算保留此前选择。')
    table(['第八轮输入','epoch scalar→lanes4 ms','epoch比','app比','胜对'], [[
        str(g['seed']),f"{g['medians']['base']['epoch']*1000:.4f}→{g['medians']['candidate']['epoch']*1000:.4f}",
        f"{g['epoch_speedup']:.3f}",f"{g['app_speedup']:.3f}",f"{g['wins']}/7"] for g in memory['heldout']])
    p('memory_lanes4将四个独立元素递推交错，两个输入epoch均7/7胜出并满足至少10%改善及app护栏。它作用于任务内核；数据生成、原FNV、完整标量参考核验均保留。新推荐只对应第八轮原构建。')
    p('第四/五轮并行化完整参考核验，改善应用端到端但不改变被测Pool任务；第五轮三个类别在两个新输入各7/7对app胜出。不能把这一收益归给工作窃取，也不能将它与第二/八轮比值相乘得到一个未实测的总倍数。')
    page()
    h('7. 负结果同样约束方案选择')
    table(['轮次','研究问题','实际决定'], [
        ['6','并行初始化填充','确认不足，保留initialization_workers=1'],
        ['7','overwrite省去预清零','第二输入仅5/7胜，保留zeroed'],
        ['9','memory p×grain参数','没有≥5%筛选候选，按协议停止'],
        ['10','生成时分块执行同一FNV','阶段费用移动，app未稳定改善，保留separate'],
        ['11','四路独立word生成','两输入app仅4/7、2/7胜，保留fill1'],
        ['12','分配/填充/FNV成本探针','仅诊断，不据探针推翻应用负结果'],
        ['14','single对照cap4/16/64','筛选选cap4，但两个新输入确认失败']])
    p('第十二轮独立noinline探针：zeroed 40/64 MiB时，填充中位数约3.25/5.32ms，分配清零约28.77/47.26ms，完整FNV约36.08/56.91ms。overwrite将大量minor faults移到填充；它们不是纯缺页成本，也不是应用可直接获得的加速。原FNV有串行依赖，不能简单并行部分散列后拼接成同一语义。')
    table(['第十四轮集中输入','epoch single→cap4 ms','胜对','app single→cap4 ms'], [[
        str(g['seed']), f"{g['medians']['base']['epoch']*1000:.4f}→{g['medians']['candidate']['epoch']*1000:.4f}",
        f"{g['epoch_wins']}/7",f"{g['medians']['base']['app']*1000:.4f}→{g['medians']['candidate']['app']*1000:.4f}"]
        for g in batch['confirmation']['groups'] if g['layout']=='concentrated'])
    p('cap4筛选中epoch下降约22.7%，确认中却没有稳定改善；第二输入app中位数上升8.01%。诊断虽显示steals更少、成本单位分配更均衡，但描述符搬运更多。少steals不等于少总费用，最终执行者也不能还原反复搬运路径。保留single，不因确认失败补测第二名。')
    page()
    h('8. 第十五轮：空闲退避的独立对照')
    p('同一原Release、p16、K256、round_robin与single固定，只比较immediate和已有bounded_backoff。前者失败后yield；后者连续失败第32次起请求固定50微秒的条件变量等待。成功取得任务会清零失败计数。本轮未测实际睡眠时长、上下文切换或功耗。')
    table(['seed / N','grain','布局','epoch base→backoff ms','胜对','app比','通过'], [[
        f"{g['seed']} / {g['elements']}", str(g['grain']),g['layout'],
        f"{g['medians']['base']['epoch']*1000:.4f}→{g['medians']['candidate']['epoch']*1000:.4f}",
        f"{g['epoch_wins']}/7",f"{g['app_speedup']:.3f}",str(g['pass'])] for g in idle['confirmation']['groups']],
        [88,35,77,110,35,47,40])
    p(f"恢复批次{idle['batch']}，{idle['processes']}进程/{idle['timing_samples']}正式计时，accepted={idle['accepted']}。主目标为两输入g8集中布局各至少6/7胜且中位数≤95%；其余epoch≤110%，全部app≤105%。门槛在采样前冻结，不是显著性保证。")
    p('首批因采集器身份缓存未区分grain，在第5个control后停止，0正式计时。5个应用输出分别独立复核均正确；原共享缓存重放可复现错误。保留失败原件和原冻结代码，按新协议仅修复grain缓存命名空间，在全新目录从control完整恢复；没有补齐原失败批次或混合样本。恢复协议为docs/43，原协议为docs/41。')
    p('诊断的attempts只在第一处victim锁成功后计数，busy包括两次锁失败；busy/attempts不能叫总失败率。empty和steals计数用于提出机制假设，不据计数下降单独证明正式性能改善。本轮完整配对、阶段和进程时间见idle-backoff审计及逐run原件。')
    p('采用结论：' + ('候选通过预定门槛；仅作为本轮p16输入/粒度范围的配置，不直接覆盖p32推荐。' if idle['accepted'] else '候选未通过全部门槛，保留immediate及既有推荐，不新增通用退避配置。'))
    page()
    h('9. 推荐组合、源码与构建来源')
    table(['任务','worker / grain','执行/核验选择','配置入口'], [[
        k, f"{c['workers']} / {c['policies']['partition']['grain']}",
        'memory_lanes4 / ref4' if k=='memory' else f"compute_lanes8 / ref{c['measurement'].get('reference_workers',1)}",
        'configs/memory-interleaved/memory.json' if k=='memory' else 'configs/verified/'+k+'.json']
        for k,c in cfgs.items()], [45,85,130,172])
    p('上述历史确认推荐采用round_robin victim、immediate、single和显式逻辑CPU掩码；输入与工作负载范围以各JSON及builds.json为准。memory-large.json保留第二个第八轮输入。第十四/十五轮p16细粒度研究不能直接把这些p32配置改写为“新最优”。')
    for label,b in ((k,builds[k]) for k in ('light','uniform','skewed')):
        p(f"{label} 原测量binary SHA256：{b['binary_sha256']}；source：{b['source_id']}。完整CMake参数与快照位置见configs/verified/builds.json。")
    p(f"memory 原测量binary SHA256：{memory_build['release_binary_sha256']}；source：{memory_build['measured_source_id']}。完整来源见configs/memory-interleaved/builds.json。")
    p('当前源码新增过参数和交付工具，今天重建的二进制不等于历史测量二进制。复现功能可从当前源码构建；要追溯历史数字，应使用对应冻结源码、CMake参数、编译环境和已归档二进制。不能把新source ID换填进旧run。')
    p('没有通吃所有负载的组合。对于已均衡工作或一次性很小的调用，先评估串行/静态/集中队列和总应用时间；本报告推荐是预定候选范围内经独立输入确认的选择，不是所有执行器及所有机器的全局最优证明。')
    page()
    h('10. 复现、正确性与最终交付边界')
    p('依赖：Linux、C++20工具链、CMake、Python3和nlohmann-json3-dev。Ubuntu 24.04可用apt安装build-essential cmake python3 nlohmann-json3-dev。报告生成另用report/requirements.txt；常规运行时不依赖报告库。')
    for line in ('cmake -S . -B build -DCMAKE_BUILD_TYPE=Release',
                 'cmake --build build -j2', 'ctest --test-dir build --output-on-failure',
                 './build/worksteal --list-policies', './build/worksteal --config configs/runtime/diagnostic.json'):
        p(line)
    p('优化重建必须按builds.json增加对应WS_COMPLETION_BATCH、WS_STEAL_SCRATCH、WS_ENABLE_IPO和WS_COMPUTE_LANES；仅默认Release不能复现已优化内核。IPO有CMake能力检查；未使用fast-math或march=native。')
    if reproduction:
        assert reproduction['pass']
        p(f"本次干净Linux复现已完成：{reproduction['source_file_count']}份源文件复制到新目录；默认、full与uniform三个Release构建均完成真实CTest，六个原推荐配置完整核验通过。来源、命令、日志及新binary散列在submission/reproduction/20261025/receipt.json；它们是功能复现，不是旧耗时再现，也没有新增sanitizer声明。")
    else:
        p('本次最终包干净Linux重建尚未完成；历史构建记录不冒充最终包验收，须补齐后核对本章。')
    p('并发检查覆盖空集合、单任务、少任务、多线程、重复epoch、恰好一次、输出发布、异常、恢复、退出及并发提交拒绝；独立扩展和非法CLI输入另检。第十一轮原Release、ASan/UBSan、TSan各保存2551项runtime检查与497次CLI调用记录。它们属于原构建；本轮未改C++，未新增sanitizer执行。')
    p('DevContainer配置已提供，但本机Docker登记路径下缺少程序，未发现可执行命令或服务，实建未证明。原生Linux验收不能冒充容器验收；这是本项目交付台账中的独立未完成项。')
    p(f"连续Prompt File位于submission/prompts/session-20261025-v15-preparation：从Session起点到{session['last_message_timestamp']}，{session['roles']['user']}用户消息、{session['roles']['assistant']}可见助手消息；JSON/Markdown与原始前缀SHA256均保留。不含思维链、工具内部输出或其他Session，不用摘要拼接。")
    p('附件限制：原始持久日志只有文本块，没有input_image块；最初两张临时截图原路径已不存在。导出证明可见文本的连续与保真，不能证明原始图片附件保全，未补写OCR或伪造图片。详见submission/prompts/attachment-availability-20261025.json。')
    p('官方要求提交PDF、可复现代码/环境与一个完整连续Session。交付时以候选包收据确认实际装包、解包验散列及链接检查，并核对验收台账；报告存在不等于所有提交项完成。用户对项目的掌握必须自行验证，自动检查不能代替面试。')
    page()
    h('附录：证据入口与学习资料')
    table(['范围','数据 / 解释入口'], [
        ['第一轮与W01-W03','results/study-summary.json；report/实验与策略选择报告.md'],
        ['联合实现/参数优化','optimization/results/optimization-summary.json；docs/15'],
        ['轻任务与参考核验','refinement、verification、confirmation-retry；docs/17、19、22'],
        ['初始化与内存内核','initialization、allocation、memory-kernel；docs/24、26、28'],
        ['负结果与成本诊断','memory-tuning、blocked-identity、fill-interleaved、init-cost；docs/30、32、34、36'],
        ['优化后机制与批量','stealing-boundary、batch-migration；docs/38、40'],
        ['退避与恢复原件','idle-backoff、idle-backoff-collector-failure；docs/41、43'],
        ['最终验收','docs/42-最终交付验收台账.md；submission/README.md'],
        ['本报告可复算输入','report/final/input-data.json；figures/及tools/final_report.py']])
    p('每轮目录保存frozen-plan、原始result/config/metadata/stdout/stderr、环境、校验和、来源快照及Linux/Windows审计。报告内表格从结构化数据生成，并再次读取对应原始run核对中位数、完整核验和散列；具体source哈希与已核对run列表保存在input-data.json。')
    p('原始数据在Linux与Windows镜像分别验散列，但目前位于同一物理盘，不等于独立故障备份。不得擅自外传原始数据；最终提交包不应含凭据或相邻项目。')
    p('官方题面：github.com/LZUOSS/LZUHPC，立项核对commit 33dad592cd74d8cf36ae7921a29c0e8393034a70；本地原文及版本说明见reference/README.md。')
    p('社区依据：oneTBB文档How Task Scheduler Works、Controlling Chunking、Bandwidth and Cache Affinity；Google Benchmark User Guide与Random Interleaving；Blumofe的Cilk调度说明。精确链接与核查范围在docs/11。借鉴双端规则和实验方法，不把Cilk递归依赖模型的理论保证套到本项目flat带锁队列。')
    p('CS149对应：工作量/跨度与可用并行度解释粗粒度上限；任务划分和动态均衡解释尾部；锁/原子/启动成本解释细任务；依赖链与指令级并行解释lanes；缓存容量和访问复用解释局部性窗口；Amdahl定律提醒只优化epoch不一定大幅改善一次性应用总时间。')

    manifest = {'created': lab.now(), 'narrative_source_snapshot':lab.snapshot(),
                'source_sha256': sources, 'verified_raw_runs': verified,
                'idle_backoff_accepted': idle['accepted'], 'boundary_groups': boundary['groups'],
                'memory_groups': memory['heldout'], 'batch_confirmation': batch['confirmation'],
                'idle_confirmation': idle['confirmation'], 'optimization_table': opt_rows,
                'native_reproduction_pass': bool(reproduction and reproduction['pass']), 'container_built': False,
                'generator_sha256': lab.digest(pathlib.Path(__file__))}
    (out/'input-data.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    md = []
    for kind, value in sections:
        if kind == 'h': md += ['# '+value, '']
        elif kind == 'p': md += [value, '']
        elif kind == 'image': md += ['![数据图](figures/'+value+'.png)', '']
        elif kind == 'table':
            headers, rows, _ = value
            md += ['|'+'|'.join(headers)+'|', '|'+'|'.join(['---']*len(headers))+'|']
            md += ['|'+'|'.join(str(x) for x in row)+'|' for row in rows]
            md += ['']
    (out/'技术报告.md').write_text('\n'.join(md)+'\n', encoding='utf-8')
    pdfmetrics.registerFont(TTFont('FinalCJK', a.font))
    normal = ParagraphStyle('body', fontName='FinalCJK', fontSize=9.2, leading=14,
                            wordWrap='CJK', spaceAfter=8)
    heading = ParagraphStyle('heading', parent=normal, fontSize=16, leading=22, spaceAfter=16)
    cell = ParagraphStyle('cell', parent=normal, fontSize=8, leading=11, spaceAfter=0)
    pdf = root/'output/pdf/Mini-WorkSteal-最终技术报告-20261025.pdf'
    pdf.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(pdf), pagesize=A4, rightMargin=42, leftMargin=42, topMargin=45, bottomMargin=44,
                            title='Mini WorkSteal - 可组合策略与可解释性能', author='Mini WorkSteal project')
    width = A4[0]-84
    story = []
    for kind, value in sections:
        if kind == 'h': story.append(Paragraph(html.escape(value), heading))
        elif kind == 'p': story.append(Paragraph(html.escape(value), normal))
        elif kind == 'page': story.append(PageBreak())
        elif kind == 'image':
            im = Image(str(figures/(value+'.png')))
            im.drawHeight *= width/im.drawWidth
            im.drawWidth = width
            story += [im, Spacer(1, 8)]
        elif kind == 'table':
            headers, rows, widths = value
            widths = [w*width/sum(widths) for w in widths] if widths else [width/len(headers)]*len(headers)
            t = Table([[Paragraph(html.escape(str(x)), cell) for x in row] for row in [headers]+rows],
                      colWidths=widths, repeatRows=1, hAlign='LEFT')
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7edf4')),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f7f9fb')]),
                ('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#c8d1dc')),
                ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
            story += [t, Spacer(1, 12)]
    def footer(canvas, document):
        canvas.setFont('FinalCJK', 8)
        canvas.setFillColor(colors.HexColor('#596579'))
        canvas.drawString(42, 24, 'Mini WorkSteal | 2026-10-25 | Linux / WSL1')
        canvas.drawRightString(A4[0]-42, 24, str(document.page))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    import fitz
    render = root/'tmp/pdfs/final-20261025'
    render.mkdir(parents=True, exist_ok=True)
    document = fitz.open(pdf)
    pages = []
    for i, pg in enumerate(document):
        text = pg.get_text()
        assert len(text.strip()) > 60
        pg.get_pixmap(matrix=fitz.Matrix(1.4,1.4), alpha=False).save(render/f'page-{i+1:02}.png')
        pages.append({'page': i+1, 'text_characters': len(text), 'text_bounds_checked': all(
            b[0] >= 0 and b[1] >= 0 and b[2] <= pg.rect.width+1 and b[3] <= pg.rect.height+1 for b in pg.get_text('blocks'))})
    result = {'created':lab.now(), 'pdf_sha256':lab.digest(pdf), 'pages':pages,
              'raw_runs_verified':len(verified), 'sources_verified':len(sources),
              'manual_visual_review': 'pending; inspect rendered pages before delivery',
              'input_sha256':lab.digest(out/'input-data.json'), 'generator_sha256':lab.digest(pathlib.Path(__file__))}
    (root/'output/pdf/final-20261025-render-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'pdf':str(pdf),'pages':len(pages),'verified_raw_runs':len(verified),'sources':len(sources)},ensure_ascii=False))


if __name__ == '__main__':
    main()
