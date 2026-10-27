#!/usr/bin/env python3
"""Generate the second-round report from audited optimization results."""
import argparse, hashlib, json, pathlib
from xml.sax.saxutils import escape

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);ap.add_argument('--font',default='C:/Windows/Fonts/simhei.ttf');a=ap.parse_args();root=pathlib.Path(a.root).resolve()
    summary=read(root/'optimization/results/optimization-summary.json');assert summary['complete']
    audit=read(root/'optimization/results/archive-audit.json');assert audit['pass']
    dest=root/'report/optimization';dest.mkdir(parents=True,exist_ok=True);figs=dest/'figures';figs.mkdir(exist_ok=True)
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'white'})
    groups=summary['groups'];kinds=('light','uniform','skewed','memory');colors=('#267A9C','#D08745','#426B44','#855C92')
    def find(stage,kind):return [g for g in groups if g['stage']==stage and g['kind']==kind]
    def figure(fig,name):fig.savefig(figs/(name+'.png'),dpi=200,bbox_inches='tight');fig.savefig(figs/(name+'.svg'),bbox_inches='tight');plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(10,7.2),layout='constrained')
    for ax,kind,col in zip(axes.flat,kinds,colors):
        gs=find('OPT1-build-screen',kind);base=next(g for g in gs if g['build']=='baseline')['epoch_seconds']['median']
        labels=[g['build'] for g in gs];vals=[base/g['epoch_seconds']['median'] for g in gs]
        ax.barh(labels,vals,color=col);ax.axvline(1,color='#667',ls=':');ax.set_title(kind+'; fixed p=4 and grain');ax.set_xlabel('baseline median / build median (n=3)')
    figure(fig,'build-screen')
    fig,axes=plt.subplots(2,2,figsize=(10,6.5),layout='constrained')
    for ax,kind in zip(axes.flat,kinds):
        gs=find('OPT2-parameter-screen',kind);grains=sorted({g['config']['policies']['partition']['grain'] for g in gs})
        for grain in grains:
            gg=sorted((g for g in gs if g['config']['policies']['partition']['grain']==grain),key=lambda g:g['config']['workers'])
            ax.plot([g['config']['workers'] for g in gg],[g['epoch_seconds']['median']*1000 for g in gg],'o-',label='g='+str(grain),ms=4)
        ax.set_xscale('log',base=2);ax.set_yscale('log');ax.set_xticks([1,2,4,8,16,32],[1,2,4,8,16,32]);ax.set_title(kind+'; selected build, n=3');ax.set_xlabel('logical worker masks');ax.set_ylabel('median epoch (ms, log)');ax.legend(fontsize=7);ax.grid(alpha=.15)
    figure(fig,'parameter-screen')
    fig,axes=plt.subplots(1,2,figsize=(10,3.5),layout='constrained');labels=[];epochs=[];e2es=[]
    for kind,d in summary['selection'].items():
        for h in d['heldout']:
            labels.append(kind+'\n'+str(h['seed']));epochs.append(h['base_over_candidate']);e2es.append(h['base']['end_to_end_seconds']['median']/h['candidate']['end_to_end_seconds']['median'])
    for ax,vals,title in zip(axes,(epochs,e2es),('Timed epoch','Application end-to-end incl. verification')):
        ax.bar(range(len(labels)),vals,color='#267A9C');ax.axhline(1,color='#667',ls=':');ax.set_xticks(range(len(labels)),labels,fontsize=7);ax.set_title(title);ax.set_ylabel('base median / candidate median (n=5)')
    figure(fig,'heldout')
    sections=[]
    def h(t):sections.append(('h',t))
    def p(t):sections.append(('p',t))
    def table(headers,rows,widths=None):sections.append(('table',(headers,rows,widths)))
    def img(name):sections.append(('image',name))
    h('联合优化结果')
    p('本轮继续优化运行时、等价计算内核、任务粒度与逻辑线程数。结论仅适用于本机 i9-13900HX / WSL1、固定独立任务及有限候选；“优化到极致”不能转化为全局最优的证明。上一轮报告和全部原始记录保留，本轮另建批次，不混成重复。')
    rows=[]
    for kind,d in summary['selection'].items():
        c=d['config'];rows.append([kind,d['build'],str(c['workers']),str(c['policies']['partition']['grain']),'两输入通过' if d['accepted'] else '保留基线'])
    table(['任务','推荐构建','worker','grain','决定'],rows,[55,145,55,55,170])
    p('完整配置位于 configs/optimized/，builds.json 包含每类对应的实际 CMake 参数与二进制 SHA256。构建选项也是推荐的一部分，不能用默认二进制执行优化配置后声称已复现同一收益。')
    h('留出输入：最终收益与波动')
    rows=[]
    for kind,d in summary['selection'].items():
        for c in d['heldout']:
            rows.append([f"{kind}/{c['seed']}",f"{c['base']['epoch_seconds']['median']*1000:.3f}",f"{c['candidate']['epoch_seconds']['median']*1000:.3f}",f"{c['base_over_candidate']:.2f}x",f"{c['wins']}/5",'是' if c['accepted'] else '否'])
    table(['任务/seed','base ms','候选 ms','base/候选','更快对数','通过'],rows,[90,80,80,85,75,70])
    img('heldout')
    p('主指标 epoch 排除建池、输入构造、分发和结果核验；应用端到端从run入口到关闭线程池，包含这些步骤，保留完整标量核验，因此加速小得多。它不包含外层配置读取、最终JSON序列化和操作系统进程启动；这些额外费用留在逐进程elapsed_process_seconds中。总收益同时包括内核实现、线程数、粒度及运行时改动；不能全部归因于工作窃取策略，更不能当成同线程数并行效率。')
    rows=[]
    for kind,d in summary['selection'].items():
        for c in d['heldout']:
            st=c['candidate']['epoch_seconds'];b=c['base'];cc=c['candidate']
            rows.append([f"{kind}/{c['seed']}",f"{st['min']*1000:.3f}-{st['max']*1000:.3f}",f"{st['iqr']*1000:.3f}",f"{b['end_to_end_seconds']['median']/cc['end_to_end_seconds']['median']:.2f}x"])
    table(['任务/seed','候选 min-max ms','候选 IQR ms','端到端 base/候选'],rows)
    h('实现改动与正确性依据')
    table(['改动','含义与保留约束'],[
        ['batch32','每 worker 累计已完成任务，每32个发布一次 remaining RMW；取不到任务或进入等待前发布余数，避免最后不足一批时无法结束。seq_cst RMW链和状态锁仍负责发布输出。'],
        ['scratch','首个偷取任务直接返回，额外描述符使用 worker 私有 vector，跨尝试复用容量。策略回调仍在锁外，批次顺序与单任务语义不变。'],
        ['LTO','CMake check_ipo_supported 成功后启用跨编译单元优化；没有 fast-math 或 march=native。LTO 单独是否有效由同参数筛选报告，不能预设加速。'],
        ['lanes4 / lanes8','同一任务内交错4/8个独立元素，暴露指令级并行；每元素原递推与迭代数不变。成本不同的块及尾部走标量路径；memory内核不变。与LTO配合测试。']], [85,395])
    p('这不是跳过工作：不同版本逐元素核验输出，记录 input/cost/data/output hash 和总逻辑成本；不同 grain 的 task hash 可不同。交错路径还覆盖小于lane宽度、非整倍数、偏斜分界和多种任务切分；CLI保留独立Python uint64参考。')
    p('任务发布计数只延迟已完成任务的计数，不预减未完成任务。worker 在取不到任务时刷新，本地余数不会让全部空闲线程永久等待。异常路径仍以 failed/finished 通知所有 worker，控制线程等 arrived==p 后才能复用。测试和sanitizer不是形式证明。')
    rows=[]
    for v in audit['validations']:
        rows.append([v['name'],str(v['runtime_checks']), '是' if v['pass'] else '否',v['binary_sha256'][:12]])
    table(['实际构建验证','runtime checks','通过','binary SHA前12位'],rows,[190,100,60,130])
    h('同参数消融：哪些改动有效')
    img('build-screen')
    p('OPT1固定p4、原grain和seed42，各构建一预热三计时，分别记录编译选项。light的grain1不具备多元素交错条件，可用于观察完成原子操作的摊销。重计算的lanes收益来自内核实现，不是窃取策略；memory未改计算内核，其几个百分点差异可能只是噪声。')
    h('线程数与粒度：有限搜索')
    img('parameter-screen')
    p('OPT2每类固定OPT1选出的构建。线程数1/2/4/8/16/32；light grain1/16/64/256、compute16/64/256/1024、memory1/2/4。按中位数最小选择，未测组合不称更差。32个逻辑mask不等于32物理核；WSL1未证明稳定物理驻留，也未核实P/E分配。')
    p('更多线程会增加启动/唤醒、锁争用和背景调度成本；不能预设32一定最快。grain增大改变描述符数、共享计数频率和分配。memory的grain/worker还改变home预读划分，收益只作为完整配置的净效果，不当纯调度或缓存因果。')
    h('预定选择规则与完整性')
    p('筛选阶段只看seed42。OPT3使用未参与筛选的seed137/2027，compute N196608/327680，memory48/80块。每输入一预热五对，AB/BA交错；两个输入都至少4/5对更快且候选中位数<=默认95%才接受。这个工程门槛不是统计显著性检验。失败时不选第二名、不追加到通过。')
    table(['阶段','条件数','研究进程','计时样本'],[[name,str(len(b['plan']['conditions'])),str(b['completion']['processes']),str(sum(g['epoch_seconds']['n'] for g in groups if g['stage']==name))] for name,b in summary['batches'].items()],[190,90,100,100])
    p(f"合计 {summary['processes']} 个研究进程，{summary['timing_samples']} 个计时样本。执行前冻结顺序、独立进程预热、全部慢成功记录保留；同组配置/身份/输出一致，跨构建/粒度总逻辑工作相同。逐记录、内外层散列、顺序、重复编号和二进制身份已审计，累计{summary['hash_checks']}次原始散列核验。")
    p('采集期间出现明显时间波动，成功记录全部保留。本机不是独占基准机。首批导出发生在OPT2预热期，之后停止导出直到批次结束；原导出暂态内容在最终核验中逐一确认，没有用拷贝时的未完成批次作结论。')
    h('复现与边界')
    p('实际Linux构建副本位于 /root/lzuhpc-experiments/ws-20261016-opt-*；构建日志、CMakeCache、validation、源码manifest和二进制均已逐文件导出至optimization/或evidence/opt-*。使用configs/optimized/builds.json里的CMake选项构建，再运行对应JSON；全部参数及原始路径在optimization/results/optimization-summary.json。')
    p('推荐配置已逐一再次真实执行验证，结果单独保存在optimization/results/recommendation-check-*，不用于选择。重算统计：python tools/analyze_opt.py --root .；审计：python tools/audit_opt.py --root .；报告：python tools/report_opt.py --root . --font <中文TrueType字体>。保留生成脚本、图表PNG/SVG、输入统计与原始进程索引。')
    p('适用边界：固定独立任务、定义良好的uint64回绕、带锁运行时、本机WSL1、这些规模和候选。没有证明全局最佳、真实缓存miss因果、NUMA或跨机器泛化；未加递归spawn、无锁deque或GPU。继续研究应换有可核实物理驻留的Linux环境，而不是在当前噪声中无限微调。')
    md=['# 第二轮优化与留出确认报告','','2026-10-16；由封存结果自动生成。','']
    for kind,value in sections:
        if kind=='h':md+=['## '+value,'']
        elif kind=='p':md+=[value,'']
        elif kind=='image':md+=[f'![{value}](figures/{value}.png)','']
        else:
            headers,rows,_=value;md+=['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(row)+' |' for row in rows]+['']
    (dest/'第二轮优化报告.md').write_text('\n'.join(md),encoding='utf-8')
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors as rc
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Image,Spacer
    pdfmetrics.registerFont(TTFont('OptCJK',a.font));normal=ParagraphStyle('OptCN',fontName='OptCJK',fontSize=9.3,leading=15,spaceAfter=8,wordWrap='CJK',textColor=rc.HexColor('#233547'))
    heading=ParagraphStyle('OptHead',parent=normal,fontSize=15,leading=22,spaceBefore=14,spaceAfter=9,keepWithNext=True,textColor=rc.HexColor('#1D657F'))
    small=ParagraphStyle('OptSmall',parent=normal,fontSize=8,leading=12,spaceAfter=0)
    story=[Paragraph('Mini WorkSteal',ParagraphStyle('OptTitle',parent=heading,fontSize=28,leading=36)),Paragraph('第二轮优化与留出确认',heading),Paragraph('2026-10-16 | 实现、指令并行、粒度与逻辑线程',normal),Spacer(1,9)]
    for kind,value in sections:
        if kind=='h':story.append(Paragraph(escape(value),heading))
        elif kind=='p':story.append(Paragraph(escape(value),normal))
        elif kind=='image':
            im=Image(str(figs/(value+'.png')));ratio=im.imageHeight/im.imageWidth;im.drawWidth=480;im.drawHeight=480*ratio;story += [im,Spacer(1,9)]
        else:
            headers,rows,widths=value;widths=widths or [480/len(headers)]*len(headers)
            t=Table([[Paragraph(escape(s),small) for s in row] for row in [headers]+rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),rc.HexColor('#DDEBF0')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.6,rc.HexColor('#7FA7B6')),('LINEBELOW',(0,1),(-1,-1),.25,rc.HexColor('#D6DFE3')),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story += [t,Spacer(1,9)]
    pdf=root/'output/pdf/Mini-WorkSteal-第二轮优化.pdf';pdf.parent.mkdir(parents=True,exist_ok=True)
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont('OptCJK',8);canvas.setFillColor(rc.HexColor('#667789'));canvas.drawString(50,26,'Mini WorkSteal | 第二轮优化 / 本机有限搜索');canvas.drawRightString(A4[0]-50,26,str(doc.page));canvas.restoreState()
    SimpleDocTemplate(str(pdf),pagesize=A4,leftMargin=50,rightMargin=50,topMargin=42,bottomMargin=44,title='Mini WorkSteal 第二轮优化').build(story,onFirstPage=footer,onLaterPages=footer)
    import fitz
    doc=fitz.open(pdf);preview=root/'tmp/pdfs/optimization';preview.mkdir(parents=True,exist_ok=True)
    for page in doc:page.get_pixmap(matrix=fitz.Matrix(1.2,1.2)).save(preview/f'page-{page.number+1:02d}.png')
    result={'pages':len(doc),'pdf':str(pdf),'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'summary_sha256':hashlib.sha256((root/'optimization/results/optimization-summary.json').read_bytes()).hexdigest(),'page_text_lengths':[len(p.get_text()) for p in doc]}
    (root/'output/pdf/optimization-render-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
