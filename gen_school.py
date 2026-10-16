# -*- coding: utf-8 -*-
"""生成校赛材料（方案二：知识驱动智能体）：
1) 作品方案书_问题清单与修改建议.docx
2) AIC2026_校赛作品方案_生猪领域知识智能体.docx
"""
import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

OUT = r"E:\harness\aic"
BODY = "宋体"
HEI = "黑体"
RED = RGBColor(0xC0, 0x00, 0x00)
GREEN = RGBColor(0x1F, 0x6F, 0x3C)


def set_run(run, size=12, bold=False, font=BODY, color=None):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = font
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font)
    if color:
        run.font.color.rgb = color


def para(doc, text="", size=12, bold=False, font=BODY, align=None,
         first_indent=True, space_after=6, line_spacing=1.0, color=None):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.line_spacing = line_spacing
    if first_indent:
        pf.first_line_indent = Pt(size * 2)
    if text:
        set_run(p.add_run(text), size=size, bold=bold, font=font, color=color)
    return p


def h1(doc, text):
    return para(doc, text, size=16, bold=True, font=HEI, first_indent=False,
                space_after=8, line_spacing=1.4)


def h2(doc, text):
    return para(doc, text, size=14, bold=True, font=HEI, first_indent=False,
                space_after=6)


def h3(doc, text):
    return para(doc, text, size=12, bold=True, font=HEI, first_indent=False,
                space_after=4)


def bullet(doc, text, size=12, indent=0.74):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Cm(indent)
    pf.space_after = Pt(3)
    pf.line_spacing = 1.0
    set_run(p.add_run(text), size=size)
    return p


def table(doc, rows, widths=None, header=True, size=9.5):
    ncols = len(rows[0])
    if widths is None:
        widths = [15.0 / ncols] * ncols
    if len(widths) != ncols:
        raise ValueError(f"widths {len(widths)} != {ncols}")
    for ri, r in enumerate(rows):
        if len(r) != ncols:
            raise ValueError(f"row {ri} has {len(r)} cols, need {ncols}: {str(r)[:80]}")
    twips = [int(round(w * 567)) for w in widths]

    t = doc.add_table(rows=0, cols=ncols)
    t.style = "Table Grid"
    t.autofit = False
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    tblPr = t._tbl.tblPr
    tblPr.append(tblPr.makeelement(qn("w:tblW"), {qn("w:type"): "pct", qn("w:w"): "5000"}))
    tblPr.append(tblPr.makeelement(qn("w:tblLayout"), {qn("w:type"): "fixed"}))
    grid = t._tbl.find(qn("w:tblGrid"))
    for gc, tw in zip(grid.findall(qn("w:gridCol")), twips):
        gc.set(qn("w:w"), str(tw))

    for ri, row in enumerate(rows):
        cells = t.add_row().cells
        for ci, val in enumerate(row):
            cells[ci].width = Cm(widths[ci])
            cells[ci].text = ""
            p = cells[ci].paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.0
            set_run(p.add_run(str(val)), size=size, bold=(header and ri == 0))
    return t


def base_page(doc):
    for s in doc.sections:
        s.page_width = Cm(21.0)
        s.page_height = Cm(29.7)
        s.top_margin = Cm(2.5)
        s.bottom_margin = Cm(2.5)
        s.left_margin = Cm(3.0)
        s.right_margin = Cm(3.0)
        s.header_distance = Cm(1.5)
        s.footer_distance = Cm(1.5)


def add_footer(doc, text):
    for s in doc.sections:
        p = s.footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run(p.add_run(text), size=9)


