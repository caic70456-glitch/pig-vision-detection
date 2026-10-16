# -*- coding: utf-8 -*-
"""定位所有文献中的「临床症状/流行特点」段落，用于人工核对与词表补全。"""
import glob
import io
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TEXT_DIR = r"C:\Users\ASUS\Downloads\AIC-文献\文本"
OUT = r"E:\harness\aic\kb\临床症状原文汇总.md"
SEP = "=" * 60

# 章节标题特征词
HEAD_PAT = re.compile(
    r"^\s*(\d+(\.\d+)*)?\s*[、.]?\s*(临床|症状|发病|流行|病理|诊断|剖检|防治|防控|治疗|"
    r"流行病学|临床表现|主要症状|典型症状)")

files = sorted(glob.glob(os.path.join(TEXT_DIR, "*.txt")))
blocks = []

for f in files:
    no = os.path.basename(f)[:2]
    raw = io.open(f, encoding="utf-8").read()
    head, body = raw.split(SEP, 1)
    title = ""
    for line in head.split("\n"):
        if line.startswith("# 题名:"):
            title = line.replace("# 题名:", "").strip()
    lines = [ln.rstrip() for ln in body.split("\n")]

    # 找出所有可能是章节标题的行，并取其到下一个标题之间的内容
    idxs = [i for i, ln in enumerate(lines) if HEAD_PAT.match(ln) and len(ln.strip()) < 40]
    if not idxs:
        # 没有明显章节结构：退化为全文
        idxs = [0]

    for k, i in enumerate(idxs):
        j = idxs[k + 1] if k + 1 < len(idxs) else len(lines)
        seg = " ".join(x.strip() for x in lines[i:j] if x.strip())
        if len(seg) < 60:
            continue
        blocks.append({"no": no, "title": title, "head": lines[i].strip(), "text": seg})

# 输出 Markdown，按文献分组
md = ["# 文献「临床/流行/病理」段落原文汇总", "",
      f"共 {len(files)} 篇文献，提取出 {len(blocks)} 个段落。",
      "用途：核对知识库症状是否漏抽，并据此补全 `symptom_dict.json`。", ""]

cur = None
for b in blocks:
    if b["no"] != cur:
        cur = b["no"]
        md.append(f"\n---\n\n## [{b['no']}] {b['title']}\n")
    md.append(f"**{b['head']}**\n")
    md.append(f"> {b['text'][:900]}\n")

io.open(OUT, "w", encoding="utf-8").write("\n".join(md))

# 控制台：只统计有专论文献的 9 种病，看它们的临床段落
DEDICATED = {"副猪嗜血杆菌病": "23", "猪繁殖与呼吸综合征": "36", "猪支原体肺炎": "03",
             "猪瘟": "?", "猪沙门氏菌病": "06", "猪圆环病毒病": "41",
             "猪流行性腹泻": "02", "非洲猪瘟": "17", "猪增生性肠炎": "?"}
print(f"提取 {len(blocks)} 个段落 -> {OUT}\n")
print("按文献统计段落数：")
from collections import Counter
c = Counter(b["no"] for b in blocks)
for no in sorted(c):
    t = next(b["title"] for b in blocks if b["no"] == no)
    print(f"  [{no}] {c[no]:>2} 段  {t[:40]}")
