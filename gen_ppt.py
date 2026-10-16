# -*- coding: utf-8 -*-
"""生成答辩 PPT（16:9，16 页，纯 python-pptx 可编辑元素）。

设计约定：
    - 深蓝为主色（技术），绿色为辅助（农业），橙色作强调
    - 全部文字框、表格、形状均为原生可编辑对象，不使用图片排版
    - 材料中不出现学校名称、学院名称与指导人员信息
    - 涉及合成数据的页面在页面内明确标注数据来源
"""
import io
import json
import os
import sys

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Cm, Emu, Inches, Pt

sys.path.insert(0, r"E:\harness\aic")
import metrics_source as M  # noqa: E402  指标从结果文件读取，不手写

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUT_DIR = r"E:\harness\aic\成果包\02_答辩PPT"
OUT = os.path.join(OUT_DIR, "答辩PPT.pptx")

# ---------- 配色 ----------
NAVY = RGBColor(0x14, 0x2C, 0x52)      # 主色：深蓝
BLUE = RGBColor(0x1F, 0x5C, 0x99)      # 次深蓝
LBLUE = RGBColor(0xE8, 0xF0, 0xF8)     # 浅蓝底
GREEN = RGBColor(0x2E, 0x7D, 0x4F)     # 农业绿
LGREEN = RGBColor(0xE8, 0xF3, 0xEC)
ORANGE = RGBColor(0xD9, 0x6B, 0x1E)    # 强调
LORANGE = RGBColor(0xFD, 0xF1, 0xE6)
GREY = RGBColor(0x5A, 0x62, 0x6B)
LGREY = RGBColor(0xF2, 0xF4, 0xF6)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
RED = RGBColor(0xC0, 0x30, 0x2B)

FONT = "微软雅黑"

# ---------- 指标 ----------
KB = M.kb_stats()
DX = M.dx_eval()
RC = M.region_calibration()
DET = M.detection()

SW = Inches(13.333)
SH = Inches(7.5)
TITLE = "基于视觉行为感知的猪只疫病辅助诊断系统"


# ============================================================
# 基础工具
# ============================================================
def slide_blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def rect(slide, x, y, w, h, fill=None, line=None, line_w=1.0,
         shape=MSO_SHAPE.RECTANGLE, shadow=False):
    s = slide.shapes.add_shape(shape, x, y, w, h)
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(line_w)
    s.shadow.inherit = shadow
    return s


def textbox(slide, x, y, w, h, anchor=MSO_ANCHOR.TOP, wrap=True):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Emu(0)
    tf.margin_top = tf.margin_bottom = Emu(0)
    return tb, tf


def setp(tf, text, size=14, bold=False, color=NAVY, align=PP_ALIGN.LEFT,
         first=False, space_before=0, space_after=4, line_spacing=1.25, font=FONT):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.space_before = Pt(space_before)
    p.space_after = Pt(space_after)
    p.line_spacing = line_spacing
    if text:
        r = p.add_run()
        r.text = text
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
        r.font.name = font
    return p


def title_bar(slide, title, sub=None, idx=None):
    """内容页页眉：左侧色块 + 标题 + 可选副标题 + 页码。"""
    rect(slide, Inches(0.55), Inches(0.42), Inches(0.09), Inches(0.52), fill=ORANGE)
    tb, tf = textbox(slide, Inches(0.78), Inches(0.36), Inches(11.0), Inches(0.62),
                     anchor=MSO_ANCHOR.MIDDLE)
    setp(tf, title, size=25, bold=True, color=NAVY, first=True, space_after=0)
    if sub:
        tb2, tf2 = textbox(slide, Inches(0.80), Inches(1.00), Inches(11.6), Inches(0.34))
        setp(tf2, sub, size=12, color=GREY, first=True, space_after=0)
    if idx is not None:
        tb3, tf3 = textbox(slide, Inches(12.45), Inches(6.92), Inches(0.6), Inches(0.3))
        setp(tf3, str(idx), size=10, color=GREY, align=PP_ALIGN.RIGHT, first=True)
    # 页脚作品名
    tb4, tf4 = textbox(slide, Inches(0.55), Inches(6.92), Inches(5.0), Inches(0.3))
    setp(tf4, TITLE, size=9, color=RGBColor(0xA8, 0xB0, 0xB8), first=True)


def note_src(slide, text):
    tb, tf = textbox(slide, Inches(0.55), Inches(6.55), Inches(12.2), Inches(0.32))
    setp(tf, text, size=10, color=ORANGE, first=True)


def card(slide, x, y, w, h, title, lines, accent=BLUE, tsize=15, bsize=12):
    """带标题色条的卡片。"""
    rect(slide, x, y, w, h, fill=LGREY)
    rect(slide, x, y, w, Inches(0.07), fill=accent)
    tb, tf = textbox(slide, x + Inches(0.22), y + Inches(0.22),
                     w - Inches(0.44), h - Inches(0.4))
    setp(tf, title, size=tsize, bold=True, color=accent, first=True, space_after=6)
    for ln in lines:
        setp(tf, ln, size=bsize, color=RGBColor(0x33, 0x39, 0x40), space_after=3)
    return tb


def styled_table(slide, x, y, w, h, data, col_w=None, fsize=11, hsize=11,
                 header_fill=NAVY):
    rows, cols = len(data), len(data[0])
    shp = slide.shapes.add_table(rows, cols, x, y, w, h)
    tbl = shp.table
    if col_w:
        total = sum(col_w)
        for i, cw in enumerate(col_w):
            tbl.columns[i].width = Emu(int(w * cw / total))
    for ri, row in enumerate(data):
        for ci, val in enumerate(row):
            cell = tbl.cell(ri, ci)
            cell.margin_left = cell.margin_right = Inches(0.06)
            cell.margin_top = cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            tf.paragraphs[0].text = ""
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT
            r = p.add_run()
            r.text = str(val)
            r.font.name = FONT
            if ri == 0:
                r.font.size = Pt(hsize)
                r.font.bold = True
                r.font.color.rgb = WHITE
                cell.fill.solid()
                cell.fill.fore_color.rgb = header_fill
            else:
                r.font.size = Pt(fsize)
                r.font.color.rgb = RGBColor(0x2A, 0x30, 0x36)
                cell.fill.solid()
                cell.fill.fore_color.rgb = WHITE if ri % 2 else LGREY
    return tbl


