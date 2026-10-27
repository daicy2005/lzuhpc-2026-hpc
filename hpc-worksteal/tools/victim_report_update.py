#!/usr/bin/env python3
"""Recheck cited runs and append a three-page V16 supplement to the sealed PDF."""
import argparse
import html
import json
import pathlib
import statistics
import sys

import lab


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--font', required=True)
    args = parser.parse_args()
    root = lab.ROOT
    sys.path.insert(0, str(root/'.cache/report-python'))
    import fitz
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image, PageBreak

    area = root/'victim-selection-recovery'
    audits = sorted((area/'results').glob('audit-*.json'))
    assert len(audits) == 2
    a, b = [read(p) for p in audits]
    assert {k:v for k,v in a.items() if k != 'created'} == {k:v for k,v in b.items() if k != 'created'}
    assert a['audit_pass'] and a['complete'] and not a['accepted']
    assert (a['processes'], a['timing_samples'], a['diagnostic_samples']) == (114,84,18)
    sources = {}
    for p in [*audits, area/'results/frozen-plan.json', area/'results/recovery-link.json',
              root/'docs/50-第十六轮Victim选择恢复结果.md',
              root/'report/victim-selection/第十六轮Victim选择报告-b339e9e0.md', pathlib.Path(__file__)]:
        sources[p.relative_to(root).as_posix()] = lab.digest(p)
    verified = {}

    def check_run(path, epoch, app, binary=None):
        rel = path.relative_to(root).as_posix()
        assert rel not in verified
        hashes = read(path/'checksums.json')
        for name, sha in hashes.items():
            assert lab.digest(path/name) == sha, (rel,name)
        r, m = read(path/'result.json'), read(path/'metadata.json')
        assert m['purpose'] == 'timing' and m['status'] == 'completed' and m['included'] and m['exit_code'] == 0
        assert r['correctness']['pass'] and read(path/'stdout.log') == r and not (path/'stderr.log').read_bytes()
        assert r['timing']['epoch_seconds'] == epoch and r['timing']['end_to_end_seconds'] == app
        n = r['resolved_config']['workload']['elements']
        assert all(e['correctness']['compared_elements'] == n and e['correctness']['mismatches'] == 0 for e in r['epochs'])
        if binary:
            assert m['binary_sha256'] == binary
        verified[rel] = {'result_sha256':lab.digest(path/'result.json'), 'checksums_sha256':lab.digest(path/'checksums.json'),
                         'epoch':epoch,'app':app,'binary_sha256':m['binary_sha256']}
        return r

    old = read(root/'report/final/input-data.json')
    assert len(old['verified_raw_runs']) == 579
    for rel,v in old['verified_raw_runs'].items():
        assert lab.digest(root/rel/'result.json') == v['result_sha256']
        check_run(root/rel,v['epoch'],v['app'],v['binary_sha256'])
    groups = sorted(a['confirmation']['groups'], key=lambda g: (g['seed'], ('concentrated','spread','shuffled').index(g['layout'])))
    for g in groups:
        assert len(g['pairs']) == 7
        for pair in g['pairs']:
            for side in ('base','candidate'):
                v = pair[side]
                r = check_run(area/v['run_path'],v['epoch'],v['app'])
                assert r['resolved_config']['workload']['seed'] == g['seed']
                assert r['resolved_config']['policies']['victim']['name'] == ('round_robin' if side == 'base' else 'seeded_random')
        for side in ('base','candidate'):
            for metric in ('epoch','app'):
                assert statistics.median(p[side][metric] for p in g['pairs']) == g['medians'][side][metric]
        wins = sum(p['candidate']['epoch'] < p['base']['epoch'] for p in g['pairs'])
        assert wins == g['epoch_wins']
        ratio = g['medians']['candidate']['epoch']/g['medians']['base']['epoch']
        app_ratio = g['medians']['candidate']['app']/g['medians']['base']['app']
        passed = app_ratio <= 1.05 and (wins >= 6 and ratio <= .95 if g['target'] else ratio <= 1.10)
        assert passed == g['pass']
    assert len(verified) == 663 and not all(g['pass'] for g in groups)
    old_pdf = root/'output/pdf/Mini-WorkSteal-最终技术报告-20261025.pdf'
    assert lab.digest(old_pdf) == '64a7c06a7663aaac360670cff8db51864339c5050b7776ae691bc34e49fe4e17'
    sources[old_pdf.relative_to(root).as_posix()] = lab.digest(old_pdf)
    sources['report/final/input-data.json'] = lab.digest(root/'report/final/input-data.json')
    out = root/'report/victim-selection/update-20261027'
    out.mkdir(exist_ok=False)
    lab.write(out/'input-data.json', {'created':lab.now(), 'groups':groups, 'source_sha256':sources,
        'verified_raw_runs':verified, 'cited_formal_runs':663, 'v16_formal_runs':84,
        'scope':'report-cited runs, not all historical experimental samples',
        'container_actual_build_verified':False, 'user_scope':'finish local experiments and delivery; container deferred'})

    font = FontProperties(fname=args.font)
    fig, ax = plt.subplots(figsize=(8.3,3.35),layout='constrained')
    for i,g in enumerate(groups):
        ratios = [p['candidate']['epoch']/p['base']['epoch'] for p in g['pairs']]
        ax.scatter(ratios,[i]*7,s=27,alpha=.80,color='#d5663d' if g['target'] else '#277c9c')
        ratio=g['medians']['candidate']['epoch']/g['medians']['base']['epoch']
        ax.scatter([ratio],[i],marker='D',s=60,color='#182c45',zorder=4)
    ax.set_yticks(range(6),[f"{g['seed']} / {g['layout']}" for g in groups])
    ax.invert_yaxis()
    ax.axvline(1,color='#6e7782',lw=1)
    ax.axvline(.95,color='#d5663d',ls='--',lw=1)
    ax.axvline(1.10,color='#277c9c',ls=':',lw=1)
    ax.grid(axis='x',alpha=.16)
    ax.set_xlabel('epoch用时比 random / round_robin；圆点=逐对比，菱形=两组中位数之比',fontproperties=font,fontsize=10)
    ax.set_title('集中输入须兼顾胜对和至少5%的中位数改善',fontproperties=font,fontsize=12,pad=10)
    for spine in ('top','right'):ax.spines[spine].set_visible(False)
    fig.savefig(out/'paired-epoch.png',dpi=190)
    fig.savefig(out/'paired-epoch.svg')
    plt.close(fig)

    pdfmetrics.registerFont(TTFont('V16CJK',args.font))
    base = ParagraphStyle('body',fontName='V16CJK',fontSize=10,leading=16,textColor=colors.HexColor('#26364c'),spaceAfter=9,wordWrap='CJK')
    title = ParagraphStyle('title',parent=base,fontSize=23,leading=32,spaceAfter=14,textColor=colors.HexColor('#132840'))
    head = ParagraphStyle('heading',parent=base,fontSize=13,leading=20,spaceBefore=10,spaceAfter=8)
    small = ParagraphStyle('small',parent=base,fontSize=8.2,leading=12,spaceAfter=7)
    def p(text,style=base):return Paragraph(html.escape(text),style)
    def table(rows,widths):
        t=Table([[p(str(c),small) for c in row] for row in rows],colWidths=widths,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7edf3')),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f8fa')]),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),
            ('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),
            ('BOTTOMPADDING',(0,0),(-1,-1),5),('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#aabacc'))]))
        return t
    story=[p('Mini WorkSteal',small),p('第十六轮结果与交付更新',title),p('2026-10-27 | 原综合报告之后的三页补充',small),
        p('结论：随机victim未过门槛，保留round_robin。',head),
        p('资源恢复后完成原定114个进程：18诊断、12预热、84正式计时。两集中输入分别6/7、2/7对更快，epoch中位数下降3.04%、上升1.97%；两者均未通过预定主要条件。四组布局护栏及六组应用耗时护栏通过。'),
        p('六组完整结果',head)]
    rows=[['seed / 布局','epoch RR→random ms','胜对','app变化']]
    for g in groups:
        m=g['medians'];rows.append([f"{g['seed']} / {g['layout']}",f"{m['base']['epoch']*1e3:.4f} → {m['candidate']['epoch']*1e3:.4f}",f"{g['epoch_wins']}/7",f"{(m['candidate']['app']/m['base']['app']-1)*100:+.2f}%"])
    story += [table(rows,[177,155,54,125]),Spacer(1,13),
        p('固定条件：compute_skewed，p32、grain256、K1024、ref32、immediate、single、CPUs 0..31；同一第四轮full_lanes8 Release，只改变victim。新输入：seed140009/N229376与seed146021/N360448。'),
        p('采用要求：两个集中输入各至少6/7对胜出且epoch中位数≤基线95%；分散和打乱各≤110%；六组app≤105%。工程选择门槛不等于统计显著性检验。'),
        p('本版范围：前十二页为2026-10-25综合报告原页，本补充为2026-10-27实际结果。合计重新核对663份报告引用的正式run；该数不是历史实验总样本数。',small),PageBreak()]
    story += [p('结果怎样解释',title),Image(str(out/'paired-epoch.png'),width=511,height=206),Spacer(1,9),
        p('“随机”不是自动更优',head),
        p('随机选择只改变空闲worker找谁要任务；任务粒度、队列锁、完成协议和计算内核仍相同。更少的成功窃取或更均衡的工作量，不能保证更短的关键路径。具体慢因仍需额外观测，不能从本轮结果反推。'),
        p('诊断与正式计时分开',head),
        p('seed146021集中布局的额外诊断中，random成功steals为189（RR为233），单位均衡度0.8148（RR为0.6111）；正式epoch中位数却略慢。诊断指标说明观测层面不同，不能作为同一次正式采样的因果证据。attempts不含第一次锁失败，busy/attempts不是整体失败率。'),
        p('源码相关性不是性能因果证明',head),
        p('现有随机策略的各worker从相同state开始，同尝试序号存在相关性；本轮没有实现独立随机流，也未记录真实同时争抢。因此不能把这个源码性质直接解释为本轮退化原因。'),
        p('资源门禁与范围',head),
        p('唯一恢复窗口等待53.767秒，CPU 36%/40%后出现9%/11%/14%连续合格；整批23.851秒，272次批内WSL观察未触发既定阻断。没有持续Windows负载观测，不证明物理独占、P/E分布、NUMA或缓存驻留。'),
        p('保留全部慢成功样本；一份外部process约467ms的记录没有剔除。process含启动等外部时间，app为应用内部端到端计时，epoch为执行区间，三者分别记录。',small),PageBreak()]
    story += [p('核验、复现与交付边界',title),
        p('双端独立核验',head),
        p('Linux与Windows均从原始记录重建并审计，除创建时间外结论相同；每端1638项批次/运行散列，1086份导出文件核对通过。全部114进程完整标量参考核验；18诊断额外核对exact_once及最终执行归属。'),
        p('Python独立重建任务、输入、工作量和初始队列。shuffle模型重新匹配50组独立C++标准库对照。小规模control另有逐元素Python参考；预热和诊断不进入84份正式统计。'),
        p('原件与构建身份',head),
        table([['项目','证据'],['历史被测二进制','c52674ba1244813d7d71808298b552042487a8bbeb41b8349a3eb4915027da8c'],
               ['历史被测源码','e85c97b09468b4a3c6a6286bdceac7ffa408d2983cc2a957765e6b3bd9580c86'],
               ['本轮采集源码','da64dae2aaef233596954ce36c64cc96d6b72d0d45ceb4d12e91bd946519a64d']], [112,399]),Spacer(1,10),
        p('本轮没有新C++编译或sanitizer；历史验证仍归原构建。当前六个推荐配置、生产代码及CMake保持。旧两段0计时等待、旧PDF与ZIP均不修改。'),
        p('本机交付与暂缓项',head),
        p('用户已确认暂无容器环境，先完成本机实验和交付。原生Linux三份Release复现、六配置功能核验和当前证据归档可交付；DevContainer实建暂缓，仍未验证。最初临时图片缺失，连续Session仅保全实际持久化可见文本。外部提交未执行。'),
        p('复现和原始数据入口',head),
        p('docs/50：完整分析与原件链接；report/victim-selection：全部42对逐run正文；victim-selection-recovery/results：两端audit、冻结plan和恢复来源；同目录runs：114份完整记录。旧综合报告正文、输入及图表位于report/final。',small),
        p('只读复核：python tools/recover_victim_selection.py report --root victim-selection-recovery。它会另存审计/报告；不要再次执行run。Linux构建步骤与原生复现收据见submission/README.md及submission/reproduction/20261025。',small),
        p('本页数据由tools/victim_report_update.py从663份原始run复核；精确输入与SHA256清单位于report/victim-selection/update-20261027/input-data.json。',small)]
    temp=root/'tmp/pdfs/update-20261027';temp.mkdir(parents=True,exist_ok=False)
    supplement=temp/'supplement.pdf'
    def footer(canvas,doc):
        canvas.setFont('V16CJK',8);canvas.setFillColor(colors.HexColor('#617287'))
        canvas.drawString(42,24,'Mini WorkSteal | 2026-10-27 | V16 supplement')
        canvas.drawRightString(A4[0]-42,24,f'补充 {doc.page}/3')
    SimpleDocTemplate(str(supplement),pagesize=A4,leftMargin=42,rightMargin=42,topMargin=40,bottomMargin=42).build(story,onFirstPage=footer,onLaterPages=footer)
    pdf=root/'output/pdf/Mini-WorkSteal-技术报告-20261027.pdf'
    assert not pdf.exists()
    old_doc,extra=fitz.open(old_pdf),fitz.open(supplement)
    assert len(old_doc)==12 and len(extra)==3, (len(old_doc),len(extra))
    old_doc.insert_pdf(extra);old_doc.set_metadata({'title':'Mini WorkSteal 技术报告 - 2026-10-27','author':'Mini WorkSteal 项目','subject':'十五轮综合报告与第十六轮结果补充'})
    old_doc.save(pdf);old_doc.close();extra.close()
    document=fitz.open(pdf);pages=[]
    for i,page in enumerate(document):
        text=page.get_text();assert len(text.strip())>60
        bounds=all(b[0]>=0 and b[1]>=0 and b[2]<=page.rect.width+1 and b[3]<=page.rect.height+1 for b in page.get_text('blocks'))
        assert bounds,(i+1,'text bounds')
        page.get_pixmap(matrix=fitz.Matrix(1.4,1.4),alpha=False).save(temp/f'page-{i+1:02}.png')
        pages.append({'page':i+1,'text_characters':len(text),'text_bounds_checked':bounds})
    lab.write(root/'output/pdf/update-20261027-render-check.json',{'created':lab.now(),'pdf':pdf.relative_to(root).as_posix(),
        'pdf_sha256':lab.digest(pdf),'pages':pages,'cited_raw_runs_rechecked':663,'new_formal_runs':84,
        'input':(out/'input-data.json').relative_to(root).as_posix(),'input_sha256':lab.digest(out/'input-data.json'),
        'generator_sha256':lab.digest(pathlib.Path(__file__)),'manual_visual_review':'pending'})
    print(json.dumps({'pdf':str(pdf),'pages':len(document),'cited_formal_runs_verified':663},ensure_ascii=False))


if __name__=='__main__':main()
