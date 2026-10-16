# -*- coding: utf-8 -*-
"""生成两份交付物：
1) 动物科学+AI_参赛作战手册.docx
2) AIC2026_AI+农业_技术方案_初稿.docx（按官方7章大纲）
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
                space_after=8, line_spacing=1.5)


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


def table(doc, rows, widths=None, header=True, size=10.5):
    """插入表格。

    关键：tblGrid 必须与单元格宽度一致，并把表格布局设为 fixed、表宽设为
    内容区 100%。python-docx 只写 tcW 时 tblGrid 仍是均分值，Word / LibreOffice
    会据此自动调整列宽，导致表格比内容区更宽、右侧被页面裁切。
    """
    ncols = len(rows[0])
    if widths is None:
        widths = [15.0 / ncols] * ncols
    if len(widths) != ncols:
        raise ValueError(f"widths 列数({len(widths)})与表头列数({ncols})不一致，表头={rows[0]}")
    for ri, r in enumerate(rows):
        if len(r) != ncols:
            raise ValueError(
                f"第 {ri} 行有 {len(r)} 列，表头有 {ncols} 列：{str(r)[:90]}"
            )
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


def base_page(doc, top=2.5, bottom=2.5, left=3.0, right=3.0, header=1.5, footer=1.5):
    """A4 纵向 + 页边距（按模板要求）。

    注意：python-docx 默认模板是 US Letter，必须显式设置 pgSz，
    否则渲染出来是 21.59×27.94cm 而不是 A4。
    """
    for s in doc.sections:
        s.page_width = Cm(21.0)
        s.page_height = Cm(29.7)
        s.top_margin = Cm(top)
        s.bottom_margin = Cm(bottom)
        s.left_margin = Cm(left)
        s.right_margin = Cm(right)
        s.header_distance = Cm(header)
        s.footer_distance = Cm(footer)


def add_footer_text(doc, text):
    for s in doc.sections:
        p = s.footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run(p.add_run(text), size=9)


# ============================================================
# 文件 1：参赛作战手册
# ============================================================
def build_playbook():
    doc = Document()
    base_page(doc)
    doc.styles["Normal"].font.name = BODY
    doc.styles["Normal"]._element.rPr.rFonts.set(qn("w:eastAsia"), BODY)

    para(doc, "动物科学 + AI", size=22, bold=True, font=HEI,
         align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False, space_after=4)
    para(doc, "第八届 AIC 算法大赛参赛作战手册", size=15, bold=True, font=HEI,
         align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False, space_after=4)
    para(doc, "编制日期：2026年10月2日｜校赛报名剩 2 天，作品提交剩 5 天",
         size=11, align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False,
         space_after=6, color=RGBColor(0xC0, 0x00, 0x00))
    para(doc, "依据：《2026-2027学年中国农业大学程序设计大赛暨第八届全球校园人工智能算法精英大赛校内选拔赛的通知》"
              "（信息与电气工程学院，2026-09-30）",
         size=9.5, align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False,
         space_after=14)

    # ---------- 零 ----------
    h1(doc, "零、关键路径（以校内通知为准，前两条是生死线）")
    para(doc, "校内通知把时间整体提前了：校赛报名 10 月 4 日截止、作品 10 月 7 日截止，"
              "都早于大赛官网的 10 月 15 日。先把日历钉死：")
    table(doc, [
        ["时间", "事项", "谁在管", "对你的影响"],
        ["10-04 20:00", "校赛在线报名截止（问卷星）", "信息与电气工程学院", "★ 只剩 2 天。每件作品填一次；同一团队交多个作品要分别填报"],
        ["10-07 20:00", "校赛作品提交截止（邮箱）", "libiyue@cau.edu.cn", "★ 只剩 5 天。校赛不设现场编程与现场答辩，纯材料评审"],
        ["10-15 20:00", "大赛官网报名 + 初赛作品提交截止", "reg.aicomp.cn", "校赛未入选仍可自行报名参赛，这条线比校赛晚 8 天"],
        ["10 月底前", "复赛（等同省级赛事）", "北部赛区组委会", "一等奖15%、二等奖25%、三等奖30%；一、二等奖晋级总决赛"],
        ["11 月底前", "全国总决赛（线下答辩）", "国赛组委会", "晋级后需准备现场答辩"],
    ], widths=[2.30, 5.30, 3.20, 4.20], size=9.5)

    para(doc, "校赛提交规范（很容易因为命名不合规被刷掉，务必照抄）：", first_indent=False, bold=True)
    table(doc, [
        ["项目", "要求"],
        ["压缩包命名", "参赛赛道-队长学院-队长姓名-作品名称"],
        ["邮件主题", "中国农业大学程序设计大赛-参赛赛道-队长学院-队长姓名-作品名称"],
        ["提交邮箱", "libiyue@cau.edu.cn"],
        ["提交材料", "① 作品名称（≤20字）② 作品方案（参照模板与大纲）③ 答辩PPT ④ 代码及其他材料（可合并压缩包）"],
        ["大文件", "上传网盘或代码仓库，在报名表中填写长期有效共享链接"],
        ["官方QQ群", "974961280（校赛通知与动态都在群里发）"],
    ], widths=[3.00, 12.00], size=9.5)

    para(doc, "两条赛道的差别，决定你该把主要精力放哪：", first_indent=False)
    table(doc, [
        ["", "路线A：算法主题赛「AI+农业」", "路线B：算法创新赛「AI+学科交叉」"],
        ["定位", "农业垂直主题赛，专人专赛", "开放式大题，7 道赛题任选"],
        ["与动科契合度", "高：智慧育种、鱼群摄食强度、畜禽视觉识别都是赛题原文点到方向", "高：赛题5明确鼓励农科在内全学科交叉"],
        ["你的主场优势", "★ 学校是北部赛区承办单位，赛区组委会就在身边", "北京赛区选拔赛，非承办单位"],
        ["材料要求", "技术方案(PDF≤10M)＋演示视频(MP4 3-5分钟≤300MB)＋答辩PPT＋佐证材料＋网盘链接", "技术报告(PDF≤10M)，模板结构基本相同"],
        ["评分侧重", "创新25＋需求15＋AI技术20＋实施15＋成效15＋展望10", "创新性、技术先进性、科学价值"],
        ["建议", "★★★ 主攻", "★★ 有余力则兼顾（可同时报名多个赛题）"],
    ], widths=[2.30, 6.90, 5.80], size=10)

    para(doc, "结论：主攻「AI+农业」主题赛，用同一个项目顺手投算法创新赛的「AI+学科交叉」，一份技术方案改两个封面即可，边际成本很低。",
         bold=True)

    # ---------- 一 ----------
    doc.add_page_break()
    h1(doc, "一、把「动物科学」翻译成赛题听得懂的话")
    para(doc, "评委是农业 + AI 背景，不会替你把畜牧场景翻译成算法任务。下面这张对照表是整份手册最值钱的一页，"
              "你的选题只要落在右列任意一格，并通过左侧的场景说明，主题符合性审查就稳过。")

    table(doc, [
        ["赛题（原文要点）", "可切入的动物科学场景", "AI 任务与数据来源"],
        ["赛题一\n农业视觉目标检测与识别\n（原文明确点名了「鱼群摄食强度」）",
         "① 鱼群摄食强度分级\n② 奶牛发情／跛行／采食行为识别\n③ 生猪体况评分与体重估测\n④ 蛋鸡群体行为与异常监测",
         "任务：目标检测／时序动作识别／图像分类（YOLO 系列、ViT、SlowFast）\n"
         "数据：自建视频（实验牧场、水产基地）；公开数据集如 MmCows 多模态奶牛监测数据集"],
        ["赛题二\n农业数据智能分析与精准预测\n（原文明确点名了「基因型 SNP」）",
         "① 奶牛／猪基因组育种值（GEBV）预测\n② 产奶量、日增重、饲料转化率预测\n③ 乳房炎与热应激风险评估\n④ 肉质与乳成分等级评估",
         "任务：回归／分类。GBLUP 基线 → 深度学习（MLP、CNN-SNP、Transformer、GNN 系谱图）\n"
         "数据：公开数据集如 1000 Bull Genomes、Animal Genomes 项目；自建数据来自合作课题组 SNP 芯片＋生产性能测定（DHI）记录"],
        ["赛题五\n农业智能体与大模型决策服务",
         "① 畜禽养殖知识智能问答与精准饲喂决策\n② 动物疫病防控智能体\n③ 牧场生产规划与成本决策助手",
         "任务：RAG（检索增强）＋知识图谱＋Agent 工具调用，无需训练即可出原型\n"
         "数据：养殖技术规程、饲料营养成分标准、疫病防治指南、专业期刊文献；辅以课程笔记、实习手册、指导教师经验语料"],
        ["开放式命题\n（智慧育种／智慧农业生产）",
         "上述任一方向的完整项目方案或功能原型",
         "自主定义任务与数据来源，适合把赛题二与赛题五组合成一个完整闭环"],
    ], widths=[3.10, 3.30, 8.60], size=9.5)

    # ---------- 二 ----------
    doc.add_page_break()
    h1(doc, "二、三个可落地的选题方案（按可行性排序）")
    para(doc, "下面三套方案都是 13 天内能交出完整材料的。方案B 是稳妥首选，方案C 是最容易出彩的，方案A 上限最高但需要硬件或独有数据。")

    h2(doc, "方案 A｜畜禽视觉智能监测：以「鱼群摄食强度识别 + 精准投喂」为题")
    bullet(doc, "痛点：水产养殖投喂靠经验，投喂不足影响生长、过量则残饵污染水体并推高饲料成本（饲料占养殖成本 60% 以上）。")
    bullet(doc, "技术路线：摄像头采集摄食视频 → 光流/时序特征 → CNN+时序模型输出摄食强度分级（强/中/弱/停止）→ 折算最优投喂量 → 边缘设备（Jetson/RK3588）部署。")
    bullet(doc, "为什么推荐：赛题一原文点名「鱼群摄食强度」，踩点极准；可做完整功能原型，演示视频好看。")
    bullet(doc, "风险：需要真实鱼群视频。可先用公开鱼类数据集 + 自建小规模水族箱视频做原理验证。")

    h2(doc, "方案 B｜基因组育种值智能预测：以「多组学融合的奶牛产奶性状基因组预测」为题（推荐主选）")
    bullet(doc, "痛点：我国奶牛/生猪育种长期依赖进口种源，传统 GBLUP 对非线性上位效应建模不足，青年公牛基因组选择准确度仍有提升空间，直接关系种业自主。")
    bullet(doc, "技术路线：SNP 基因型编码 → 特征筛选（LD 剪枝 / GWAS 先验）→ 深度学习模型（CNN 捕捉 SNP 局部连锁、Attention 加权重要位点、MLP 融合系谱与表型）→ 与 GBLUP、BayesA 基线对比 → 5 折交叉验证评估预测准确度（r）、RMSE、R²。")
    bullet(doc, "为什么最稳：纯算法、零硬件、零现场采集成本；数据可先用公开数据集（1000 Bull Genomes、Animal Genomes 项目）或合作课题组数据；论文与专利佐证材料容易产出。")
    bullet(doc, "加分动作：把模型封装成「育种值预测 Web 工具」，让评委点一下就能上传 SNP 文件出结果，作品从「论文」变成「产品」。")
    bullet(doc, "风险：需要真正跑通模型并给出可复现指标，别只做文献综述。")

    h2(doc, "方案 C｜畜禽养殖垂直大模型智能体：以「生猪/奶牛精准饲喂与疫病防控决策助手」为题")
    bullet(doc, "痛点：中小养殖户「问路无门」，基层技术推广人员缺口大，专业知识散落在标准、规程、论文里，查得到但用不上。")
    bullet(doc, "技术路线：领域语料清洗 → 向量化入库（RAG）→ 知识图谱构建（疾病-症状-用药-休药期）→ LLM 智能体 + 工具调用（饲料配方计算器、用药剂量校验、成本核算）→ 前端对话界面。")
    bullet(doc, "为什么容易出彩：不需要训练数据、不需要显卡集群，7 天可做出可用原型；交互式演示视频天然流畅，评委体验分高；「炎症/用药安全」还能呼应科技伦理审查。")
    bullet(doc, "风险：容易被认为「只是套壳」。必须做出真正的领域壁垒：休药期与禁用药物校验规则、饲料营养需要量计算引擎、可溯源引用。")
    bullet(doc, "政策契合：农业农村部持续推进智慧畜牧业与减抗行动，「减抗/精准用药」是天然的政策叙事。")

    para(doc, "推荐组合：方案 B 作为技术方案主体（吃下创新性与 AI 技术应用的分数），方案 C 作为第五章「应用成效」的落地载体（说明模型如何被养殖场用起来），两者合起来就是一个完整闭环。",
         bold=True)

    # ---------- 三 ----------
    doc.add_page_break()
    h1(doc, "三、5 天冲刺时间表（10月2日 → 10月7日 20:00 校赛截止）")
    para(doc, "校赛不设现场编程与现场答辩，评审只看材料。所以这 5 天里，「把方案写扎实 + 把 PPT 做清楚」的"
              "优先级高于「把模型调到最好」。实验能跑出多少就写多少，绝不编数据。", first_indent=False)
    table(doc, [
        ["日期", "任务", "产出物", "负责人"],
        ["10/2（今天）", "① 填问卷星报名表（10/4 20:00 截止，别拖）② 定选题一句话 ③ 拉群 974961280 ④ 找 1-2 位指导教师（动科 + 信息与电气工程学院各一）",
         "报名截图、选题定稿", "队长"],
        ["10/3", "补齐队伍（≤3 人，同校）。数据与基线落地：能拿到的数据先跑通；拿不到数据就立刻转向「方案 C」或零样本方案，不要在这儿卡住",
         "团队名单、基线结果或转向决定", "全队"],
        ["10/4", "20:00 前完成在线报名（硬截止）。同日完成需求调研：问卷 + 访谈 3-5 位养殖户/牧场技术员/师兄师姐",
         "报名成功截图、调研纪要", "队长 + 动科同学"],
        ["10/5", "写作品方案正文（按官方 7 章大纲）；把已有的实验结果、图表、界面截图填进去",
         "作品方案 Word 初稿", "全队"],
        ["10/6", "制作答辩 PPT；整理代码包；补充参考文献与佐证材料；录制演示视频（如条件允许）",
         "PPT、代码压缩包", "全队"],
        ["10/7 上午", "合规自查：删掉所有校名与指导教师信息；导出 PDF＜10M；按命名规范打包压缩",
         "提交包 v1", "队长"],
        ["10/7 20:00", "★ 硬截止：邮件发至 libiyue@cau.edu.cn。建议提前 2 小时发出",
         "—", "—"],
    ], widths=[1.95, 7.05, 3.30, 2.70], size=9.5)

    # ---------- 四 ----------
    h1(doc, "四、照评分表倒推：每一分怎么拿")
    table(doc, [
        ["评分项", "分值", "拿分动作", "常见丢分点"],
        ["创新性", "25", "讲清「别人怎么做/为什么不够/我改了什么」，用一句话概括创新点；强调产业推广示范价值",
         "只讲用了什么模型，不讲为什么这个模型在此场景下更合适"],
        ["需求分析", "15", "必须有真实调研：问卷 N 份、访谈 N 人、现场试验记录；给出量化痛点（如每头牛每年损失 X 元）",
         "通篇二手资料，无一手调研，评委会认为不了解产业"],
        ["AI 技术应用", "20", "给出模型结构图、超参、消融实验、可复现说明；说明与农业场景的匹配逻辑",
         "堆砌名词、无实验、无指标"],
        ["项目实施", "15", "给实施方案：步骤、时间计划、资源、分工；关键技术细节（数据采集→训练→部署）",
         "只有方案没有过程，看不出真的做过"],
        ["研究结论与应用成效", "15", "给出具体数字：准确率提升 X%、成本降低 Y%、试点 Z 个场；附佐证材料",
         "结论停留在「效果良好」这类空话"],
        ["总结与展望", "10", "复盘不足要真诚，未来规划要具体到下一步做什么、和谁合作",
         "结尾套话，无反思"],
    ], widths=[2.40, 1.20, 6.50, 4.90], size=9.5)

    # ---------- 五 ----------
    doc.add_page_break()
    h1(doc, "五、提交材料清单（缺一项可能直接失去资格）")
    para(doc, "校赛只需要前四项（作品名称、作品方案、答辩PPT、代码及其他材料），"
              "但建议现在就按大赛完整标准准备第 4-7 项，入选后可直接复用。",
         first_indent=False, size=10)
    table(doc, [
        ["#", "材料", "规范要求", "易错点"],
        ["1", "作品名称", "自主拟定，不超过 20 字", "别把校名/团队名写进作品名"],
        ["2", "作品简介", "≤300 字，按「问题-方案-效果-应用」", "超字数、没写效果"],
        ["3", "技术方案", "PDF，≤10M，按官方模板与大纲", "用了旧模板；超 10M（图片未压缩）"],
        ["4", "演示视频", "MP4，3-5 分钟，≤300MB", "时长差几秒就违规；未展示完整流程"],
        ["5", "答辩 PPT", "最终保存为 PDF", "直接交 pptx"],
        ["6", "佐证材料", "专利/软著/论文录用/企业合作/用户反馈，合并为 1 个 PDF", "散着交多个文件"],
        ["7", "其他材料链接", "代码包等放百度网盘，永久有效＋自动提取码；命名「团队编号-赛题名称-作品名称-材料名称」",
         "链接过期；命名不合规"],
    ], widths=[0.80, 2.30, 6.60, 5.30], size=9.5)

    para(doc, "★ 红线（务必记住）：技术方案、演示视频、答辩 PPT 里都不能出现学校名称和指导教师信息。这是公平性条款，"
              "违反了会直接影响成绩。写完一定要通读一遍删干净，包括页眉页脚、文件属性、致谢段落。", bold=True)

    # ---------- 六 ----------
    h1(doc, "六、队长现在就该做的 5 件事（今晚完成）")
    for i, t in enumerate([
        "填校赛报名表：https://v.wjx.cn/vm/exoenAc.aspx# ，10 月 4 日 20:00 截止。同一团队交多个作品要分别填报，把提交成功页截图存档。",
        "加两个群：校赛官方群 974961280（校赛通知与动态都在这儿发）；AI 农业主题赛群 1016209674。北部赛区联系人李碧月 18811778600，"
        "也是本次校赛的收件人；组委会邮箱 jaassnxh@126.com。有疑问今天就在群里问。",
        "下载官方附件：《AIC·“AI+农业”竞赛规则及作品提交要求》与《AIC·“AI+农业”技术方案参考大纲》，并把官方技术方案模板下载下来"
        "（规则附件里给了网盘地址，提取码 2026）。校赛通知里的「附件3、附件4」就是这两份，优先按它们写。",
        "定选题并做数据可行性判断：先问清「我在 10 月 6 日之前能拿到什么数据」，再回头定选题。数据决定方向，不是方向决定数据。",
        "找指导教师：一位动物科学技术学院方向（动物遗传育种／动物营养／智慧养殖），一位信息与电气工程学院方向（机器学习／计算机视觉）。"
        "注意：大赛材料里不能出现学校名称与指导教师信息，所以指导教师只用于把方向把关，名字不要写进方案。",
    ], 1):
        para(doc, f"{i}. {t}", first_indent=False, space_after=4)

    # ---------- 七 ----------
    h1(doc, "七、参考资料与数据源")
    for t in [
        "大赛官网：https://www.aicomp.cn　赛题规则页：https://www.aicomp.cn/tracks/tracks-5/4912.html",
        "报名系统：https://reg.aicomp.cn",
        "《关于举办第八届全球校园人工智能算法精英大赛“AI+农业”算法主题赛的通知》（全智赛组委会〔2026〕28号）",
        "《关于举办第八届全球校园人工智能算法精英大赛“算法创新赛道”竞赛的通知》（全智赛组委会〔2026〕11号）",
        "MmCows：多模态奶牛监测数据集（NeurIPS 2024 Datasets & Benchmarks）",
        "ReaGP：残差单元＋注意力机制的基因组预测网络（可作为赛题二基线对比）",
        "1000 Bull Genomes Project / Animal Genomes 项目：公开基因组与表型数据",
        "行业动向：生猪产业大模型与智能体平台建设、畜禽智能养殖与减抗政策",
    ]:
        bullet(doc, "· " + t, size=10.5)

    add_footer_text(doc, "动物科学+AI 参赛作战手册｜2026-10-02")
    path = os.path.join(OUT, "动物科学+AI_参赛作战手册.docx")
    doc.save(path)
    return path


# ============================================================
# 文件 2：技术方案初稿
# ============================================================
def build_proposal():
    doc = Document()
    base_page(doc)

    # 封面
    para(doc, "2026 年第八届", size=18, bold=True, font=HEI,
         align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False, space_after=2)
    para(doc, "全球校园人工智能算法精英大赛", size=18, bold=True, font=HEI,
         align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False, space_after=2)
    para(doc, "算法主题赛", size=16, bold=True, font=HEI,
         align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False, space_after=2)
    para(doc, "AI+农业", size=16, bold=True, font=HEI,
         align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False, space_after=18)
    para(doc, "技 术 方 案", size=26, bold=True, font=HEI,
         align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False, space_after=40)
    for label in ["团队名称：", "团队编号：", "赛题名称：", "作品名称：", "日期：    年    月    日"]:
        para(doc, label, size=14, bold=True, font=HEI,
             align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False, space_after=10)

    para(doc, "【提交前必读】本文件所有方括号【】内容为待填写或待确认项。依据竞赛公平性条款，"
              "全文（含页眉页脚、文件属性）不得出现参赛团队所在学校名称与指导教师信息。",
         size=10.5, first_indent=False, space_after=0,
         color=RGBColor(0xC0, 0x00, 0x00))

    doc.add_page_break()
    para(doc, "AIC·“AI+农业”技术方案参考大纲", size=12, bold=True, font=HEI,
         first_indent=False, space_after=6)

    # 作品简介
    h1(doc, "作品简介")
    para(doc, "【≤300字，按“问题—方案—效果—应用”四段式撰写。以下为可直接改写的模板：】", size=10.5,
         first_indent=False, color=RGBColor(0xC0, 0x00, 0x00))
    para(doc, "【问题】我国畜禽种业长期依赖进口种源，传统基因组选择方法（GBLUP）对基因间非线性互作建模不足，"
              "青年个体基因组育种值预测准确度受限，直接影响选种效率与种业自主可控。"
              "【方案】本作品构建面向【奶牛产奶性状／生猪日增重】的多组学融合深度学习预测框架："
              "以 SNP 基因型为主特征，引入注意力机制加权关键位点，并通过 CNN 分支捕捉 SNP 局部连锁结构，"
              "同时融合系谱与生产性能测定数据，最后封装为可上传基因型文件即出预测值的 Web 工具。"
              "【效果】在【公开数据集名称】上，预测准确度（5 折交叉验证相关系数 r）由 GBLUP 的【0.XX】提升至【0.XX】，"
              "RMSE 降低【X%】，单次全群预测耗时由【X】分钟缩短至【X】秒。"
              "【应用】工具已在【N】个合作牧场／育种场开展试用，可支撑早期选留与配种决策。")

    # 一
    h1(doc, "一、作品概述")
    h2(doc, "1. 背景介绍")
    para(doc, "【阐述作品所属行业与领域现状：我国畜牧业规模、种业对外依存度、基因组选择技术应用现状。"
              "点明存在的问题或机遇：计算育种在畜禽种业振兴行动中的战略地位。说明作品的必要性与重要性。】")
    para(doc, "建议写作要点：")
    bullet(doc, "① 产业规模与地位：畜牧业在农业产值中的占比、畜禽种业“卡脖子”问题。")
    bullet(doc, "② 技术现状：基因组选择（GS）已在奶牛、猪育种中应用，主流方法为 GBLUP、BayesA/B、ssGBLUP。")
    bullet(doc, "③ 现存问题：SNP 维度高达数万至数十万，样本量小、非线性上位效应难以捕捉、跨群体泛化差、"
                "计算成本高，导致青年个体早期选择准确度不足。")
    bullet(doc, "④ 机遇：深度学习与注意力机制在基因组预测中的最新进展，以及国内牧场表型数据积累日趋完善。")

    h2(doc, "2. 目标定位")
    para(doc, "【用可量化指标界定目标，建议写成如下形式：】")
    table(doc, [
        ["维度", "目标", "验证方式"],
        ["技术指标", "5 折交叉验证预测准确度 r ≥ 【0.XX】，较 GBLUP 基线提升 ≥ 【X%】；RMSE 降低 ≥ 【X%】",
         "同一数据划分下与 GBLUP／BayesA 对比"],
        ["工程指标", "支持单次上传 ≤【5万】头个体基因型，全流程预测 ≤【60】秒", "工具端实测计时"],
        ["应用指标", "在【N】个育种场／课题组试用，形成用户反馈 ≥【N】份", "试用证明、访谈纪要"],
        ["社会效益", "为畜禽种业自主选育提供低成本、可复现的算法工具，降低基因组预测的使用门槛", "推广说明"],
    ], widths=[2.40, 7.40, 5.20], size=10)
    para(doc, "【没有经济效益可以不写，不影响作品成绩。】", size=10.5, first_indent=False)

    # 二
    doc.add_page_break()
    h1(doc, "二、需求分析")
    h2(doc, "1. 问题剖析")
    para(doc, "【从多维度挖掘问题本质，明确关键难点与痛点。建议按“产业痛点 → 技术痛点 → 用户痛点”三层展开。】")
    bullet(doc, "产业痛点：育种周期长（奶牛世代间隔 4-5 年），早期选择依赖后裔测定，成本高、周期长；"
                "进口种源依赖度高，选育效率直接决定产业竞争力。")
    bullet(doc, "技术痛点：SNP 位点数远大于个体数（p≫n），经典线性模型难以刻画上位效应；"
                "不同群体、不同品种间模型泛化能力差；深度学习模型可解释性不足，育种家不敢用。")
    bullet(doc, "用户痛点：育种场技术员不具备编程能力，算法成果难以落地为可用工具；"
                "商业育种软件授权费用高、不透明、不可二次开发。")
    para(doc, "关键难点：【明确写出 2-3 个真正的技术难点，例如“小样本高维下的过拟合抑制”“模型可解释性与预测精度的平衡”"
              "“跨群体迁移时的分布偏移”】。")

    h2(doc, "2. 需求调研")
    para(doc, "【这一段是需求分析 15 分的关键，必须有真实一手材料，不能只引文献。建议采用下表汇总：】")
    table(doc, [
        ["调研方式", "对象/样本量", "时间", "主要发现"],
        ["问卷调查", "养殖场技术人员／动科专业学生 【N】份", "【10/6-10/8】", "【N%】受访者认为早期选种准确度是最需改进环节"],
        ["深度访谈", "育种场技术负责人 【N】人；课题组老师 【N】人", "【10/7-10/9】", "现有软件【具体痛点，如无法上传自有模型、结果不可解释】"],
        ["现场试验／实习观察", "【牧场/实验室名称脱敏】", "【时间】", "【观察到的人工记录方式与效率问题】"],
        ["文献与标准研究", "【N】篇论文＋【N】项行业标准", "【时间】", "主流方法仍以 GBLUP 系为主，深度学习落地案例稀少"],
    ], widths=[2.80, 4.20, 2.20, 5.80], size=10)
    para(doc, "调研结论归纳为功能、性能、体验三方面要求：【示例】功能上需支持常见基因型格式（PLINK bed/ped、"
              "VCF）直接上传；性能上要求万级个体分钟内出结果；体验上要求给出可解释的重要性排序与可视化报告。")

    # 三
    h1(doc, "三、AI 技术工具选择与运用")
    para(doc, "【说明选型依据，不要只列名词。建议用“需求 → 候选技术 → 选择理由 → 放弃理由”的逻辑表。】")
    table(doc, [
        ["需求", "候选方案", "本作品选择", "选型依据"],
        ["高维 SNP 特征提取", "GBLUP / BayesA / 随机森林 / CNN", "CNN（一维卷积）",
         "SNP 沿染色体排列存在局部连锁结构，卷积核可有效捕捉邻近位点组合效应"],
        ["关键位点加权", "GWAS 先验筛选 / 注意力机制", "自注意力加权",
         "避免硬筛选丢失弱效位点，且注意力权重可作为可解释性输出"],
        ["多源数据融合", "简单拼接 / 多分支网络 / 图神经网络", "多分支融合（基因型＋系谱＋表型）",
         "系谱可编码为亲缘关系矩阵作为辅助输入，图网络在样本量小时易过拟合"],
        ["可视化与交付", "命令行脚本 / Web 应用 / 桌面软件", "Web 应用（前后端分离）",
         "育种场无需安装环境，浏览器即可使用，便于推广"],
        ["开发环境", "—", "Python 3.1x＋PyTorch＋scikit-learn＋pandas；部署 FastAPI＋轻量前端",
         "生态成熟、复现门槛低、便于评委验证"],
    ], widths=[2.60, 3.40, 3.20, 5.80], size=9.5)
    para(doc, "【如采用第三方大模型/智能体工具，需在此明确写出工具名称、版本与选型依据。】")

    # 四
    doc.add_page_break()
    h1(doc, "四、项目实施")
    h2(doc, "1. 实施方案设计")
    para(doc, "【注：时间为校赛窗口（10月2日—10月7日）。若校赛入选后继续参加区域赛，可在 10 月 15 日前继续完善，"
              "届时按同一框架顺延即可。】", first_indent=False, size=10)
    table(doc, [
        ["阶段", "时间", "主要任务", "资源配置", "团队分工"],
        ["S1 数据与基线", "10/3-10/4", "数据获取、质控（MAF/HWE/缺失率过滤）、GBLUP 基线复现",
         "公开数据集＋课题组数据；CPU 或云 GPU", "【姓名A】数据；【姓名B】基线"],
        ["S2 模型开发", "10/4-10/5", "构建 CNN-Attention 模型、超参搜索、消融实验",
         "PyTorch 环境", "【姓名B】主模型；【姓名A】实验记录"],
        ["S3 需求验证与封装", "10/4-10/6", "用户调研；Web 工具开发与联调",
         "FastAPI＋前端；测试机", "【姓名C】调研；【姓名B】封装"],
        ["S4 材料制作", "10/5-10/6", "作品方案撰写、答辩 PPT、代码包与佐证材料整理",
         "录屏与剪辑工具", "全员"],
        ["S5 合规自查与提交", "10/7", "去校名/教师信息、PDF 压缩＜10M、按「参赛赛道-队长学院-队长姓名-作品名称」打包",
         "—", "队长"],
    ], widths=[2.40, 2.20, 4.40, 3.20, 2.80], size=9.5)

    h2(doc, "2. 关键技术实现")
    h3(doc, "（1）数据采集与处理")
    bullet(doc, "数据来源：【公开数据集名称／合作课题组，需注明并取得合法授权】。")
    bullet(doc, "质控流程：剔除 MAF＜0.01 位点、缺失率＞5% 个体与位点、HWE 检验 p＜1e-6 位点；"
                "缺失基因型用群体均值或 Beagle 填充。")
    bullet(doc, "特征编码：将 {0,1,2} 基因型编码为数值向量，并按染色体顺序组织为一维序列输入卷积层。")
    bullet(doc, "数据集划分：5 折交叉验证；另设独立验证群体以考察泛化能力（避免同群体泄漏）。")

    h3(doc, "（2）模型训练与优化")
    bullet(doc, "网络结构：一维卷积模块（捕捉局部连锁）→ 多头自注意力模块（全局位点加权）→ 全连接回归头；"
                "并行系谱分支输入亲缘关系矩阵降维特征。")
    bullet(doc, "损失函数：MSE；加入 L2 正则与 Dropout 抑制过拟合；小样本场景采用早停策略。")
    bullet(doc, "基线对比：GBLUP、BayesA、随机森林、MLP，统一数据划分与评价指标。")
    bullet(doc, "评价指标：预测准确度 r（观测值与预测值相关系数）、RMSE、R²、MAE；"
                "同时报告训练耗时与显存占用。")
    bullet(doc, "【必须放消融实验表：去掉注意力模块、去掉系谱分支、仅用线性模型的效果变化。】")

    h3(doc, "（3）系统开发与部署")
    bullet(doc, "后端：FastAPI 提供基因型文件上传、质控报告、预测结果与特征重要性接口。")
    bullet(doc, "前端：单页应用，支持拖拽上传、进度反馈、结果可视化（重要性位点曼哈顿图、个体预测值分布）。")
    bullet(doc, "可复现性：提供 requirements.txt、随机种子固定说明、一键复现脚本（通过网盘链接提交，命名符合规范）。")
    bullet(doc, "【技术实现细节与创新点要在这里说透：这是 AI 技术应用 20 分的主战场。】")

    # 五
    doc.add_page_break()
    h1(doc, "五、应用成效")
    h2(doc, "1. 成果展示")
    table(doc, [
        ["指标", "GBLUP 基线", "本作品", "提升"],
        ["预测准确度 r（5 折均值）", "【0.XX】", "【0.XX】", "【+X%】"],
        ["RMSE", "【X.XX】", "【X.XX】", "【-X%】"],
        ["R²", "【0.XX】", "【0.XX】", "【+X%】"],
        ["全群预测耗时", "【X】分钟", "【X】秒", "【X 倍】"],
        ["模型体积", "—", "【X】MB", "可离线部署"],
    ], widths=[4.60, 3.00, 3.00, 4.40], size=10)
    para(doc, "功能实现情况：【列出已实现的完整功能，如基因型质控、育种值预测、重要性位点可视化、批量导出】。")
    para(doc, "应用案例：【在 N 个牧场／课题组试用，脱敏说明，附用户反馈与试用证明】。")

    h2(doc, "2. 效益分析")
    bullet(doc, "经济效益：早期选择替代部分后裔测定，按每头测定成本【X】元、年测定【N】头计，"
                "预计每年节约【X】万元；选育准确性提升带来的遗传进展折算为【X】元/年。")
    bullet(doc, "社会效益：降低基因组预测工具使用门槛，助力中小育种场与科研团队，服务种业振兴与畜牧业高质量发展。")
    bullet(doc, "学科建设与科学研究效益：形成“动物遗传育种＋人工智能”交叉培养案例；"
                "沉淀可复用的数据处理规范与开源脚本；产出论文／软著【N】项。")

    # 六
    h1(doc, "六、总结与展望")
    h2(doc, "1. 经验总结")
    para(doc, "【回顾实施过程，诚实写明哪些做成了、哪些没做成。例如：模型精度提升明显，但跨品种泛化能力仍不足；"
              "调研样本量偏小，结论代表性有限。提炼作品在应用创新方面的关键要点："
              "把领域先验（连锁结构、系谱关系）编码进网络，是提升小样本基因组预测的关键。】")
    h2(doc, "2. 未来规划")
    bullet(doc, "近期（3 个月）：扩充多品种数据，验证跨群体泛化；接入更多性状（繁殖、抗病、肉质）。")
    bullet(doc, "中期（1 年）：引入多组学数据（转录组、代谢组、微生物组），构建多模态预测框架；"
                "与育种场共建数据闭环。")
    bullet(doc, "远期：形成可对外服务的基因组预测平台，探索与商业育种软件的互补定位；"
                "推动算法在畜禽种业自主选育中的规模化应用。")

    # 七
    doc.add_page_break()
    h1(doc, "七、附录")
    for t in [
        "1. 数据资料：原始数据来源说明（数据集名称、版本、获取方式、授权情况）、处理后数据说明、质控前后统计表。",
        "2. 代码与模型：关键算法代码片段、模型结构定义、训练脚本；完整代码包通过网盘链接提交。",
        "3. 参考文献：GBLUP 原始文献、深度学习基因组预测综述与代表性论文、畜禽育种行业标准，注明出处。",
        "4. 其他材料：软著／专利受理通知、用户试用证明、调研问卷与访谈纪要、演示视频与答辩 PPT 说明。",
    ]:
        para(doc, t, first_indent=False, space_after=5)

    para(doc, "", space_after=10)
    para(doc, "【最终交付提醒】① 全文删除学校名称与指导教师信息；② 导出 PDF 且文件＜10M；"
              "③ 演示视频 MP4、3-5 分钟、＜300MB；④ 答辩 PPT 同样导出为 PDF；"
              "⑤ 佐证材料合并为 1 个 PDF；⑥ 网盘链接永久有效并按要求命名。",
         size=10.5, first_indent=False, bold=True, color=RGBColor(0xC0, 0x00, 0x00))

    add_footer_text(doc, "AIC·“AI+农业”技术方案")
    path = os.path.join(OUT, "AIC2026_AI+农业_技术方案_初稿.docx")
    doc.save(path)
    return path


if __name__ == "__main__":
    p1 = build_playbook()
    p2 = build_proposal()
    print("OK1", p1)
    print("OK2", p2)