# ============================================================
# 各页
# ============================================================
def s01_cover(prs):
    s = slide_blank(prs)
    rect(s, 0, 0, SW, SH, fill=NAVY)
    rect(s, Inches(0.9), Inches(2.02), Inches(1.5), Inches(0.08), fill=ORANGE)
    tb, tf = textbox(s, Inches(0.9), Inches(1.15), Inches(11.5), Inches(0.4))
    setp(tf, "第八届全球校园人工智能算法精英大赛 · 校内选拔赛", size=14,
         color=RGBColor(0x9C, 0xB4, 0xD0), first=True)
    tb, tf = textbox(s, Inches(0.9), Inches(2.45), Inches(11.8), Inches(1.5))
    setp(tf, TITLE, size=40, bold=True, color=WHITE, first=True, space_after=6)
    setp(tf, "零训练成本的边缘可部署方案", size=19,
         color=RGBColor(0xA8, 0xC8, 0xE8), space_after=0)
    tb, tf = textbox(s, Inches(0.9), Inches(4.85), Inches(11.8), Inches(0.9))
    setp(tf, "参赛赛道：AI+农业算法主题赛道", size=15,
         color=RGBColor(0xC8, 0xD8, 0xE8), first=True, space_after=4)
    setp(tf, "队长：陈麒光　动物科学（动物科学+人工智能双学士学位）", size=13,
         color=RGBColor(0x9C, 0xB4, 0xD0), space_after=0)
    return s


def s02_problem(prs, idx):
    s = slide_blank(prs)
    title_bar(s, "要解决的问题", "疫病早期发现依赖人工巡查，存在三个现实困难", idx)
    items = [
        ("覆盖不足", "饲养员人均看护头数多，难以逐栏逐头细致观察；\n"
                     "夜间与节假日巡查频次下降，而部分疾病恰在此时段加重。",
         BLUE),
        ("主观性强", "行为是否属于异常依赖饲养员个人经验，\n"
                     "不同人判断标准不一致，换人看护后结论可能变化。",
         GREEN),
        ("难以量化", "即使发现异常，也缺少「比平时少了多少」的记录，\n"
                     "难以支撑趋势判断和事后复盘。",
         ORANGE),
    ]
    x = Inches(0.55)
    w = Inches(4.0)
    gap = Inches(0.21)
    for i, (t, d, c) in enumerate(items):
        cx = x + i * (w + gap)
        rect(s, cx, Inches(1.72), w, Inches(2.5), fill=LGREY)
        rect(s, cx, Inches(1.72), w, Inches(0.09), fill=c)
        # 序号圆
        circ = rect(s, cx + Inches(0.26), Inches(1.98), Inches(0.62), Inches(0.62),
                    fill=c, shape=MSO_SHAPE.OVAL)
        ctf = circ.text_frame
        ctf.vertical_anchor = MSO_ANCHOR.MIDDLE
        setp(ctf, str(i + 1), size=20, bold=True, color=WHITE,
             align=PP_ALIGN.CENTER, first=True, space_after=0)
        tb, tf = textbox(s, cx + Inches(1.02), Inches(2.06), w - Inches(1.24),
                         Inches(0.5), anchor=MSO_ANCHOR.MIDDLE)
        setp(tf, t, size=19, bold=True, color=c, first=True, space_after=0)
        tb, tf = textbox(s, cx + Inches(0.26), Inches(2.82), w - Inches(0.52),
                         Inches(1.25))
        for j, ln in enumerate(d.split("\n")):
            setp(tf, ln, size=12.5, color=RGBColor(0x33, 0x39, 0x40),
                 first=(j == 0), space_after=4, line_spacing=1.3)
    # 底部结论
    rect(s, Inches(0.55), Inches(4.55), Inches(12.23), Inches(1.05), fill=LBLUE)
    rect(s, Inches(0.55), Inches(4.55), Inches(0.09), Inches(1.05), fill=BLUE)
    tb, tf = textbox(s, Inches(0.95), Inches(4.72), Inches(11.6), Inches(0.75),
                     anchor=MSO_ANCHOR.MIDDLE)
    setp(tf, "本阶段分析依据 41 篇中文养猪文献与专业课程学习、猪场实习中的现场观察。",
         size=13, bold=True, color=NAVY, first=True, space_after=3)
    setp(tf, "面向养殖从业者的问卷调研尚在进行中，痛点判断属于分析结论，"
             "后续将以问卷数据验证与细化。", size=11.5, color=GREY, space_after=0)
    return s


