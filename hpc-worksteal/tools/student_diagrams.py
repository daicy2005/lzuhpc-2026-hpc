"""Editable reconstructions and icon refinements of the existing generated designs."""
from pathlib import Path
import hashlib
import json
import math
import subprocess

from reportlab.graphics.shapes import Drawing, Group, Rect, Circle, Line, Polygon, String, Path as VectorPath
from reportlab.graphics import renderSVG, renderPDF
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / 'report/student/figures'
NAVY, TEAL, BLUE, AMBER, GRAY = '#183D65', '#168C91', '#4C8ED3', '#D49539', '#858B91'
pdfmetrics.registerFont(TTFont('DiagramSans', 'C:/Windows/Fonts/msyh.ttc', subfontIndex=0))
pdfmetrics.registerFont(TTFont('DiagramSansBold', 'C:/Windows/Fonts/msyhbd.ttc', subfontIndex=0))


def color(value):
    return colors.HexColor(value)


class Sheet:
    def __init__(self, width, height):
        self.drawing = Drawing(width, height)
        self.width, self.height = width, height

    def box(self, x, top, w, h, fill='#FFFFFF', stroke=None, radius=12, lw=2):
        self.drawing.add(Rect(x, self.height-top-h, w, h, rx=radius, ry=radius,
                              fillColor=color(fill), strokeColor=color(stroke) if stroke else None,
                              strokeWidth=lw))

    def text(self, value, x, top, size=25, fill=NAVY, bold=False, anchor='start'):
        self.drawing.add(String(x, self.height-top-size, value, fontSize=size,
                                fontName='DiagramSansBold' if bold else 'DiagramSans',
                                textAnchor=anchor, fillColor=color(fill)))

    def line(self, x1, y1, x2, y2, stroke=NAVY, lw=3):
        self.drawing.add(Line(x1, self.height-y1, x2, self.height-y2,
                             strokeColor=color(stroke), strokeWidth=lw,
                             strokeLineCap=1))

    def circle(self, x, y, radius, stroke=NAVY, fill=None, lw=3):
        self.drawing.add(Circle(x, self.height-y, radius, strokeColor=color(stroke) if stroke else None,
                               fillColor=color(fill) if fill else None, strokeWidth=lw))

    def arrow(self, x1, y1, x2, y2, stroke=TEAL, lw=4):
        length = math.hypot(x2-x1, y2-y1)
        if not length:
            return
        ux, uy = (x2-x1)/length, (y2-y1)/length
        head = min(10, max(6, lw*2.5), length*.36)
        half = head*.62
        bx, by = x2-ux*head, y2-uy*head
        self.line(x1, y1, bx+ux, by+uy, stroke, lw)
        points = [x2, self.height-y2, bx-uy*half, self.height-(by+ux*half),
                  bx+uy*half, self.height-(by-ux*half)]
        self.drawing.add(Polygon(points, fillColor=color(stroke), strokeColor=None))

    def check(self, x, y, size=40, stroke=TEAL):
        self.line(x-size*.42, y, x-size*.10, y+size*.28, stroke, 5)
        self.line(x-size*.10, y+size*.28, x+size*.48, y-size*.30, stroke, 5)