# ============================================================
# 文件 1：问题清单与修改建议
# ============================================================
def build_issues():
    doc = Document()
    base_page(doc)
    doc.styles["Normal"].font.name = BODY
    doc.styles["Normal"]._element.rPr.rFonts.set(qn("w:eastAsia"), BODY)

    para(doc, "《作品方案书》问题清单与逐条修改建议", size=18, bold=True, font=HEI,
         align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False, space_after=4)
    para(doc, "针对「基于 YOLOv8 的猪行为智能识别与健康监测系统」现有材料",
         size=12, align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False, space_after=4)
    para(doc, "编制日期：2026年10月2日｜校赛提交截止：2026年10月7日 20:00",
         size=10.5, align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False,
         space_after=14, color=RED)

    para(doc, "说明：本文档逐条列出需要修改的问题，分「合规红线」「学术诚信」「方法论」"
              "「内部一致性」四类，按严重程度排序。每条给出定位、问题、具体改法。"
              "先改完第 1 类和第 2 类，这两类会直接导致取消资格。",
         first_indent=False, size=11)
    para(doc, "★ 重要：本文档为内部自查用，其中出现的学校与学院名称均为「引用待删除的原文」，"
              "目的是帮你定位。本文档本身不要作为参赛材料提交。",
         first_indent=False, size=11, bold=True, color=RED)

    # ---------- 一 ----------
    h1(doc, "一、合规红线（必须改，否则可能取消参赛资格）")
    para(doc, "依据大赛《竞赛规则》：「为保证评审工作的公平、公正性，大赛作品材料"
              "（技术方案、演示视频、答辩 PPT 等）中均不得出现参赛团队所在学校名称"
              "与指导教师信息。」校赛亦参照大赛正式作品要求执行。", first_indent=False)
    table(doc, [
        ["#", "需清理的内容", "出现位置", "处理动作"],
        ["1-1", "「学校：中国农业大学」「学院：动物科学技术学院」",
         "README.md 第 146-147 行", "整块删除，只保留 QQ 群号"],
        ["1-2", "「中国农业大学动物科学技术学院」", "作品方案书 第 342 行（指导教师表）", "整行删除"],
        ["1-3", "「动物科学技术学院 / 动物科学」", "作品方案书 第 334、336、342 行（团队表）",
         "改为「动物科学相关专业」或直接写「队员A／队员B」，不写学院与学校"],
        ["1-4", "「中国农业大学、华中农业大学、浙江大学等高校」",
         "作品方案书 第 51 行", "删掉机构名。学术综述应引用具体论文，而不是点机构名"],
        ["1-5", "文档属性中的作者、单位", "所有 docx / pptx / pdf 文件",
         "另存后检查「文件-信息」，清空作者与单位；导出 PDF 后再检查一次"],
        ["1-6", "演示视频画面中的校徽、校名、门牌、实验服标识",
         "演示视频", "录制时避开；有露出的画面做模糊或裁剪"],
    ], widths=[0.90, 4.60, 4.50, 5.00], size=9)

    para(doc, "★ 建议做法：提交前用 Word 的「查找」功能，全文搜索「农业」「大学」"
              "「学院」「指导」四个关键词，逐个确认。这一步花 10 分钟，能避免致命失误。",
         bold=True, first_indent=False, color=RED)

    # ---------- 二 ----------
    doc.add_page_break()
    h1(doc, "二、学术诚信问题（必须改）")
    para(doc, "这是最危险的一类。现有材料把「还没做过的实验」写成了「已经做完的实验」，"
              "并且把通用指标当作本项目结果。评委只要追问一句「这个数从哪来」，就会当场暴露。",
         first_indent=False)

    h2(doc, "2-1　把 COCO 通用性能当成自己的实验结果")
    para(doc, "问题：作品方案书 4.6「结果分析」下的模型选型对比表（第 166-171 行）写着：",
         first_indent=False)
    table(doc, [
        ["模型", "参数量", "mAP50", "推理速度(CPU)", "适用场景"],
        ["YOLOv8n", "3.2M", "~85%", "~30 FPS", "边缘设备、实时监测"],
        ["YOLOv8s", "11.2M", "~90%", "~15 FPS", "平衡精度和速度"],
        ["YOLOv8m", "25.9M", "~93%", "~5 FPS", "服务器端、高精度需求"],
        ["YOLOv8l", "43.7M", "~95%", "~2 FPS", "研究用、最高精度"],
    ], widths=[2.30, 2.30, 2.30, 3.60, 4.50], size=9)
    para(doc, "这些是 YOLO 系列在 COCO 数据集上的公开性能，与猪行为检测没有任何关系。"
              "而 4.5「预期结果」（第 248-251 行）又列了另一套数字（mAP50>85%、mAP50-95>60%）。"
              "同一篇方案里出现两套互不相干的指标，是明显的破绽。", first_indent=False)
    para(doc, "改法（二选一）：", first_indent=False, bold=True)
    bullet(doc, "① 如果确实还没训练：subsection 标题从「结果分析」改为「预期结果与验证计划」，"
                "删掉 4.6 那张表，只保留 4.5，并明确写「截至目前已完成方案设计与基线验证，"
                "模型训练正在进行，最终指标以提交时的实测结果为准」。")
    bullet(doc, "② 如果已经训练出结果：把表换成你**真实测出来的**每类 AP50、mAP50、mAP50-95、"
                "Precision、Recall，并写清数据集划分方式和随机种子。")

    h2(doc, "2-2　参考文献无法核实")
    para(doc, "作品方案书第 370-374 行引用了 3 篇中文论文（《农业工程学报》《农业机械学报》"
              "《中国畜牧杂志》）。这三条我无法核实是否真实存在。", first_indent=False)
    bullet(doc, "★ 必须逐条去知网（CNKI）或万方检索原文，确认作者、标题、期刊、年份、卷期页码完全一致。")
    bullet(doc, "查不到原文的，一律删除。引用不存在的文献属于学术不端，风险远大于「参考文献少」。")
    bullet(doc, "宁少勿假：3 篇能核实的真文献，胜过 10 篇凑数的。")

    h2(doc, "2-3　数据集描述存在事实性矛盾")
    para(doc, "作品方案书 4.1.1 说数据来自「Kaggle Pig Behaviors Recognition Dataset（3193张）」，"
              "4.1.2 紧接着说「标注格式采用 YOLO 格式」「标注猪的整体边界框」。", first_indent=False)
    para(doc, "但 Kaggle 上名为「Pig Behaviors Recognition」的数据集是以行为类别组织的，"
              "如果它是**图像分类**数据集，就不存在边界框标注，4.1.2 的描述不成立。", first_indent=False)
    bullet(doc, "★ 请登录 Kaggle 确认该数据集的文件结构：有没有 labels 目录或 *.txt/*.xml/*.json 标注文件？")
    bullet(doc, "若是分类数据集：要么如实改写 4.1.2（说明标注由你们自行完成、标注规则与标注量），"
                "要么改用一个确认带边界框的检测数据集。")
    bullet(doc, "若你们确实自行标注了：写明标注人、标注工具（如 LabelImg/Roboflow）、"
                "标注一致性检验方式（如双人标注 Kappa 系数），这反而是加分项。")

    h2(doc, "2-4　健康判断基准值加不起来")
    para(doc, "作品方案书 3.2.3「正常行为模式参考值」（第 122-128 行）：采食 10-15%、饮水 3-5%、"
              "休息 60-70%、站立 5-10%、行走 10-15%、争斗 <1%。", first_indent=False)
    para(doc, "上界相加为 116%，下界相加为 89%，本身无法构成一个合理的分布。", first_indent=False, bold=True)
    bullet(doc, "★ 改为归一化表述，例如「占全天活动时间的比例」并明确定义分母；")
    bullet(doc, "★ 必须注明每个数值的文献出处或自己的观察样本量。没有依据的阈值会被追问到崩。")

    # ---------- 三 ----------
    doc.add_page_break()
    h1(doc, "三、方法论问题（决定作品上限）")

    h2(doc, "3-1　拿 YOLO 做行为分类，方法上不成立（最根本的问题）")
    para(doc, "现有设计让 YOLO 把整头猪的检测框标成「争斗」「采食」等行为类别。"
              "但行为是**时序动作**，不是物体的静态属性。", first_indent=False)
    bullet(doc, "单帧图像里，猪头低着可能是采食、可能是嗅探、也可能只是低头——无法区分。")
    bullet(doc, "「争斗」与「并排休息」在单帧上高度相似，靠静态框无法分开。")
    bullet(doc, "「行走」必须靠连续帧的位移才能判断，单帧根本没有这个信息。")
    para(doc, "这是任何懂计算机视觉的评委都会第一时间指出的问题。", first_indent=False, bold=True)
    para(doc, "改法：拆成「检测 + 行为推导」两段，各司其职。", first_indent=False, bold=True)
    table(doc, [
        ["层次", "负责什么", "技术手段", "为什么这样分"],
        ["第一段：检测", "找出每头猪的位置，以及食槽、饮水器等栏位设施的位置",
         "单类目标检测（只训「猪」+ 设施若干类），YOLOv8n 或同等轻量模型",
         "目标检测擅长回答「在哪」，标注成本最低，5 天可训出真结果"],
        ["第二段：行为推导", "把位置关系与时间变化映射为 6 类行为",
         "规则引擎 + 时序统计：猪↔食槽距离→采食；猪↔饮水器距离→饮水；"
         "连续帧位移→站立/行走/休息；框交叠+相对位移→争斗",
         "规则可解释、可复现、可写进动物行为学依据，且不需要额外标注"],
        ["第三段：健康评估", "基于行为的时间分布与突变做预警",
         "与历史基线对比（个体自身对照），而非拍脑袋的固定阈值",
         "符合「预防为主」的实际养殖逻辑，也更容易说清科学性"],
    ], widths=[2.60, 4.20, 5.20, 3.00], size=9)
    para(doc, "注意：这个改法还必须解决「食槽/饮水器怎么定位」的问题。"
              "最简单可行的办法是**首次部署时人工框选栏位区域并保存为配置**，"
              "这在真实养殖场是完全可接受的工程做法，也省掉了训练设施检测器的工作量。",
         first_indent=False, bold=True, color=GREEN)

    h2(doc, "3-2　健康评估逻辑过于粗糙")
    para(doc, "现有逻辑：争斗>0 即「异常」；休息占比>90% 即「需关注」。", first_indent=False)
    bullet(doc, "猪群在转群、混群、高温等情况下出现争斗是正常现象，一刀切报「异常」会产生大量误报，"
                "实际落地会被养殖场直接关掉。")
    bullet(doc, "「休息>90%」没有时间尺度——是按一小时还是按一天算？没有时间窗口的阈值无法执行。")
    para(doc, "改法：引入时间窗口 + 个体自身基线 + 多指标联合判断。例如以 6 小时为窗口，"
              "比较该栏当前行为分布与其自身过去 7 天同时段基线的偏离程度；"
              "采食/饮水时长下降超阈值 且 争斗频次上升，才触发预警。"
              "这样既有动物科学依据，也便于写成可复现的算法。", first_indent=False)

    h2(doc, "3-3　创新点表述空泛")
    para(doc, "2.4「本项目创新点」以及第六章列了「专业深度融合」「轻量级模型」「开源开放」等。"
              "这些是**做法描述**，不是创新点——开源的 YOLO 项目成千上万，「开源」不构成创新。",
         first_indent=False)
    bullet(doc, "★ 创新点必须写成「别人怎么做 → 为什么不够 → 我改了什么 → 带来什么差异」的四段式。")
    bullet(doc, "★ 举例：不要写「采用轻量级模型」，而要写「针对猪舍边缘设备算力受限问题，"
                "将检测与行为推理解耦，使行为识别无需时序模型训练即可部署，"
                "在 [实测硬件] 上达到 [实测] FPS」。")

    # ---------- 四 ----------
    h1(doc, "四、内部一致性与小问题")
    table(doc, [
        ["#", "问题", "位置", "改法"],
        ["4-1", "README 称「基于 YOLOv8，CPU 也能实时运行」，方案书却写 YOLOv8n CPU 约 30 FPS",
         "README 第 16 行 / 方案书第 168 行", "CPU 上 30 FPS 不现实。删掉未经实测的速度声明，或改为实测值"],
        ["4-2", "数据增强写了「翻转：水平翻转」，但未说明猪舍固定视角下翻转是否合理",
         "方案书 3.4.1", "补充一句：左右翻转适用于俯拍场景，需确认不引入方向性偏差"],
        ["4-3", "2.4 称「多数研究偏重算法，缺乏动物行为学知识的深度融合」，但 2.1 又列举了国外成熟成果",
         "方案书 2.1 / 2.4", "两处要一致：改为「现有研究多聚焦于单元行为的算法精度，"
         "对行为背后的动物福利与生产指标关联挖掘不足」"],
        ["4-4", "项目进度计划是「第1-10天」的相对时间，未对齐真实截止日",
         "方案书 第八章", "改为绝对日期，与校赛 10-07 / 区域赛 10-15 对齐"],
        ["4-5", "附录 A/B/C 全是「提交时填写」的占位符",
         "方案书 第十章", "提交前必须填实：代码仓库链接、视频链接、数据集来源说明"],
        ["4-6", "「预期结果」小节的容错率",
         "方案书 4.5", "校赛评审看材料，「预期结果」可以存在，但必须明确标注为预期，"
         "不能与「结果分析」混用"],
    ], widths=[0.90, 5.30, 3.60, 5.20], size=9)

    para(doc, "★ 一句话总结：这份材料的**工程骨架是合格的**（代码结构清晰、Web 演示可用、"
              "README 与方案书齐全），问题集中在「把没做的实验写成做完了」和「校名合规」两处。"
              "前者决定你能不能拿高分，后者决定你有没有资格。", bold=True, first_indent=False)

    add_footer(doc, "作品方案书问题清单与修改建议｜2026-10-02")
    path = os.path.join(OUT, "作品方案书_问题清单与修改建议.docx")
    doc.save(path)
    return path