def s03_entry(prs, idx):
    s = slide_blank(prs)
    title_bar(s, "切入点：把现成的监控画面用起来", None, idx)
    # 左：现状
    rect(s, Inches(0.55), Inches(1.55), Inches(5.95), Inches(3.05), fill=LGREY)
    rect(s, Inches(0.55), Inches(1.55), Inches(5.95), Inches(0.09), fill=GREY)
    tb, tf = textbox(s, Inches(0.85), Inches(1.85), Inches(5.4), Inches(2.5))
    setp(tf, "现状", size=18, bold=True, color=GREY, first=True, space_after=10)
    for ln in ["猪场普遍已安装监控摄像头，图像采集条件具备",
               "但录像基本只用于事后回看",
               "视频数据没有转化成可用于预警的行为指标"]:
        setp(tf, "· " + ln, size=13.5, color=RGBColor(0x33, 0x39, 0x40), space_after=6)
    # 右：本作品
    rect(s, Inches(6.83), Inches(1.55), Inches(5.95), Inches(3.05), fill=LGREEN)
    rect(s, Inches(6.83), Inches(1.55), Inches(5.95), Inches(0.09), fill=GREEN)
    tb, tf = textbox(s, Inches(7.13), Inches(1.85), Inches(5.4), Inches(2.5))
    setp(tf, "本作品", size=18, bold=True, color=GREEN, first=True, space_after=10)
    for ln in ["把现成的监控画面转化成可量化的行为数据",
               "复用已有摄像头，不新增硬件",
               "纯 CPU 推理，不需独立显卡"]:
        setp(tf, "· " + ln, size=13.5, color=RGBColor(0x33, 0x39, 0x40), space_after=6)
    # 中间箭头
    ar = rect(s, Inches(6.42), Inches(2.75), Inches(0.55), Inches(0.5),
              fill=ORANGE, shape=MSO_SHAPE.RIGHT_ARROW)
    # 底部成本结论
    rect(s, Inches(0.55), Inches(4.85), Inches(12.23), Inches(0.95), fill=LORANGE)
    tb, tf = textbox(s, Inches(0.9), Inches(5.0), Inches(11.6), Inches(0.65),
                     anchor=MSO_ANCHOR.MIDDLE)
    setp(tf, "复用已有摄像头 + 纯 CPU 推理，相比部署 GPU 方案可省去数万元设备投入",
         size=15, bold=True, color=ORANGE, first=True, align=PP_ALIGN.CENTER)
    return s


def s04_arch(prs, idx):
    s = slide_blank(prs)
    title_bar(s, "系统结构", "三层结构，每层都有可量化的验证指标", idx)
    layers = [
        ("视觉感知层", "猪只检测　+　设施区域标定", "mAP50 0.94　·　CPU 37 毫秒/张", BLUE),
        ("行为理解层", "设施锚定（空间）+ 位移与面积变化（时序）→ 六类行为",
         "21/21 单帧　·　7/7 时序", GREEN),
        ("应用层", "健康评估　+　疫病辅助诊断　+　用药安全提示",
         "诊断 Top-3 80%　·　禁用药物拦截 4/4", ORANGE),
    ]
    y = Inches(1.62)
    for name, desc, metric, c in layers:
        rect(s, Inches(0.55), y, Inches(2.5), Inches(1.28), fill=c)
        tb, tf = textbox(s, Inches(0.55), y, Inches(2.5), Inches(1.28),
                         anchor=MSO_ANCHOR.MIDDLE)
        setp(tf, name, size=16, bold=True, color=WHITE, align=PP_ALIGN.CENTER,
             first=True, space_after=0)
        rect(s, Inches(3.05), y, Inches(9.73), Inches(1.28), fill=LGREY)
        tb, tf = textbox(s, Inches(3.35), y, Inches(9.2), Inches(1.28),
                         anchor=MSO_ANCHOR.MIDDLE)
        setp(tf, desc, size=14, bold=True, color=RGBColor(0x2A, 0x30, 0x36),
             first=True, space_after=4)
        setp(tf, metric, size=12, color=c, space_after=0)
        if name != "应用层":
            rect(s, Inches(6.6), y + Inches(1.32), Inches(0.32), Inches(0.22),
                 fill=RGBColor(0xC5, 0xCD, 0xD5), shape=MSO_SHAPE.DOWN_ARROW)
        y += Inches(1.62)
    return s


def s05_innovation(prs, idx):
    s = slide_blank(prs)
    title_bar(s, "创新点概览", "三个环节的做法对比：别人怎么做 → 为什么不够 → 我改了什么", idx)
    rows = [
        ("检测环节", "直接用通用预训练检测器",
         "COCO 的 80 个类别中没有猪，实测漏检约 65%",
         "自训单类 YOLOv8n 检测器", "mAP50 0.94", BLUE),
        ("行为识别", "端到端时序动作识别网络",
         "需大规模行为标注视频，且要求 GPU 推理",
         "检测与行为推理拆开，用规则实现", "零标注成本 · 纯 CPU · 每条可解释", GREEN),
        ("设施标定", "再训练一个设施检测器",
         "需要额外标注与训练成本",
         "图形化框选工具，标定一次长期复用", "采食识别提升 24.3%", ORANGE),
    ]
    y = Inches(1.66)
    for name, old, why, mine, gain, c in rows:
        rect(s, Inches(0.55), y, Inches(12.23), Inches(1.52), fill=LGREY)
        rect(s, Inches(0.55), y, Inches(0.09), Inches(1.52), fill=c)
        tb, tf = textbox(s, Inches(0.82), y, Inches(1.35), Inches(1.52),
                         anchor=MSO_ANCHOR.MIDDLE)
        setp(tf, name, size=15, bold=True, color=c, first=True, space_after=0)
        # 三段
        segs = [(Inches(2.3), "别人怎么做", old, GREY),
                (Inches(5.55), "为什么不够", why, RED),
                (Inches(8.85), "本作品做法", mine + "　→　" + gain, c)]
        for sx, lab, val, col in segs:
            tb, tf = textbox(s, sx, y + Inches(0.22), Inches(2.9), Inches(1.1))
            setp(tf, lab, size=10.5, color=RGBColor(0x8A, 0x92, 0x9A), first=True,
                 space_after=3)
            setp(tf, val, size=12, bold=(col is c), color=col, space_after=0,
                 line_spacing=1.2)
        y += Inches(1.68)
    return s