def icon(sheet, kind, x, y, scale=1, stroke=NAVY):
    """One 112-unit optical box; common stroke, rounded ends and simple silhouettes."""
    weight = 3.4
    def line(a,b,c,d,ink=stroke,lw=weight):
        sheet.line(x+a*scale,y+b*scale,x+c*scale,y+d*scale,ink,lw*scale)
    def box(a,b,w,h,fill='#FFFFFF',ink=stroke,radius=5):
        sheet.box(x+a*scale,y+b*scale,w*scale,h*scale,fill,ink,radius*scale,weight*scale)
    def circle(a,b,r,ink=stroke,fill=None):
        sheet.circle(x+a*scale,y+b*scale,r*scale,ink,fill,weight*scale)
    def path(points, ink=stroke, fill=None):
        p = VectorPath(strokeColor=color(ink), fillColor=color(fill) if fill else None,
                       strokeWidth=weight*scale, strokeLineCap=1, strokeLineJoin=1)
        for i, (a,b) in enumerate(points):
            (p.moveTo if i==0 else p.lineTo)(x+a*scale,sheet.height-y-b*scale)
        sheet.drawing.add(p)
    def check(a,b,size=16,ink=stroke):
        path([(a-size*.45,b),(a-size*.10,b+size*.30),(a+size*.48,b-size*.35)],ink)
    def arrow(a,b,c,d,ink=stroke):
        sheet.arrow(x+a*scale,y+b*scale,x+c*scale,y+d*scale,ink,weight*scale)
    if kind == 'config':
        box(-39,-46,78,92)
        for row, offset in [(-23,-13),(0,13),(23,0)]:
            line(-25,row,25,row)
            circle(offset,row,5,stroke,'#D9F0F2')
    elif kind == 'cards':
        box(-16,-45,60,68,'#DCEFF3','#80B7C8')
        box(-29,-32,60,68,'#EEF7FA','#5D9DB5')
        box(-42,-19,60,68)
        for row in (0,15,30):
            line(-29,row,5,row,TEAL)
    elif kind == 'queues':
        for row in (-31,0,31):
            circle(-44,row,9,stroke,'#C2E7ED')
            box(-25,row-10,62,20,radius=4)
        box(17,-41,20,20,'#F8DFB5',AMBER,3)
        line(-5,-40,-5,-22,'#9BCBD5')
        line(16,-40,16,-22,'#9BCBD5')
        line(-5,-9,-5,9,'#9BCBD5')
        line(-5,22,-5,40,'#9BCBD5')
        path([(42,-31),(53,-31),(53,31)],AMBER)
        arrow(53,31,40,31,AMBER)
    elif kind in ('verify','check'):
        box(-34,-43,68,86)
        box(-13,-49,26,12,'#E6F2F7',stroke,4)
        for row in (-20,3,26):
            check(-16,row,14,TEAL if kind=='verify' else stroke)
            line(1,row,22,row,'#6EAFC1' if kind=='verify' else stroke)
    elif kind == 'balance':
        line(0,-33,0,39)
        line(-35,-21,35,-21)
        line(-18,40,18,40)
        for side in (-27,27):
            path([(side-13,10),(side,-21),(side+13,10)],stroke)
            line(side-13,10,side+13,10)
        circle(0,-35,4,stroke,stroke)
    elif kind == 'tuning':
        for col, offset in [(-27,-13),(0,16),(27,-2)]:
            line(col,-39,col,39)
            box(col-9,offset-6,18,12,'#E5F4F4',stroke,4)
    elif kind == 'memory':
        box(-29,-29,58,58,'#F3FAFB',stroke,6)
        for a in (-13,13):
            for b in (-13,13):
                box(a-7,b-7,14,14,'#DDF0F1',stroke,2)
        for offset in (-16,0,16):
            line(offset,-43,offset,-31)
            line(offset,31,offset,43)
            line(-43,offset,-31,offset)
            line(31,offset,43,offset)
    elif kind == 'transfer':
        box(-45,-37,27,74,radius=5)
        box(18,-37,27,74,radius=5)
        for row in (-23,0,23):
            box(-40,row-7,17,14,'#F9E8CD',stroke,2)
        box(23,16,17,14,'#F9E8CD',stroke,2)
        arrow(-11,0,11,0)
    elif kind == 'question':
        circle(0,0,40)
        p = VectorPath(strokeColor=color(stroke), fillColor=None,
                       strokeWidth=weight*scale,strokeLineCap=1,strokeLineJoin=1)
        def pt(a,b):
            return x+a*scale,sheet.height-y-b*scale
        p.moveTo(*pt(-12,-16))
        p.curveTo(*pt(-9,-31),*pt(15,-29),*pt(15,-13))
        p.curveTo(*pt(15,-4),*pt(0,-2),*pt(0,11))
        sheet.drawing.add(p)
        circle(0,24,2,stroke,stroke)
    else:
        raise ValueError(f'Unknown diagram icon: {kind}')


def runtime_diagram():
    s = Sheet(1440, 540)
    s.text('Mini WorkSteal 运行流程',720,3,38,bold=True,anchor='middle')
    cards = [
        ('配置与注册',['JSON / Registry'],'config',None),
        ('切分与放置',['Partition / Placement'],'cards','固定任务集合'),
        ('执行与窃取',['Victim / Timing','Migration'],'queues','持久线程 / 带锁队列'),
        ('完成与核验',['结果发布 / 逐元素参考'],'verify',None),
    ]
    for i,(heading,details,kind,note) in enumerate(cards):
        x=15+i*360
        s.box(x,82,330,304,'#F6FBFD','#72B7CA',18)
        s.box(x+2,84,326,61,'#E7F3F8',None,16)
        s.text(heading,x+165,96,31,bold=True,anchor='middle')
        for j,detail in enumerate(details):
            s.text(detail,x+165,159+j*29,24,anchor='middle')
        icon(s,kind,x+165,270,1.00)
        if note:
            s.box(x+23,339,284,33,'#E0F1F6',None,16)
            s.text(note,x+165,342,21,anchor='middle')
        if i<3:
            s.arrow(x+337,237,x+353,237,TEAL,3)
    s.box(357,416,726,64,'#E8F4F8','#72B7CA',30)
    s.text('Affinity：工作线程与逻辑 CPU 的绑定请求',720,432,26,bold=True,anchor='middle')
    s.text('Migration：任务描述符在工作队列间转移',720,505,22,anchor='middle')
    return s.drawing


