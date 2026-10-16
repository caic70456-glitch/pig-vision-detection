# -*- coding: utf-8 -*-
"""检查 PPTX 中的文字是否含违规词（大赛公平性条款）。

PPTX 的文字分散在 slide XML 中，这里把全部 slide XML 拼起来后去标签检查。
"""
import io
import os
import re
import sys
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FORBIDDEN = ["中国农业大学", "农业大学", "农大", "信息与电气工程学院",
             "动物科学技术学院", "动物科技学院", "指导教师", "指导老师"]

paths = sys.argv[1:] or [r"E:\harness\aic\成果包\02_答辩PPT\答辩PPT.pptx",
                         r"E:\harness\aic\成果包\02_答辩PPT\答辩PPT大纲.docx"]

for p in paths:
    if not os.path.isfile(p):
        print(f"  跳过（不存在）：{p}")
        continue
    with zipfile.ZipFile(p) as z:
        parts = [n for n in z.namelist()
                 if re.search(r"(slides/slide\d+\.xml|word/document\.xml)$", n)]
        text = []
        for n in parts:
            xml = z.read(n).decode("utf-8", "replace")
            text.append(re.sub(r"<[^>]+>", "", xml))
    full = "".join(text)
    hits = [w for w in FORBIDDEN if w in full]
    n_slides = len([n for n in parts if "slide" in n])
    tag = "OK " if not hits else "问题"
    extra = f"　命中：{hits}" if hits else ""
    print(f"  {tag} {os.path.basename(p)}　"
          f"{'幻灯片 ' + str(n_slides) + ' 页' if n_slides else '文档'}　"
          f"字符数 {len(full)}{extra}")