def s06_roadmap(prs, idx):
    s = slide_blank(prs)
    title_bar(s, "实施路线", "六个阶段，每阶段有明确产出", idx)
    stages = [
        ("S1", "检测器训练", "公开数据集 500 张\nCPU 约 40 分钟", BLUE),
        ("S2", "行为识别", "六类行为判据\n规则引擎", GREEN),
        ("S3", "标定工具", "图形化框选\n归一化坐标配置", ORANGE),
        ("S4", "疾病诊断", "41 篇文献知识库\n用药安全层", BLUE),
        ("S5", "评测", "合成场景 + 帧序列\n+ 真实图片", GREEN),
        ("S6", "材料整理", "作品方案、PPT\n代码与数据归档", ORANGE),
    ]
    x0 = Inches(0.55)
    w = Inches(1.87)
    gap = Inches(0.165)
    for i, (code, name, desc, c) in enumerate(stages):
        cx = x0 + i * (w + gap)
        rect(s, cx, Inches(2.0), w, Inches(2.85), fill=LGREY)
        rect(s, cx, Inches(2.0), w, Inches(0.09), fill=c)
        circ = rect(s, cx + Inches(0.6), Inches(2.26), Inches(0.67), Inches(0.67),
                    fill=c, shape=MSO_SHAPE.OVAL)
        ctf = circ.text_frame
        ctf.vertical_anchor = MSO_ANCHOR.MIDDLE
        setp(ctf, code, size=15, bold=True, color=WHITE, align=PP_ALIGN.CENTER,
             first=True, space_after=0)
        tb, tf = textbox(s, cx + Inches(0.14), Inches(3.12), w - Inches(0.28),
                         Inches(0.42))
        setp(tf, name, size=14, bold=True, color=c, align=PP_ALIGN.CENTER,
             first=True, space_after=0)
        tb, tf = textbox(s, cx + Inches(0.14), Inches(3.62), w - Inches(0.28),
                         Inches(1.1))
        for j, ln in enumerate(desc.split("\n")):
            setp(tf, ln, size=11, color=RGBColor(0x40, 0x46, 0x4C),
                 align=PP_ALIGN.CENTER, first=(j == 0), space_after=2)
        if i < 5:
            rect(s, cx + w + Inches(0.005), Inches(3.24), Inches(0.155), Inches(0.3),
                 fill=RGBColor(0xC5, 0xCD, 0xD5), shape=MSO_SHAPE.RIGHT_ARROW)
    rect(s, Inches(0.55), Inches(5.2), Inches(12.23), Inches(0.95), fill=LBLUE)
    tb, tf = textbox(s, Inches(0.95), Inches(5.35), Inches(11.5), Inches(0.65),
                     anchor=MSO_ANCHOR.MIDDLE)
    setp(tf, "S1 至 S5 的全部结果均保存在成果包 04_实验数据 目录，可逐项复现。",
         size=13, bold=True, color=NAVY, first=True, space_after=0)
    return s


def s07_detector_why(prs, idx):
    s = slide_blank(prs)
    title_bar(s, "检测器为什么必须自己训练",
              "通用检测器所用的 COCO 数据集，80 个类别中有鸟、猫、狗、马、羊、牛等，唯独没有猪", idx)
    # 左：文字与结论
    tb, tf = textbox(s, Inches(0.55), Inches(1.72), Inches(5.35), Inches(0.4))
    setp(tf, "实测对比", size=17, bold=True, color=NAVY, first=True, space_after=0)
    rows = [("通用预训练检测器", "检出 8 个目标，判为 pig 的 0 个", RED),
            ("自训单类检测器", "检出 24 头，与人工标注 23 头一致", GREEN)]
    y = Inches(2.24)
    for lab, val, col in rows:
        rect(s, Inches(0.55), y, Inches(5.35), Inches(0.92), fill=LGREY)
        rect(s, Inches(0.55), y, Inches(0.08), Inches(0.92), fill=col)
        tb2, tf2 = textbox(s, Inches(0.82), y + Inches(0.12), Inches(4.95), Inches(0.72))
        setp(tf2, lab, size=12, color=GREY, first=True, space_after=2)
        setp(tf2, val, size=14, bold=True, color=col, space_after=0)
        y += Inches(1.04)
    # 做法说明
    tb3, tf3 = textbox(s, Inches(0.55), Inches(4.42), Inches(5.35), Inches(1.6))
    setp(tf3, "做法", size=14, bold=True, color=NAVY, first=True, space_after=5)
    setp(tf3, "以 COCO 预训练权重为起点，把检测头类别数由 80 改为 1，"
              "在公开猪只检测数据集 PigBench 上微调。", size=11.5,
         color=RGBColor(0x40, 0x46, 0x4C), space_after=4, line_spacing=1.3)
    setp(tf3, "训练集 500 张，验证集 80 张，图像尺寸 640，批大小 8，共 15 轮，"
              "全程 CPU 约 40 分钟。", size=11.5, color=RGBColor(0x40, 0x46, 0x4C),
         space_after=4, line_spacing=1.3)
    setp(tf3, "此外发现：有开源仓库声称提供猪只检测权重，实测其检测头类别数仍为 80、"
              "训练数据声明为 COCO，实为通用模型改名。使用第三方权重前需核验这两项。",
         size=10.5, color=GREY, space_after=0, line_spacing=1.3)
    # 右：真实对比图
    img = r"E:\harness\aic\ppt_assets\det_compare.png"
    if os.path.isfile(img):
        pic = s.shapes.add_picture(img, Inches(6.18), Inches(1.78), width=Inches(6.6))
        tb4, tf4 = textbox(s, Inches(6.18), Inches(1.78) + pic.height + Inches(0.08),
                           Inches(6.6), Inches(0.5))
        setp(tf4, "同一张猪舍照片的两种检测结果（真实模型输出，非示意）",
             size=10.5, color=GREY, first=True, space_after=0)
    return s