def roadmap_diagram():
    s=Sheet(1440,680)
    s.text('实验路线与方案选择',720,3,38,bold=True,anchor='middle')
    cards=[
        (1,20,87,'调度策略对照','第一轮','粒度 / 偏斜 / 局部性','balance',NAVY,None),
        (2,520,87,'执行内核与参数优化','第二、三轮','联合配置分别确认','tuning',TEAL,None),
        (3,1020,87,'完整核验并行化','第四、五轮','保留：并行核验','check',BLUE,None),
        (4,1020,365,'内存路径优化与诊断','第六至十二轮','保留：四路执行交错','memory',TEAL,'其他候选未通过 / 独立诊断'),
        (5,520,365,'窃取边界与策略验证','第十三至十五轮','批量与退避：未采用','transfer',AMBER,None),
        (6,20,365,'Victim 策略对照','第十六轮','准备完成，尚未计时','question',GRAY,None),
    ]
    for number,x,top,title,rounds,outcome,kind,ink,note in cards:
        s.box(x,top,400,230,'#FBFDFE',ink,15)
        s.box(x+2,top+2,396,47,'#EEF4F7',None,13)
        s.box(x-2,top-2,85,65,ink,None,10)
        s.text(f'{number:02}',x+40,top+4,42,'#FFFFFF',True,'middle')
        icon(s,kind,x+68,top+130,.82,ink)
        s.text(title,x+134,top+67,25,bold=True)
        badge_width=min(248,len(rounds)*23+24)
        s.box(x+134,top+109,badge_width,36,'#E8F0F5',None,12)
        s.text(rounds,x+146,top+113,22,ink)
        s.text(outcome,x+134,top+159,22)
        if note:
            s.text(note,x+24,top+200,19,'#677785')
    s.arrow(442,205,500,205,NAVY,4)
    s.arrow(942,205,1000,205,NAVY,4)
    s.arrow(1220,326,1220,353,NAVY,4)
    s.arrow(1000,481,942,481,NAVY,4)
    s.arrow(500,481,442,481,NAVY,4)
    s.line(190,646,275,646,NAVY,2)
    s.line(1165,646,1250,646,NAVY,2)
    s.text('对照实验 → 新输入验证 → 方案选择',720,623,27,bold=True,anchor='middle')
    return s.drawing


def export_diagrams():
    FIGURES.mkdir(parents=True,exist_ok=True)
    result={}
    provenance={'mode':'User-selected imagegen CLI design, then native vector reconstruction',
                'entrypoint':'C:/Users/admin/.codex/tools/imagegen/imagegen.ps1',
                'provider':'laogou','model':'gpt-image-2.5-sunburst','quality':'high',
                'reconstruction_generator':'tools/student_diagrams.py',
                'vector_revision':'icons-v2-consistent-strokes',
                'new_image_generation_requests_in_this_revision':0,
                'icon_refinements':['Shared 3.4-unit strokes and rounded line ends',
                                    'Parameter sliders replace the abstract chain',
                                    'Checklist, memory chip and task-queue transfer symbols',
                                    'Arrowheads scale to connector length'],
                'assets':{}}
    designs={'runtime-flow-designed':('runtime-flow','b1911315636e483eb0feea8767274b21'),
             'exploration-roadmap-designed':('exploration-roadmap','f8e6608b5ccb452184b07212a129b10f')}
    for name,make in [('runtime-flow-designed',runtime_diagram),
                      ('exploration-roadmap-designed',roadmap_diagram)]:
        drawing=make()
        target=FIGURES/f'{name}.svg'
        renderSVG.drawToFile(drawing,str(target))
        svg=target.read_text(encoding='utf-8')
        svg=svg.replace('font-family: DiagramSansBold', "font-family: Microsoft YaHei; font-weight: bold")
        svg=svg.replace('font-family: DiagramSans', 'font-family: Microsoft YaHei')
        assert '<image' not in svg and '<text' in svg and '<rect' in svg
        target.write_text(svg,encoding='utf-8')
        result[name]=drawing
        source,receipt=designs[name]
        raw=ROOT/f'output/imagegen/{source}-20261026.png'
        prompt=FIGURES/f'prompts/{source}-20261026.txt'
        provenance['assets'][name]={
            'source_image':raw.relative_to(ROOT).as_posix(),
            'source_image_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),
            'prompt':prompt.relative_to(ROOT).as_posix(),
            'prompt_sha256':hashlib.sha256(prompt.read_bytes()).hexdigest(),
            'provider_result_receipt_id':receipt,
            'vector':target.relative_to(ROOT).as_posix(),
            'vector_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'embedded_raster_images':0,
            'text_editable':True,
            'review':'Reconstructed labels, stages, status and arrows checked against project sources.'}
    (FIGURES/'design-provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    preview=ROOT/'tmp/pdfs/diagram-previews'
    preview.mkdir(parents=True,exist_ok=True)
    poppler='C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe'
    for name,drawing in export_diagrams().items():
        pdf=preview/f'{name}.pdf'
        renderPDF.drawToFile(drawing,str(pdf))
        subprocess.run([poppler,'-singlefile','-r','100','-png',str(pdf),str(preview/name)],check=True)
    print('Two editable SVG reconstructions exported; no embedded raster images.')