# ============================================================
# 文件 2：校赛作品方案（干净版）
# ============================================================
def build_plan():
    doc = Document()
    base_page(doc)
    doc.styles["Normal"].font.name = BODY
    doc.styles["Normal"]._element.rPr.rFonts.set(qn("w:eastAsia"), BODY)

    # 封面
    para(doc, "2026 年第八届全球校园人工智能算法精英大赛", size=15, bold=True, font=HEI,
         align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False, space_after=2)
    para(doc, "AI+农业算法主题赛　校赛作品方案", size=15, bold=True, font=HEI,
         align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False, space_after=20)
    para(doc, "生猪精准饲喂与疫病防控领域知识智能体", size=22, bold=True, font=HEI,
         align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False, space_after=6)
    para(doc, "——让基层养殖问路不再无门", size=13, font=HEI,
         align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False, space_after=30)
    table(doc, [
        ["项目", "内容"],
        ["作品名称", "生猪精准饲喂与疫病防控领域知识智能体（20字以内）"],
        ["参赛赛道", "算法主题赛 / AI+农业（对应赛题五：农业智能体与大模型决策服务）"],
        ["团队名称", "【待填】"],
        ["团队编号", "【待填，报名后由系统分配】"],
        ["队长 / 队员", "【待填，不超过3人，同校】"],
        ["提交日期", "2026 年 10 月 7 日"],
    ], widths=[3.60, 11.40], size=10)
    para(doc, "【提交前必读】全文（含页眉页脚、文件属性）不得出现参赛团队所在学校名称"
              "与指导教师信息。标注【】处为待填内容；标注〔实测〕处为必须用真实实验数据替换的占位符，"
              "严禁编造。", size=10, first_indent=False, space_after=0, color=RED)

    # 作品简介
    doc.add_page_break()
    h1(doc, "作品简介")
    para(doc, "【全文不超过 300 字。以下为可直接使用的成稿，括号内数字需按实测填写。】",
         size=10, first_indent=False, color=RED)
    para(doc, "我国生猪养殖的疫病防控与精准饲喂高度依赖经验，基层从业者面对问题「问路无门」："
              "饲养标准、兽药规范、防治技术分散在数十份标准与技术文件中，"
              "查得到却用不上，且通用大模型给出的用药建议存在安全风险。"
              "本作品构建面向生猪生产的领域知识智能体：以检索增强生成（RAG）技术"
              "接入饲养标准、饲料成分表、兽药使用与休药期规范等权威语料，"
              "配合疫病—症状—用药知识图谱，并封装饲料配方计算、用药剂量与休药期校验、"
              "生产成本核算三类可调用工具，实现自然语言提问到可执行方案的端到端输出。"
              "〔实测〕在由〔N〕道专业知识题构成的评测集上，本系统答案准确率为〔X%〕，"
              "显著优于通用大模型基线的〔Y%〕；禁用药物拦截率〔X%〕。"
              "系统已在〔N〕位养殖户／技术人员中试用，可用于日常饲喂决策与用药安全把关，"
              "为基层畜牧技术推广提供低成本工具支持。")

    # 一
    h1(doc, "一、作品概述")
    h2(doc, "1. 背景介绍")
    para(doc, "【本节的写法：行业现状 → 问题 → 为什么现在需要它。下面给出可直接改写的事实框架，"
              "引用数据请补上来源与出处。】", size=10.5, first_indent=False, color=RED)
    bullet(doc, "产业地位：我国是世界上生猪养殖与猪肉消费规模最大的国家，生猪产业在保障肉食品供给中"
                "具有基础性地位。生猪养殖以中小规模场户为主体的结构特征，"
                "决定了基层技术服务的覆盖难度较大。")
    bullet(doc, "现实困境：疫病防控与精准饲喂的效果高度依赖个人经验；饲料成本占养殖总成本的比重最高，"
                "配方是否合理直接影响效益；兽药使用不规范既带来食品安全风险，"
                "也加重细菌耐药性问题。")
    bullet(doc, "政策背景：国家持续推进兽用抗菌药使用减量化行动，"
                "对休药期管理与规范用药提出了更严格的要求；同时大力推进智慧农业与数字乡村建设。")
    bullet(doc, "技术缺口：通用大语言模型在畜牧领域存在三类明显不足——"
                "一是专业知识覆盖不足且更新滞后，容易给出过时或笼统的建议；"
                "二是存在幻觉，可能编造不存在的药品名称或剂量；"
                "三是缺乏安全约束，无法保证用药合规。")
    para(doc, "本作品正是针对第三点切入：不做「又一个聊天机器人」，而是做"
              "**有知识边界、有安全约束、有可执行工具**的领域智能体。", bold=True, first_indent=False)

    h2(doc, "2. 目标定位")
    table(doc, [
        ["维度", "目标", "验证方式"],
        ["知识准确性", "在自建专业知识评测集上，答案准确率不低于〔X%〕，"
         "且相对通用大模型基线提升不低于〔X〕个百分点",
         "自建评测集（建议不少于 100 题），双人独立判分，报告一致性"],
        ["用药安全性", "对禁用药物与休药期不足的提问，拦截率〔X%〕；"
         "所有用药建议均附出处与休药期提示",
         "构造风险提问集（不少于 30 条）进行对抗测试"],
        ["工具可用性", "饲料配方计算、剂量校验、成本核算三类工具调用成功率〔X%〕，"
         "单次应答时延不超过〔X〕秒",
         "接口层日志统计与人工抽查"],
        ["应用价值", "在〔N〕位养殖户／基层技术人员中试用，形成试用反馈不少于〔N〕份",
         "现场试用记录、访谈纪要、用户反馈表"],
        ["社会效益", "为基层规范用药与减抗行动提供低成本辅助工具，降低专业知识获取门槛",
         "推广说明与合作协议（如有）"],
    ], widths=[2.40, 7.20, 5.40], size=9.5)
    para(doc, "【没有经济效益可以不写，不影响作品成绩。】", size=10, first_indent=False)

    # 二
    doc.add_page_break()
    h1(doc, "二、需求分析")
    h2(doc, "1. 问题剖析")
    para(doc, "从产业、技术、用户三个层次剖析，明确关键难点：", first_indent=False)
    bullet(doc, "产业层：养殖场户数量多、分布散，专职兽医与技术员覆盖不足；"
                "技术推广多依赖经验口口相传，标准化程度低。")
    bullet(doc, "技术层：专业知识以标准、规程、表格形式存在，结构异构、术语不统一，"
                "直接拼接进大模型提示词既超长又不可靠；"
                "如何把「非结构化文本 + 结构化表格」的混合知识变成可检索、可引用、"
                "可校验的知识底座，是本作品的核心技术难点。")
    bullet(doc, "用户层：养殖户提问口语化、信息不完整（往往缺少日龄、体重、症状持续时间），"
                "系统必须能主动追问补全，而不是在信息不足时硬给答案。")
    para(doc, "关键难点归纳为三条：① 领域知识的混合结构检索与可信引用；"
              "② 用药安全的硬约束（不能只靠模型自觉）；"
              "③ 口语化不完备提问下的需求澄清与工具编排。", bold=True, first_indent=False)

    h2(doc, "2. 需求调研")
    para(doc, "【本节是「需求分析」评分项的关键，必须有真实一手材料。下面给出可直接执行的调研设计，"
              "请在 10 月 4 日前完成并回填数据。】", size=10.5, first_indent=False, color=RED)
    table(doc, [
        ["调研方式", "对象与样本量", "时间", "主要发现【待回填】"],
        ["问卷调查", "养殖户／基层技术人员／动科专业学生，目标〔≥50〕份",
         "10/3-10/4", "【待回填：如〔X%〕受访者曾因用药不规范遇到问题】"],
        ["深度访谈", "养殖场技术负责人〔≥3〕人、基层畜牧技术推广人员〔≥2〕人、"
         "相关方向教师〔≥1〕人", "10/4-10/5", "【待回填：现存工具的具体痛点】"],
        ["现场观察／实习记录", "【牧场合规脱敏描述】", "【时间】",
         "【待回填：日常用药与配方调整的实际决策方式】"],
        ["文献与标准梳理", "兽药使用规范、饲养标准、饲料成分表等〔≥10〕份权威文件",
         "10/3-10/5", "【待回填：知识条目总量、可用表格数量】"],
    ], widths=[2.80, 4.20, 2.20, 5.80], size=9.5)
    para(doc, "调研结论归纳为三类要求：", first_indent=False, bold=True)
    bullet(doc, "功能要求：支持口语化提问；能主动追问关键缺失信息（日龄、体重、症状时长）；"
                "用药类回答必须给出出处与休药期；支持上传或输入配方需求并返回计算结果。")
    bullet(doc, "性能要求：单次应答〔≤X〕秒；知识库可增量更新，不必重训模型。")
    bullet(doc, "体验要求：回答结构固定（结论—依据—操作步骤—注意事项—出处），"
                "避免大段无结构文本；关键风险点用醒目方式提示。")

    # 三
    h1(doc, "三、AI 技术工具选择与运用")
    para(doc, "【本节说明选型依据，按「需求 → 候选 → 选择 → 放弃理由」展开，不要只堆名词。】",
         size=10.5, first_indent=False, color=RED)
    table(doc, [
        ["需求", "候选方案", "本作品选择", "选型依据与放弃理由"],
        ["领域知识接入", "微调领域大模型 / 检索增强生成（RAG）",
         "RAG 为主，轻量微调为辅",
         "微调成本高、知识更新需重训、且难以给出可核验出处；"
         "RAG 可保留原文引用，标准更新时只需重建索引，更适合频繁变动的法规类知识"],
        ["答案可信性", "纯提示词约束 / 引用+校验双通道",
         "强制引用 + 后置校验",
         "提示词约束易被绕过；把「必须携带知识库出处」做成硬性输出校验，"
         "无出处的用药类回答直接拒绝输出"],
        ["结构化知识推理", "向量检索 / 知识图谱 / 两者结合",
         "向量检索 + 知识图谱混合",
         "「疾病—症状—用药—休药期」本质是关系推理，纯向量检索易漏召回；"
         "图谱负责关系约束，向量负责开放语义，二者互补"],
        ["用药安全", "依赖模型判断 / 规则引擎硬校验",
         "独立规则引擎",
         "安全底线不能交给概率模型。将禁用药物清单、休药期要求、剂量上限"
         "做成独立规则层，任何用药建议必须通过该层校验才允许输出"],
        ["可执行能力", "仅回答 / 工具调用（Function Calling）",
         "三类工具：饲料配方计算、剂量与休药期校验、成本核算",
         "养殖户需要的是能直接用的数字，不是一段描述；"
         "把确定性计算交给工具、把语言组织交给模型，可显著降低算错风险"],
        ["开发环境", "—",
         "Python 3.1x；向量库 + 图数据库（或轻量图结构）；"
         "大语言模型以本地部署或 API 方式接入；前端网页对话界面",
         "生态成熟、复现门槛低、便于评委验证"],
    ], widths=[2.40, 3.30, 3.10, 6.20], size=9)
    para(doc, "【必须补全：实际使用的知识库文件清单（名称、发布单位、版本年份）、"
              "大模型的具体名称与版本、向量模型名称。这些是评委核验的依据。】",
         size=10, first_indent=False, color=RED)

    # 四
    doc.add_page_break()
    h1(doc, "四、项目实施")
    h2(doc, "1. 实施方案设计")
    para(doc, "【时间为校赛窗口。若入选后继续参加区域赛，可在此框架上顺延至 10 月 15 日。】",
         size=10, first_indent=False)
    table(doc, [
        ["阶段", "时间", "主要任务", "产出物", "分工"],
        ["S1 知识底座", "10/3-10/4",
         "收集权威知识文件；文本切分与清洗；表格结构化；建立向量索引与图谱关系",
         "知识库文件清单、索引构建脚本", "【队员A】"],
        ["S2 智能体开发", "10/4-10/5",
         "提示词与输出结构设计；RAG 链路；三类工具实现；安全规则引擎",
         "可运行原型", "【队员B】"],
        ["S3 需求调研", "10/3-10/5",
         "问卷、访谈、现场观察；整理痛点并回填第二章",
         "调研纪要与图表", "【队员C】"],
        ["S4 评测与试用", "10/5-10/6",
         "构建专业知识评测集与风险提问集；跑对比实验；请〔N〕位用户试用",
         "评测结果表、试用反馈", "全员"],
        ["S5 材料与提交", "10/6-10/7",
         "作品方案定稿；答辩 PPT；代码打包；合规自查；按命名规范发送邮件",
         "提交包", "队长"],
    ], widths=[2.30, 2.10, 5.00, 3.10, 2.50], size=9)

    h2(doc, "2. 关键技术实现")
    h3(doc, "（1）知识库构建与数据处理")
    bullet(doc, "语料范围：【待补全为真实文件清单】。建议涵盖饲料营养成分与营养价值表、"
                "猪饲养标准中营养需要量部分、兽药使用与休药期相关规定、"
                "常见疫病防治技术规范与防控指南等。每条知识保留来源标识（文件名、发布单位、版本）。")
    bullet(doc, "处理流程：文档解析 → 语义分段（按章节而非固定长度，避免切断表格）→ "
                "表格单独抽取为结构化记录 → 术语规范化（同一成分的不同叫法统一）→ 向量化入库。")
    bullet(doc, "知识图谱：以「疾病—典型症状—推荐用药—禁用情形—休药期」为主干关系，"
                "节点标注来源，供检索时做路径约束。")

    h3(doc, "（2）智能体流程与安全约束")
    bullet(doc, "对话流程：意图识别 →（信息不足则主动追问）→ 混合检索 → 图谱关系校验 → "
                "工具调用（如需计算）→ 安全规则校验 → 结构化生成回答。")
    bullet(doc, "输出结构固定为五段：结论／依据／操作步骤／注意事项／出处，保证可读与可追溯。")
    bullet(doc, "安全规则引擎（独立于模型）：命中禁用药物 → 直接拒绝并说明原因；"
                "给出用药建议但缺少休药期信息 → 拒绝输出并提示查阅最新规定；"
                "剂量超出知识库记载范围 → 提示超出范围并要求人工确认。")
    bullet(doc, "【本节是「AI 技术应用」评分项的主战场，务必补齐模型名称、"
                "检索参数、提示词结构、工具接口定义等可复现细节。】")

    h3(doc, "（3）系统开发与部署")
    bullet(doc, "后端提供服务接口：对话、知识检索、工具调用、安全校验四类；"
                "前端为网页对话界面，支持展示引用出处与工具体计算结果。")
    bullet(doc, "可复现性：提供依赖清单、知识库构建脚本、评测集与评测脚本、随机种子说明；"
                "完整代码包通过网盘链接提交，命名符合大赛规范。")

    # 五
    h1(doc, "五、应用成效")
    h2(doc, "1. 成果展示")
    para(doc, "【下表所有数字必须来自你的真实评测。评测设计已给出，跑完直接填数。】",
         size=10, first_indent=False, color=RED)
    table(doc, [
        ["评测项", "通用大模型基线", "本作品", "提升"],
        ["专业知识问答准确率（〔N〕题）", "〔X%〕", "〔X%〕", "〔+X 个百分点〕"],
        ["答案出处引用完整率", "〔X%〕", "〔X%〕", "〔+X 个百分点〕"],
        ["禁用药物拦截率（〔N〕条风险提问）", "〔X%〕", "〔X%〕", "〔+X 个百分点〕"],
        ["工具调用成功率", "不适用", "〔X%〕", "—"],
        ["单次应答平均时延", "〔X〕秒", "〔X〕秒", "〔±X〕"],
    ], widths=[5.00, 3.20, 3.20, 3.60], size=9.5)
    para(doc, "评测集构建建议：从知识库中抽取知识点，人工编写问答对（不少于 100 题），"
              "覆盖饲养、疫病、用药、成本四类；由两名成员独立判分并报告一致性；"
              "风险提问集专门构造「禁用药物」「休药期不足」「剂量超范围」三类越界提问。",
         first_indent=False)
    para(doc, "功能实现情况：【列出已实现功能，如口语化提问、主动追问、"
              "三类工具调用、出处展示、风险拦截】。", first_indent=False)
    para(doc, "应用案例：【在〔N〕位养殖户／技术人员中试用，脱敏说明，附反馈记录】。",
         first_indent=False)

    h2(doc, "2. 效益分析")
    bullet(doc, "经济效益：以〔N〕头规模猪场为例，通过配方优化降低饲料成本约〔X〕元/头/年，"
                "避免违规用药造成的处置损失与产品降级损失〔X〕元/年。")
    bullet(doc, "社会效益：降低基层获取规范养殖知识的门槛，配合兽用抗菌药减量化行动，"
                "减少不规范用药带来的食品安全与耐药性风险。")
    bullet(doc, "学科建设与科研效益：沉淀「动物科学 + 人工智能」交叉的知识组织规范与评测方法；"
                "形成可复用的知识库构建流程；产出软件著作权〔N〕项。")

    # 六
    h1(doc, "六、总结与展望")
    h2(doc, "1. 经验总结")
    para(doc, "【要写真诚的不足，例如：知识库覆盖范围仍限于生猪育肥阶段，"
              "对种猪与仔猪阶段知识不足；评测集规模有限，判分存在主观性；"
              "图谱关系主要靠人工整理，覆盖广度受限。"
              "提炼关键要点：把安全约束做成独立规则层、而不依赖模型自觉，"
              "是让领域智能体可用于生产场景的前提。】")
    h2(doc, "2. 未来规划")
    bullet(doc, "近期：扩充知识库至种猪、仔猪阶段；增加基于图像的症状辅助识别入口；"
                "与养殖场共建真实问答数据集，持续迭代评测集。")
    bullet(doc, "中期：接入养殖场生产数据（饲喂记录、生产成绩），"
                "从「知识问答」走向「基于本场数据的个性化决策」。")
    bullet(doc, "远期：形成可对接基层畜牧技术推广体系的辅助工具，"
                "探索与现有养殖管理系统的数据互通与协同。")

    # 七
    doc.add_page_break()
    h1(doc, "七、附录")
    for t in [
        "1. 数据资料：知识库文件清单（名称、发布单位、版本年份、获取方式）、"
        "文本与表格处理后的知识条目统计、评测集题目分布统计。",
        "2. 代码与模型：知识库构建脚本、检索链路、工具函数、安全规则引擎关键代码；"
        "完整代码包通过网盘链接提交。",
        "3. 参考文献：饲养标准、兽药使用规范、猪病学教材、"
        "检索增强生成与知识图谱相关论文，注明出处。",
        "4. 其他材料：调研问卷与访谈纪要、用户试用反馈表、"
        "软件著作权申请材料（如有）、评测结果原始记录。",
    ]:
        para(doc, t, first_indent=False, space_after=5)

    para(doc, "", space_after=8)
    para(doc, "【提交前检查清单】① 全文无学校名称与指导教师信息（含文件属性）；"
              "② 报名表已于 10 月 4 日 20:00 前提交；"
              "③ 压缩包命名「参赛赛道-队长学院-队长姓名-作品名称」；"
              "④ 邮件主题按校赛通知规定的固定格式填写（该格式含校名，属通知硬性要求，"
              "只出现在邮件主题与压缩包名里，绝不能写进作品方案正文）；"
              "⑤ 发送至 libiyue@cau.edu.cn，10 月 7 日 20:00 前，建议提前 2 小时。"
              "★ 本页是自查清单，正式提交前请整页删除，避免把校名带进作品材料。",
         size=10, first_indent=False, bold=True, color=RED)

    add_footer(doc, "AI+农业算法主题赛　校赛作品方案")
    path = os.path.join(OUT, "AIC2026_校赛作品方案_生猪领域知识智能体.docx")
    doc.save(path)
    return path


if __name__ == "__main__":
    print("OK1", build_issues())
    print("OK2", build_plan())