def s08_detection(prs, idx):
    s = slide_blank(prs)
    title_bar(s, "检测结果", "公开数据集 PigBench 测试集：80 张图 / 1730 个标注框", idx)
    metrics = [
        ("mAP50", f"{DET.get('map50', 0):.4f}", BLUE),
        ("mAP50-95", f"{DET.get('map5095', 0):.4f}", BLUE),
        ("Precision", f"{DET.get('precision', 0):.4f}", GREEN),
        ("Recall", f"{DET.get('recall', 0):.4f}", GREEN),
    ]
    x = Inches(0.55)
    w = Inches(2.95)
    gap = Inches(0.145)
    for i, (name, val, c) in enumerate(metrics):
        cx = x + i * (w + gap)
        rect(s, cx, Inches(1.72), w, Inches(1.5), fill=LGREY)
        rect(s, cx, Inches(1.72), w, Inches(0.08), fill=c)
        tb, tf = textbox(s, cx, Inches(1.95), w, Inches(0.4))
        setp(tf, name, size=13.5, color=GREY, align=PP_ALIGN.CENTER, first=True,
             space_after=0)
        tb, tf = textbox(s, cx, Inches(2.4), w, Inches(0.62))
        setp(tf, val, size=30, bold=True, color=c, align=PP_ALIGN.CENTER,
             first=True, space_after=0)
    data = [
        ["项目", "数值", "说明"],
        ["推理速度", "37 毫秒 / 张", "纯 CPU（14 线程），无需独立显卡"],
        ["模型体积", "5.94 MB（.pt）／ 11.70 MB（.onnx）",
         "同时提供可加载与可脱离框架部署两种格式"],
        ["训练轮次", f"{DET.get('epoch', 0)} 轮", "mAP50 由第 1 轮 0.832 升至第 15 轮，"
                                               "三项损失单调下降"],
    ]
    styled_table(s, Inches(0.55), Inches(3.5), Inches(12.23), Inches(2.0),
                 data, col_w=[2.2, 3.8, 6.2], fsize=12.5, hsize=12.5)
    note_src(s, "以上为公开数据集上的真实指标，可用成果包中的评测脚本复现。")
    return s


def s09_behavior_why(prs, idx):
    s = slide_blank(prs)
    title_bar(s, "行为为什么不能由检测器直接输出",
              "行为属于时序动作，不是物体的静态属性", idx)
    rect(s, Inches(0.55), Inches(1.68), Inches(12.23), Inches(1.15), fill=LBLUE)
    tb, tf = textbox(s, Inches(0.95), Inches(1.82), Inches(11.5), Inches(0.9),
                     anchor=MSO_ANCHOR.MIDDLE)
    setp(tf, "低头可能是采食，也可能是嗅探；「争斗」与「并排休息」在单帧上非常相似；"
             "「行走」必须依靠连续帧的位移才能判断。", size=14, bold=True,
         color=NAVY, first=True, space_after=4)
    setp(tf, "因此本作品把行为拆成两部分：设施锚定（空间）+ 位移与面积变化（时序），"
             "每条判定都给出所依据的特征与阈值。", size=12.5, color=GREY, space_after=0)
    data = [
        ["行为", "判据", "证据类型"],
        ["采食 / 饮水", "目标框与食槽、饮水器区域的重叠比例 ≥ 0.35", "设施锚定（空间）"],
        ["争斗", "静态图：IoU ≥ 0.35　视频：IoU ≥ 0.15 且双方均有位移", "时空联合（双阈值）"],
        ["行走", "相邻帧归一化位移 ≥ 0.012，或时间窗累计位移 ≥ 0.05", "时序"],
        ["休息 / 站立", "框面积相对缩小 ≥ 15% 判为卧倒，否则判为站立", "姿态（时序）"],
    ]
    styled_table(s, Inches(0.55), Inches(3.05), Inches(12.23), Inches(2.3),
                 data, col_w=[2.6, 7.2, 2.9], fsize=12.5, hsize=12.5)
    note_src(s, "实现中有三处判据经过调整，详见第 10 页。")
    return s


def s10_behavior_iter(prs, idx):
    s = slide_blank(prs)
    title_bar(s, "三处判据经过调整", "这些问题是实际跑数据时暴露出来的", idx)
    items = [
        ("设施锚定优先于框重叠",
         "最初把「争斗」排在「采食」之前，结果多头同时采食时，"
         "因目标框相邻重叠被全部判成争斗。",
         "设施锚定有明确的空间锚点，可信度高于框重叠，因此调整优先级。", BLUE),
        ("姿态变化优先于运动判据",
         "猪由站立转为卧倒时，框面积明显缩小但位移很小，"
         "先判断运动会被误判为「站立」。",
         "改为优先比较面积变化，再判断位移。", GREEN),
        ("争斗采用双阈值",
         "实测真实争斗的 IoU 约 0.17，密集采食时的正常重叠约 0.15 至 0.32，"
         "两者分布本身重叠，单一阈值无法分开。阈值取 0.12 时争斗占比达 20.3%，"
         "远超猪群实际水平；取 0.35 时会漏检真实争斗。",
         "静态图用保守阈值 0.35；视频放宽到 0.15，并要求双方均有位移作为额外验证。",
         ORANGE),
    ]
    y = Inches(1.68)
    for t, prob, fix, c in items:
        rect(s, Inches(0.55), y, Inches(12.23), Inches(1.6), fill=LGREY)
        rect(s, Inches(0.55), y, Inches(0.09), Inches(1.6), fill=c)
        tb, tf = textbox(s, Inches(0.85), y + Inches(0.18), Inches(11.7), Inches(1.3))
        setp(tf, t, size=15, bold=True, color=c, first=True, space_after=4)
        setp(tf, "问题：" + prob, size=11.5, color=RGBColor(0x40, 0x46, 0x4C),
             space_after=3, line_spacing=1.25)
        setp(tf, "调整：" + fix, size=11.5, bold=True, color=NAVY, space_after=0,
             line_spacing=1.25)
        y += Inches(1.72)
    return s


