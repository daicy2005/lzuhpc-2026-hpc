#!/usr/bin/env python3
"""Create the study report from audited JSON; no benchmark numbers are handwritten."""
import argparse,copy,hashlib,json,pathlib,statistics,sys
from xml.sax.saxutils import escape

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);ap.add_argument('--font',default='C:/Windows/Fonts/simhei.ttf');a=ap.parse_args();root=pathlib.Path(a.root)
    summary=json.loads((root/'results/study-summary.json').read_text(encoding='utf-8'));assert summary['complete']
    dest=root/'report';figs=dest/'figures';figs.mkdir(parents=True,exist_ok=True)
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'white','axes.labelcolor':'#233547','text.color':'#233547','savefig.facecolor':'white'})
    colors=['#267A9C','#D08745','#426B44','#855C92']
    groups={(g['experiment'],g['condition']):g for g in summary['groups']}
    claims={c['id']:c for c in summary['claims']}
    def group(exp,cid):return groups[(exp,cid)]
    def median(exp,cid):return group(exp,cid)['epoch_seconds']['median']
    def save(fig,name):
        fig.savefig(figs/(name+'.png'),dpi=200,bbox_inches='tight');fig.savefig(figs/(name+'.svg'),bbox_inches='tight');plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(10,3.3),layout='constrained')
    for ax,p in zip(axs,(1,4)):
        for color,mode in zip(colors,('static','central','off','on')):
            gs=[group('W00_W01',f'{mode}-p{p}-g{g}') for g in (1,64,4096)]
            med=np.array([g['epoch_seconds']['median']*1000 for g in gs]);lo=np.array([min(g['epoch_seconds']['values'])*1000 for g in gs]);hi=np.array([max(g['epoch_seconds']['values'])*1000 for g in gs])
            ax.plot((1,64,4096),med,'o-',label=mode,color=color);ax.fill_between((1,64,4096),lo,hi,color=color,alpha=.12)
        if p==1:ax.axhline(median('W00_W01','S0')*1000,color='#667',ls=':',label='serial')
        ax.set_xscale('log');ax.set_xlabel('grain (elements/task)');ax.set_ylabel('epoch (ms)');ax.set_title(f'{p} worker(s); n=3, shaded min/max');ax.grid(alpha=.15)
    axs[1].legend(ncol=2,fontsize=8);save(fig,'w01-grain')
    fig,ax=plt.subplots(figsize=(9.5,3.2),layout='constrained');xs=np.arange(3);width=.18
    for i,(color,mode) in enumerate(zip(colors,('static','central','off','on'))):
        vals=[median('W02',f'{layout}-{mode}')*1000 for layout in ('concentrated','spread','shuffled')]
        ax.bar(xs+(i-1.5)*width,vals,width,color=color,label=mode)
    ax.set_xticks(xs,['concentrated','spread','shuffled']);ax.set_ylabel('median epoch (ms), n=3');ax.legend(ncol=4);save(fig,'w02-balance')
    fig,ax=plt.subplots(figsize=(9.5,3),layout='constrained');xs=np.arange(3)
    for home,color,offset in ((0,colors[0],-.16),(1,colors[1],.16)):
        vals=[claims[f'W03a_{scale}_home{home}']['foreign_over_home'] for scale in ('small','middle','large')]
        ax.bar(xs+offset,vals,.3,label=f'home worker {home}',color=color)
    ax.axhline(1,color='#667',ls=':');ax.set_xticks(xs,['512 KiB','4.5 MiB','288 MiB']);ax.set_ylabel('foreign / home median time');ax.set_ylim(0,max(1.3,max(c.get('foreign_over_home',0) for c in claims.values())*1.15));ax.legend();ax.set_title('Controlled executor changes; n=3; physical residency unproven');save(fig,'w03-controlled')
    fig,axs=plt.subplots(1,3,figsize=(11,4),layout='constrained')
    for ax,kind in zip(axs,('uniform','skewed','memory')):
        gs=sorted((g for g in summary['groups'] if g['experiment']=='W04' and g['condition'].startswith(kind+'--')),key=lambda g:g['condition'])
        base=median('W04',kind+'--base');labels=[g['condition'].split('--')[1] for g in gs];vals=[g['epoch_seconds']['median']/base for g in gs]
        ax.barh(labels,vals,color=[colors[0] if label=='base' else '#AEC8D1' for label in labels]);ax.axvline(1,color='#667',ls=':');ax.set_xlabel('median time / base (lower better)');ax.set_title(kind+'; n=3')
    save(fig,'w04-policies')
    # Every held-out median and paired win count is also present in the text/table.
    fig,ax=plt.subplots(figsize=(9.5,3.2),layout='constrained');labels=[];ratios=[];wins=[]
    for kind,s in summary['selection'].items():
        for case in s['heldout']:labels.append(kind+'\ns'+str(case['seed']));ratios.append(case['base_over_candidate']);wins.append(case['wins_of_5'])
    ax.bar(np.arange(len(labels)),ratios,color=colors[0]);ax.axhline(1/.95,color=colors[1],ls='--',label='>=5% lower time threshold');ax.axhline(1,color='#667',ls=':')
    for i,(ratio,win) in enumerate(zip(ratios,wins)):ax.text(i,ratio+.015,f'{win}/5 wins',ha='center',fontsize=8)
    ax.set_xticks(range(len(labels)),labels);ax.set_ylim(0,max(1.2,max(ratios)*1.15));ax.set_ylabel('base median / candidate median');ax.legend(fontsize=8);save(fig,'w05-heldout')
    (figs/'input-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    # One common structure feeds Markdown and PDF to prevent diverging claims.
    sections=[]
    def p(text):sections.append(('p',text))
    def h(text):sections.append(('h',text))
    def table(headers,rows,widths=None):sections.append(('table',(headers,rows,widths)))
    def image(name):sections.append(('image',name))
    h('结论与推荐')
    p('本研究在固定独立任务模型中实现并评测工作窃取。结论限定于本机 i9-13900HX / Ubuntu 24.04 / WSL1 环境及预先列出的候选，不宣称全局最优或四物理核扩展。')
    rows=[]
    for kind,s in summary['selection'].items():rows.append([kind,s['screening_candidate'],s['selected'],'两输入均过门槛' if s['selected']!='base' else '候选未同时过门槛，保留默认'])
    table(['任务类','筛选最快候选','最终组合','决定依据'],rows)
    p('选择范围仅为预先列出的开启窃取策略组合。static、central 与关闭窃取是机制对照，未进入 W04 的最终策略候选集合；因此 base 不代表全部执行器中最快。均匀输入的关闭窃取与 base 接近或略快，实际系统应先看负载是否需要动态均衡。')
    p('base = fixed_grain（compute: 64 元素/task；memory: 1 数据块/task）+ round_robin victim + immediate + single 描述符迁移 + explicit 逻辑 CPU 掩码 [0,1,2,3] + round_robin 初始放置。偏斜机制组另外冻结 concentrated 布局。若最终选择其他名字，其完整可执行组合见 configs/recommended/，不是只记录一个简称。')
    c=claims['W02_concentrated'];p(f"最清楚的均衡收益来自集中放置的偏斜输入：关闭窃取 {c['off_seconds']*1000:.2f} ms，开启窃取 {c['on_seconds']*1000:.2f} ms，关闭/开启中位数比值 {c['speedup_off_over_on']:.3f}。这是允许窃取的净收益，包含调度与同步费用，不能称纯均衡时间。")
    h('目标、模型与比较口径')
    p('首要问题：固定总逻辑工作时，粒度与初始不均衡如何决定窃取是否值得？S0 直接串行，S1 固定归属的本地 mutex/deque，S2 集中队列；S3-off/on 使用同二进制、同队列锁、同本地 LIFO、同完成协议，只改变窃取许可。S1 同样存在本地队列锁开销。固定任务集合没有递归 spawn；不直接套用 Cilk 的工作/跨度性能保证。')
    p('compute 使用 uint64 定义回绕的输入依赖混合，每元素 cost 次；输入按 seed/ElementId 固定。W02 前 N/8 元素成本 9K，其余 K，改变布局不改变元素、成本集合或结果。每次逐元素与参考核验；另用独立 Python 参考核验已知小向量。')
    p('主要时钟为 steady_clock：线程池准备后，控制线程持状态锁记 t0、发布 epoch；确认全部完成记 t1。epoch 包含调度、同步、任务计算和主线程唤醒，排除创建线程和分发；setup/dispatch/端到端另存。端到端含输入生成、核验和关闭，绝不把 epoch 收益冒充一次性调用全收益。')
    p('筛选每配置 1 独立进程预热 + 3 计时，确认每输入 1 预热 + 5 计时。冻结实际顺序并交错，慢的成功记录全部保留。统计为 n、中位数、min/max、IQR（线性插值）；预热、诊断与失败均不进入计时组。5% 与 4/5 是工程替换门槛，不是显著性检验。')
    h('运行时与正确性')
    table(['部分','实现与证据'],[
      ['模块边界','公共 policy/runtime/workload 接口，核心不识别策略字符串；新增 test_reverse 注册文件只链接到扩展入口，复用核心库。'],
      ['队列','每 worker 一把 mutex；本地后端取，thief 前端取；锁外决定迁移数量，锁内裁剪；不同时持两把队列锁。'],
      ['完成与退出','冻结任务总数，seq_cst remaining RMW 发布；最后完成者在状态锁下通知。等待所有 worker 返回后可复用；异常停止后续开始、等待正在执行任务并抛出。'],
      ['检查','各通过版本 runtime_checks 1204 项、CLI/独立参考/非法配置/注册扩展/受控预读检查；Release、ASan+UBSan、TSan 各保存实际 validation.json。'],
      ['已修正问题','早期单文件试跑计时含建线程，不纳入正式成绩；v2 新增检查检出 local-phase 标记不一致，保留失败记录，修正为 v3 后再测。']])
    p('检查不是形式证明：固定随机短扰动与多个规模能覆盖常见竞争，但不能保证遍历全部调度。TSan 通过也不等于证明不存在竞争。诊断逐任务计数与详细计时单独运行，不能从未插桩的时间逐项相减。')
    p('诊断口径：attempts 仅在首次 victim 快照锁成功后递增，busy 可来自第一次或第二次 try_lock；不能用 busy/attempts 表示全部尝试的锁忙率。capped_half 按快照长度取半后以当前可用数量裁剪，可能超过当前队列的一半。未来新增 partition 必须提供合法区间；当前布局构造前未逐项验证区间，不把错误插件的隔离能力列为已验收。')
    h('本机条件与硬件边界')
    p('32 个允许逻辑 CPU，正式预试验使用前 4 个掩码。WSL1 允许读取 singleton mask，但 CPUID x2APIC 不随掩码稳定对应；因此未证明物理驻留，也未证明 P/E 或 SMT 对照。主机非独占，开跑前未见本项目/光追冲突；后台噪声与频率变化仍可能影响结果。')
    p('CPUID leaf4 报告 LLC 37,748,736 字节（36 MiB），Windows CIM L3=36,864 KB 交叉吻合。它支持尺度覆盖；不能证明具体 worker 的缓存内容与稳定共享域。perf/PMU 未具备可用证据，缓存 miss 与 DRAM 流量不冒充已测。')
    h('W01：粒度与框架费用')
    first=summary['batches']['W00_W01'];p(f"批次 {first['id']}：127 个进程，包含 20 个集成检查、3 次有界校准、100 个预热/计时及 4 个诊断。正式 K=1024、N=262144，串行中位数 {median('W00_W01','S0')*1000:.2f} ms。只比较 1 与 4 worker，不定位饱和点。")
    table(['grain','static ms','central ms','off ms','on ms'],[[str(g)]+[f"{median('W00_W01',f'{m}-p4-g{g}')*1000:.2f}" for m in ('static','central','off','on')] for g in (1,64,4096)])
    image('w01-grain');p('曲线说明这个探针范围内多数差异较小，未识别完整最优粒度窗口。grain 变化同时改变描述符数量、锁/完成原子次数、输出假共享等，不能把全部差异单独归因于窃取锁。串行比值不是同执行器并行效率。')
    h('W02：初始布局与均衡收益')
    table(['布局','off ms','on ms','off/on'],[[layout,f"{claims['W02_'+layout]['off_seconds']*1000:.2f}",f"{claims['W02_'+layout]['on_seconds']*1000:.2f}",f"{claims['W02_'+layout]['speedup_off_over_on']:.3f}"] for layout in ('concentrated','spread','shuffled')])
    image('w02-balance');p('各布局输入、成本表、总成本和参考输出相同；同布局 off/on 队列散列相同。跨布局也改变执行顺序，因此只能称初始布局影响。集中布局收益明显，spread 已较均衡，额外窃取不一定划算。集中队列同样能均衡，不能把动态调度收益说成工作窃取独有。')
    if 'W02-diagnostics-v3' in summary['batches']:
        p('追加 v3 诊断保存每 worker 实际成本单位、task executor 与尾部时刻。它与 v1 正式计时分开归档，不混入中位数或做时间分解。下表每行只是一份带插桩诊断，用于确认确实发生工作迁移与尾部变化。')
        b=summary['batches']['W02-diagnostics-v3'];records=json.loads((root/'runs'/b['id']/'records.json').read_text(encoding='utf-8'));rows=[]
        for r in records:
            epoch=json.loads((root/'runs'/b['id']/r['run_id']/'result.json').read_text(encoding='utf-8'))['epochs'][0]
            costs=epoch['execution']['worker_cost_units'];ws=epoch['worker_stats'];finishes=[w['last_finish_seconds'] for w in ws]
            rows.append([r['condition'], ' / '.join(f'{c/1e6:.1f}' for c in costs),str(sum(w['steals'] for w in ws)),f'{(max(finishes)-min(finishes))*1000:.2f}'])
        table(['诊断条件','worker 成本（百万 mix）','成功偷取','结束跨度 ms'],rows,[120,195,70,95])
    h('W03：局部性尺度与受控执行者变化')
    table(['每任务工作集','相对 LLC','并行任务数','总数据','访问遍数'],[['512 KiB','1/72','64','32 MiB','16'],['4.5 MiB','1/8','16','72 MiB','8'],['288 MiB','8','4','1152 MiB','2']])
    p('每个规模内部固定数据、任务划分、home、布局、预读和访问遍数，不跨规模相减当迁移损失。独立进程内先由 home worker 本地预读，关闭预读阶段窃取；正式访问完整重新计算，之后核验。两方向受控组分别安排 home0/执行0或1、home1/执行1或0。')
    p('memory_reuse 每次数据混合依赖前一步 x，是带串行数据依赖的访问内核；它不是已证明达到带宽饱和的 STREAM 类基准。大工作集耗时可能同时受计算、依赖链与内存层次影响。')
    table(['规模','home0：foreign/home','home1：foreign/home'],[[scale,f"{claims[f'W03a_{scale}_home0']['foreign_over_home']:.3f}",f"{claims[f'W03a_{scale}_home1']['foreign_over_home']:.3f}"] for scale in ('small','middle','large')])
    image('w03-controlled');p('没有一致方向的受控差异，且物理驻留未证明；不能宣布局部性窗口已被证伪，或精确量化了缓存 miss 损失。动态组还需查看实际偷取：没有 steal 的运行不给出迁移效果证据。容量两端已覆盖，因果解释强度仍有限。')
    b=summary['batches']['W03'];records=json.loads((root/'runs'/b['id']/'records.json').read_text(encoding='utf-8'));rows=[]
    for r in records:
        if r['purpose']!='diagnostic' or not r['condition'].endswith('-on'):continue
        e=json.loads((root/'runs'/b['id']/r['run_id']/'result.json').read_text(encoding='utf-8'))['epochs'][0]
        rows.append([r['condition'],str(sum(w['steals'] for w in e['worker_stats'])),str(e['execution']['element_home_mismatches'])])
    table(['动态诊断组（单次）','成功偷取次数','执行者不同于 home 的块数'],rows,[220,100,160])
    p('上述六个开启窃取动态诊断的成功偷取数全部为 0，不能提供动态窃取造成局部性损失的证据。home 不匹配还可能来自初始放置，不等同于实际偷取。受控 executor 变化仍可描述，但受 WSL1 物理映射限制，不能据此断言缓存因果。')
    h('W04：有限策略组合筛选')
    p('compute 每类 8 个、memory 7 个候选：默认、random victim、bounded_backoff、capped_half、unbound、balanced_chunks（仅 compute），以及 random+half、backoff+half。memory 固定 partition/home，避免更改预处理归属。不是所有策略的笛卡尔积，未测组合不能称更差。')
    image('w04-policies')
    h('W05：留出输入确认与最终选择')
    p('筛选前已冻结 seed=73/991；compute N=196608/327680，memory 元素数 48/80，其余核与策略含义保持一致。候选与默认五对交错，AB/BA 轮换；关闭窃取作为额外解释性组，不伪装成严格配对的同时测量。')
    table(['类 / seed','候选','默认 ms','候选 ms','更快对数','通过'],[[f"{kind}/{c['seed']}",s['screening_candidate'],f"{c['base_median_seconds']*1000:.3f}",f"{c['candidate_median_seconds']*1000:.3f}",f"{c['wins_of_5']}/5",'是' if c['accepted'] else '否'] for kind,s in summary['selection'].items() for c in s['heldout']])
    image('w05-heldout');p('筛选阶段的最小中位数不自动升级为最终最优。未同时通过两个输入的门槛，则保留较简单默认实现；这表示现有证据不足以支持额外复杂性，不表示证明候选在所有任务上都更慢。内存很小的短 epoch 更容易受唤醒与背景变化影响。')
    p('留出计时有明显波动，所有较慢成功记录均保留。memory/991 单输入通过，另一个输入失败；skewed/991 虽然中位数改善，但仅 3/5 对胜出。没有改门槛、改选第二名或追加到通过。每组 min/max/IQR 与五个原始值见统计 JSON，5 次重复不足以保证很小的差异可跨时段重现。')
    h('复现、原始证据与限制')
    table(['实验','批次 ID','进程数'],[[exp,b['id'],str(b['completion']['processes'])] for exp,b in summary['batches'].items()])
    timing_count=sum(g['epoch_seconds']['n'] for g in summary['groups'])
    p(f"本报告覆盖 {summary['total_formal_processes']} 个研究进程，其中 {timing_count} 个为正式计时，其余为开发检查、校准、预热、诊断与推荐配置验收。results/study-summary.json 保留全部组的 n/med/min/max/IQR、原始值及 run_paths；results/runs.jsonl 保留逐进程索引。已核验冻结顺序、重复编号、实际配置、条件身份与逐文件散列。早期 smoke 与 v2 失败单独保留，不纳入排名。")
    audit=json.loads((root/'results/closeout-audit.json').read_text(encoding='utf-8'))
    p(f"归档审计通过 {audit['verified_manifests']} 份清单、{audit['file_hash_checks']} 次文件散列核验；当前生产 C++、接口、测试与 CMake 与通过验证的 v3 一致。configs/recommended/ 的三个完整配置已在 v3 各真实运行一次并通过输出核验；这些验收进程不参与选择。扩展注册与 sanitizer/失败记录索引见 results/closeout-audit.json。")
    p('构建：cmake -S . -B build -DCMAKE_BUILD_TYPE=Release；cmake --build build -j2；ctest --test-dir build --output-on-failure。实际编译参数、工具版本、二进制 SHA256 与源码快照见 snapshots/。W01/W02 使用 v1，W03/W04/W05 使用 v3，各比较在同一二进制内完成，不跨版本拼接重复。')
    p('生成：python tools/analyze.py --root . --out results；再按 report/requirements.txt 安装报告依赖，运行 tools/make_report.py --root . --font <中文 TrueType 字体路径>。图表 PNG/SVG、输入摘要与生成脚本都保留。Linux 原件和 Windows 导出逐文件核对 SHA256；同一物理盘的两份不等于独立故障备份。')
    p('适用范围：固定独立任务、小型带锁运行时、本机 WSL1 与有限探针。没有递归 spawn、无锁队列、GPU 或分布式执行，也未证明裸机/混合核/NUMA 泛化。最终建议是该范围内有证据支持的实现选择，不能承诺通用最优或固定加速比。')
    h('社区与理论参考')
    for title,url in [
      ('oneTBB - How Task Scheduler Works','https://github.com/uxlfoundation/oneTBB/blob/master/doc/main/tbb_userguide/How_Task_Scheduler_Works.rst'),
      ('oneTBB - Controlling Chunking','https://github.com/uxlfoundation/oneTBB/blob/master/doc/main/tbb_userguide/Controlling_Chunking_os.rst'),
      ('oneTBB - Bandwidth and Cache Affinity','https://github.com/uxlfoundation/oneTBB/blob/master/doc/main/tbb_userguide/Bandwidth_and_Cache_Affinity_os.rst'),
      ('Google Benchmark - User Guide / Random Interleaving','https://github.com/google/benchmark/tree/main/docs'),
      ('Blumofe - The Cilk language and work-stealing scheduler','https://www.usenix.org/legacy/publications/library/proceedings/ana97/full_papers/blumofe/blumofe_html/node2.html'),
      ('LZUHPC assignment, frozen commit 33dad592','https://github.com/LZUOSS/LZUHPC/blob/33dad592cd74d8cf36ae7921a29c0e8393034a70/assignments/2026/autumn/HPC.Proj/README.md')]:p(title+' - '+url)

    md=['# Mini WorkSteal 实验与策略选择报告','', '生成依据：results/study-summary.json；真实实验日期 2026-10-16。','']
    for kind,value in sections:
        if kind=='h':md+=['## '+value,'']
        elif kind=='p':md+=[value,'']
        elif kind=='image':md+=[f'![{value}](figures/{value}.png)','']
        else:
            headers,rows,_=value;md+=['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(row)+' |' for row in rows]+['']
    (dest/'实验与策略选择报告.md').write_text('\n'.join(md),encoding='utf-8')
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib import colors as rc
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,KeepTogether
    pdfmetrics.registerFont(TTFont('CJK',a.font));styles=getSampleStyleSheet()
    normal=ParagraphStyle('CN',fontName='CJK',fontSize=9.4,leading=15,spaceAfter=8,wordWrap='CJK',textColor=rc.HexColor('#233547'))
    heading=ParagraphStyle('CNHeading',parent=normal,fontSize=15,leading=22,spaceBefore=15,spaceAfter=9,keepWithNext=True,textColor=rc.HexColor('#1D657F'))
    small=ParagraphStyle('CNSmall',parent=normal,fontSize=8,leading=12,spaceAfter=0)
    story=[Paragraph('Mini WorkSteal',ParagraphStyle('Cover',parent=heading,fontSize=30,leading=40)),Paragraph('实验与策略选择报告',heading),Paragraph('2026-10-16 | i9-13900HX / Ubuntu 24.04 / WSL1',normal),Spacer(1,12)]
    for kind,value in sections:
        if kind=='h':story.append(Paragraph(escape(value),heading))
        elif kind=='p':story.append(Paragraph(escape(value),normal))
        elif kind=='image':
            img=Image(str(figs/(value+'.png')));ratio=img.imageHeight/img.imageWidth;img.drawWidth=480;img.drawHeight=480*ratio;story+=[img,Spacer(1,9)]
        else:
            headers,rows,widths=value;n=len(headers);widths=widths or ([80,400] if n==2 else [480/n]*n)
            table=Table([[Paragraph(escape(s),small) for s in row] for row in [headers]+rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),rc.HexColor('#DDEBF0')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.6,rc.HexColor('#7FA7B6')),('LINEBELOW',(0,1),(-1,-1),.25,rc.HexColor('#D6DFE3')),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story+=[table,Spacer(1,10)]
    output=root/'output/pdf';output.mkdir(parents=True,exist_ok=True);pdf=output/'Mini-WorkSteal-实验与策略选择.pdf'
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont('CJK',8);canvas.setFillColor(rc.HexColor('#667789'));canvas.drawString(50,26,'Mini WorkSteal | 有限候选与本机证据');canvas.drawRightString(A4[0]-50,26,str(doc.page));canvas.restoreState()
    SimpleDocTemplate(str(pdf),pagesize=A4,leftMargin=50,rightMargin=50,topMargin=42,bottomMargin=44,title='Mini WorkSteal 实验与策略选择',author='Mini WorkSteal Project').build(story,onFirstPage=footer,onLaterPages=footer)
    import fitz
    doc=fitz.open(pdf);preview=root/'tmp/pdfs';preview.mkdir(parents=True,exist_ok=True)
    for page in doc:page.get_pixmap(matrix=fitz.Matrix(1.2,1.2)).save(preview/f'page-{page.number+1:02d}.png')
    texts=[page.get_text() for page in doc];assert all(len(t)>40 for t in texts)
    evidence={'pdf':str(pdf),'pages':len(doc),'summary_sha256':hashlib.sha256((root/'results/study-summary.json').read_bytes()).hexdigest(),'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'page_text_lengths':[len(t) for t in texts]}
    (output/'render-check.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(evidence,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