def s11_behavior_result(prs, idx):
    s = slide_blank(prs)
    title_bar(s, "行为识别结果", None, idx)
    # 左：单帧
    rect(s, Inches(0.55), Inches(1.62), Inches(5.95), Inches(2.5), fill=LGREY)
    rect(s, Inches(0.55), Inches(1.62), Inches(5.95), Inches(0.08), fill=BLUE)
    tb, tf = textbox(s, Inches(0.85), Inches(1.88), Inches(5.4), Inches(0.5))
    setp(tf, "单帧行为分类", size=17, bold=True, color=BLUE, first=True, space_after=0)
    tb, tf = textbox(s, Inches(0.85), Inches(2.42), Inches(2.5), Inches(0.8))
    setp(tf, "21 / 21", size=32, bold=True, color=BLUE, first=True, space_after=0)
    tb, tf = textbox(s, Inches(3.4), Inches(2.5), Inches(2.9), Inches(0.7))
    setp(tf, "准确率 100%", size=14, bold=True, color=NAVY, first=True, space_after=3)
    setp(tf, "宏平均 F1 = 1.000", size=12, color=GREY, space_after=0)
    tb, tf = textbox(s, Inches(0.85), Inches(3.28), Inches(5.4), Inches(0.7))
    setp(tf, "六个场景：全群采食、混合行为、争斗重叠、高密度拥挤、"
             "空栏负样本、有人作业", size=11.5, color=RGBColor(0x40, 0x46, 0x4C),
         first=True, space_after=0, line_spacing=1.25)
    # 右：时序
    rect(s, Inches(6.83), Inches(1.62), Inches(5.95), Inches(2.5), fill=LGREY)
    rect(s, Inches(6.83), Inches(1.62), Inches(5.95), Inches(0.08), fill=GREEN)
    tb, tf = textbox(s, Inches(7.13), Inches(1.88), Inches(5.4), Inches(0.5))
    setp(tf, "时序行为判定", size=17, bold=True, color=GREEN, first=True, space_after=0)
    tb, tf = textbox(s, Inches(7.13), Inches(2.42), Inches(2.5), Inches(0.8))
    setp(tf, "7 / 7", size=32, bold=True, color=GREEN, first=True, space_after=0)
    tb, tf = textbox(s, Inches(9.68), Inches(2.5), Inches(2.9), Inches(0.7))
    setp(tf, "准确率 100%", size=14, bold=True, color=NAVY, first=True, space_after=3)
    setp(tf, "5 个序列 / 7 个检查点", size=12, color=GREY, space_after=0)
    tb, tf = textbox(s, Inches(7.13), Inches(3.28), Inches(5.4), Inches(0.7))
    setp(tf, "静止站立、匀速行走、站立转卧倒、持续争斗、采食后离开",
         size=11.5, color=RGBColor(0x40, 0x46, 0x4C), first=True, space_after=0,
         line_spacing=1.25)
    # 底部警示
    rect(s, Inches(0.55), Inches(4.35), Inches(12.23), Inches(1.1), fill=LORANGE)
    rect(s, Inches(0.55), Inches(4.35), Inches(0.09), Inches(1.1), fill=ORANGE)
    tb, tf = textbox(s, Inches(0.95), Inches(4.5), Inches(11.5), Inches(0.8),
                     anchor=MSO_ANCHOR.MIDDLE)
    setp(tf, "数据性质说明：以上两项指标来自合成场景与合成帧序列，"
             "作用是验证规则逻辑是否正确，不代表真实场景下的行为识别精度。",
         size=12.5, bold=True, color=ORANGE, first=True, space_after=3)
    setp(tf, "真实行为精度需要人工标注真实视频片段后才能给出，已列入近期计划。",
         size=11.5, color=GREY, space_after=0)
    note_src(s, "数据来源：eval_behavior_synthetic.json / eval_temporal_synthetic.json（合成数据）")
    return s


def s12_calibration(prs, idx):
    s = slide_blank(prs)
    title_bar(s, "设施区域标定", "食槽与饮水器的位置，是采食、饮水两个行为的空间锚点", idx)
    inf, cal = RC["inferred"], RC["calibrated"]
    data = [
        ["行为", "标定前（布局先验推断）", "标定后（人工框选）", "变化"],
        ["采食", f"{inf.get('eating', 0):.1f}%", f"{cal.get('eating', 0):.1f}%",
         f"+{cal.get('eating', 0) - inf.get('eating', 0):.1f}%"],
        ["争斗", f"{inf.get('aggressive', 0):.1f}%", f"{cal.get('aggressive', 0):.1f}%",
         f"{cal.get('aggressive', 0) - inf.get('aggressive', 0):.1f}%"],
        ["饮水", f"{inf.get('drinking', 0):.1f}%", f"{cal.get('drinking', 0):.1f}%",
         f"{cal.get('drinking', 0) - inf.get('drinking', 0):.1f}%"],
        ["站立", f"{inf.get('standing', 0):.1f}%", f"{cal.get('standing', 0):.1f}%",
         f"{cal.get('standing', 0) - inf.get('standing', 0):.1f}%"],
    ]
    styled_table(s, Inches(0.55), Inches(1.94), Inches(7.4), Inches(2.6),
                 data, col_w=[1.5, 2.6, 2.4, 1.5], fsize=12.5, hsize=12)
    # 右侧说明
    rect(s, Inches(8.25), Inches(1.94), Inches(4.53), Inches(2.6), fill=LGREEN)
    rect(s, Inches(8.25), Inches(1.94), Inches(4.53), Inches(0.08), fill=GREEN)
    tb, tf = textbox(s, Inches(8.52), Inches(2.16), Inches(4.0), Inches(2.2))
    setp(tf, "标定工具", size=15, bold=True, color=GREEN, first=True, space_after=8)
    for ln in ["在照片上拖拽框选食槽、饮水器、保温区",
               "导出归一化坐标（0~1）配置",
               "同一份配置可跨分辨率复用，换相机不会错位",
               "程序自动查找并应用配置，无需手动指定"]:
        setp(tf, "· " + ln, size=11.5, color=RGBColor(0x33, 0x39, 0x40), space_after=5,
             line_spacing=1.2)
    rect(s, Inches(0.55), Inches(4.78), Inches(12.23), Inches(1.2), fill=LBLUE)
    rect(s, Inches(0.55), Inches(4.78), Inches(0.09), Inches(1.2), fill=BLUE)
    tb, tf = textbox(s, Inches(0.95), Inches(4.92), Inches(11.5), Inches(0.95),
                     anchor=MSO_ANCHOR.MIDDLE)
    setp(tf, f"对比方式：{RC.get('n_images')} 张真实猪舍图片、{RC.get('n_targets')} 个目标，"
             "使用同一份检测结果，只切换区域来源。", size=13, bold=True, color=NAVY,
         first=True, space_after=4)
    setp(tf, "这是行为部分唯一来自真实猪舍图片的数据，也是方案可落地性的直接证据。",
         size=11.5, color=GREY, space_after=0)
    note_src(s, "数据来源：region_calibration_effect.json（真实猪舍图片）")
    return s


def s13_safety(prs, idx):
    s = slide_blank(prs)
    title_bar(s, "用药安全层", "安全底线独立于诊断推理，不交给概率模型判断", idx)
    rules = [
        ("禁用药物扫描与阻断", "扫描用户原始输入中的禁用药物名称，命中即阻断输出，"
                              "不依赖知识库检索结果。"),
        ("强制休药期核对", "任何用药建议都必须附带休药期核对要求，"
                          "提示以标签说明书与官方公告为准。"),
        ("证据不足时降级", "当症状证据不足以支持判断时，只提示方向，"
                          "不给出具体用药建议。"),
    ]
    y = Inches(1.7)
    for i, (t, d) in enumerate(rules):
        rect(s, Inches(0.55), y, Inches(7.7), Inches(1.32), fill=LGREY)
        rect(s, Inches(0.55), y, Inches(0.09), Inches(1.32), fill=RED)
        tb, tf = textbox(s, Inches(0.88), y + Inches(0.16), Inches(7.2), Inches(1.05))
        setp(tf, f"{i + 1}. {t}", size=14.5, bold=True, color=RED, first=True,
             space_after=4)
        setp(tf, d, size=11.5, color=RGBColor(0x40, 0x46, 0x4C), space_after=0,
             line_spacing=1.25)
        y += Inches(1.44)
    rect(s, Inches(8.55), Inches(1.7), Inches(4.23), Inches(4.04), fill=LORANGE)
    rect(s, Inches(8.55), Inches(1.7), Inches(4.23), Inches(0.08), fill=ORANGE)
    tb, tf = textbox(s, Inches(8.82), Inches(1.94), Inches(3.7), Inches(3.6))
    setp(tf, "拦截测试", size=16, bold=True, color=ORANGE, first=True, space_after=10)
    setp(tf, "4 / 4", size=34, bold=True, color=ORANGE, space_after=6)
    setp(tf, "构造含禁用药物的输入，全部被正确拦截",
         size=12, color=RGBColor(0x40, 0x46, 0x4C), space_after=12, line_spacing=1.3)
    setp(tf, "禁用药物清单依据农业农村部相关公告整理。",
         size=11.5, color=GREY, space_after=0, line_spacing=1.3)
    note_src(s, "数据来源：eval_results.json（安全层拦截测试）")
    return s


def s14_diagnosis(prs, idx):
    s = slide_blank(prs)
    title_bar(s, "疾病辅助诊断", None, idx)
    # 左：知识库
    rect(s, Inches(0.55), Inches(1.62), Inches(4.5), Inches(4.1), fill=LGREY)
    rect(s, Inches(0.55), Inches(1.62), Inches(4.5), Inches(0.08), fill=BLUE)
    tb, tf = textbox(s, Inches(0.85), Inches(1.86), Inches(3.9), Inches(3.7))
    setp(tf, "知识库", size=17, bold=True, color=BLUE, first=True, space_after=10)
    for lab, val in [("文献", f"{KB['docs']} 篇中文养猪文献"),
                     ("疾病", f"{KB['diseases']} 种"),
                     ("症状关联", f"{KB['symptoms']} 条")]:
        setp(tf, lab, size=11.5, color=GREY, space_after=1)
        setp(tf, val, size=17, bold=True, color=NAVY, space_after=9)
    setp(tf, "每条症状关联均保留原文出处（文献编号、期刊年份、原句）以便核对。",
         size=11.5, color=RGBColor(0x40, 0x46, 0x4C), space_after=0, line_spacing=1.3)
    # 右上：指标
    metrics = [("Top-1 命中率", f"{DX.get('top1', 0):.1%}"),
               ("Top-3 命中率", f"{DX.get('top3', 0):.1%}"),
               ("MRR", f"{DX.get('mrr', 0):.3f}")]
    x = Inches(5.35)
    w = Inches(2.42)
    for i, (n, v) in enumerate(metrics):
        cx = x + i * (w + Inches(0.195))
        rect(s, cx, Inches(1.62), w, Inches(1.35), fill=LGREY)
        rect(s, cx, Inches(1.62), w, Inches(0.08), fill=GREEN)
        tb, tf = textbox(s, cx, Inches(1.82), w, Inches(0.35))
        setp(tf, n, size=11.5, color=GREY, align=PP_ALIGN.CENTER, first=True,
             space_after=0)
        tb, tf = textbox(s, cx, Inches(2.22), w, Inches(0.6))
        setp(tf, v, size=26, bold=True, color=GREEN, align=PP_ALIGN.CENTER,
             first=True, space_after=0)
    # 右下：分层
    rect(s, Inches(5.35), Inches(3.14), Inches(7.43), Inches(2.58), fill=LBLUE)
    rect(s, Inches(5.35), Inches(3.14), Inches(7.43), Inches(0.08), fill=NAVY)
    tb, tf = textbox(s, Inches(5.65), Inches(3.38), Inches(6.9), Inches(2.2))
    setp(tf, "分层分析：瓶颈在知识库覆盖，不在算法", size=15, bold=True,
         color=NAVY, first=True, space_after=8)
    setp(tf, f"· 知识库证据充分的 {DX.get('strong_n')} 个病例，Top-3 命中率 "
             f"{DX.get('strong_top3', 0):.1%}", size=12.5,
         color=RGBColor(0x33, 0x39, 0x40), space_after=5)
    setp(tf, f"· 缺少专论文献的 {DX.get('weak_n')} 个病例，Top-3 命中率 "
             f"{DX.get('weak_top3', 0):.1%}", size=12.5,
         color=RGBColor(0x33, 0x39, 0x40), space_after=8)
    setp(tf, "说明：后续补充专论文献即可提升命中率，这是可预期的改进路径。",
         size=11.5, color=GREY, space_after=0, line_spacing=1.3)
    note_src(s, "数据来源：eval_results.json（15 个自建评测用例）")
    return s


def s15_limits(prs, idx):
    s = slide_blank(prs)
    title_bar(s, "不足与改进方向", None, idx)
    items = [
        ("行为评测以合成数据为主", "不代表真实场景精度",
         "近期采集真实猪舍视频，人工标注行为片段，建立真实评测集"),
        ("设施区域需要人工标定一次", "尚未做到全自动",
         "探索半自动标定，并提供典型栏舍的配置模板"),
        ("没有个体识别，只能做群体级预警", "无法定位到具体某一头猪",
         "中期引入个体重识别，把预警粒度从栏细化到头"),
        ("健康评估基线尚未现场标定", "当前使用的是示例值",
         "接入真实场数据重新标定基线，并禁止单帧下给出评估结论"),
    ]
    y = Inches(1.66)
    for prob, why, plan in items:
        rect(s, Inches(0.55), y, Inches(12.23), Inches(1.16), fill=LGREY)
        rect(s, Inches(0.55), y, Inches(0.09), Inches(1.16), fill=RED)
        tb, tf = textbox(s, Inches(0.85), y + Inches(0.13), Inches(5.3), Inches(0.9))
        setp(tf, prob, size=13.5, bold=True, color=RED, first=True, space_after=3)
        setp(tf, why, size=11, color=GREY, space_after=0)
        ar = rect(s, Inches(6.28), y + Inches(0.4), Inches(0.42), Inches(0.36),
                  fill=RGBColor(0xB8, 0xC2, 0xCC), shape=MSO_SHAPE.RIGHT_ARROW)
        tb, tf = textbox(s, Inches(6.9), y + Inches(0.13), Inches(5.7), Inches(0.9),
                         anchor=MSO_ANCHOR.MIDDLE)
        setp(tf, plan, size=12.5, color=GREEN, first=True, space_after=0,
             line_spacing=1.25)
        y += Inches(1.28)
    return s


def s16_plan(prs, idx):
    s = slide_blank(prs)
    title_bar(s, "后续计划", None, idx)
    plans = [
        ("近期", "1 个月内", [
            "采集真实猪舍视频，人工标注行为片段，建立真实行为评测集",
            "引入 ByteTrack，改进跨帧关联的稳定性",
        ], BLUE),
        ("中期", "3 至 6 个月", [
            "引入个体重识别，实现个体级行为时长统计与自身历史基线对比",
            "训练数据由 500 张扩充到全部 2682 张，并延长训练轮数",
        ], GREEN),
        ("远期", "1 年", [
            "接入猪场生产管理系统，把行为数据与饲喂记录、生产成绩联合研判",
            "扩展行为类别至发情鉴定、跛行检测",
            "探索边缘设备端侧部署",
        ], ORANGE),
    ]
    x = Inches(0.55)
    w = Inches(4.0)
    gap = Inches(0.21)
    for i, (name, period, lines, c) in enumerate(plans):
        cx = x + i * (w + gap)
        rect(s, cx, Inches(1.68), w, Inches(4.05), fill=LGREY)
        rect(s, cx, Inches(1.68), w, Inches(0.09), fill=c)
        tb, tf = textbox(s, cx + Inches(0.28), Inches(1.94), w - Inches(0.56),
                         Inches(0.7))
        setp(tf, name, size=20, bold=True, color=c, first=True, space_after=2)
        setp(tf, period, size=11.5, color=GREY, space_after=0)
        tb, tf = textbox(s, cx + Inches(0.28), Inches(2.85), w - Inches(0.56),
                         Inches(2.7))
        for j, ln in enumerate(lines):
            setp(tf, "· " + ln, size=12, color=RGBColor(0x33, 0x39, 0x40),
                 first=(j == 0), space_after=9, line_spacing=1.3)
    return s


def s17_summary(prs, idx):
    s = slide_blank(prs)
    rect(s, 0, 0, SW, SH, fill=NAVY)
    rect(s, Inches(1.0), Inches(2.06), Inches(1.5), Inches(0.08), fill=ORANGE)
    tb, tf = textbox(s, Inches(1.0), Inches(1.2), Inches(11.3), Inches(0.4))
    setp(tf, "总结", size=15, color=RGBColor(0x9C, 0xB4, 0xD0), first=True)
    tb, tf = textbox(s, Inches(1.0), Inches(2.5), Inches(11.3), Inches(1.6))
    setp(tf, "把猪场已有的监控画面，", size=30, bold=True, color=WHITE,
         first=True, space_after=6)
    setp(tf, "转化为可量化、可预警的行为数据。", size=30, bold=True, color=WHITE,
         space_after=0)
    tb, tf = textbox(s, Inches(1.0), Inches(4.45), Inches(11.3), Inches(1.4))
    for ln in ["复用现有硬件，不新增设备投入",
               "纯 CPU 运行，不需要独立显卡",
               "每条判定都给出依据，饲养员知道该不该采信"]:
        setp(tf, "· " + ln, size=15, color=RGBColor(0xC8, 0xD8, 0xE8),
             first=(ln.startswith("复用")), space_after=7)
    return s


# ============================================================
def main():
    prs = Presentation()
    prs.slide_width = SW
    prs.slide_height = SH

    s01_cover(prs)
    builders = [s02_problem, s03_entry, s04_arch, s05_innovation, s06_roadmap,
                s07_detector_why, s08_detection, s09_behavior_why, s10_behavior_iter,
                s11_behavior_result, s12_calibration, s13_safety, s14_diagnosis,
                s15_limits, s16_plan]
    for i, fn in enumerate(builders):
        fn(prs, i + 2)
    s17_summary(prs, 17)

    os.makedirs(OUT_DIR, exist_ok=True)
    prs.save(OUT)
    print(f"已生成 {OUT}（{len(prs.slides.__iter__.__self__._sldIdLst)} 页，"
          f"{os.path.getsize(OUT)/1024:.0f} KB）")
    return OUT


if __name__ == "__main__":
    main()
