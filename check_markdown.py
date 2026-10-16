# -*- coding: utf-8 -*-
"""校验成果包文档中已无 Markdown 残留符号（** 与反引号）。"""
import io
import os
import re
import sys
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PKG = r"E:\harness\aic\成果包"
docs = []
for root, _d, files in os.walk(PKG):
    for f in files:
        if f.endswith(".docx"):
            docs.append(os.path.join(root, f))

for d in docs:
    with zipfile.ZipFile(d) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    txt = re.sub(r"<[^>]+>", "", xml)
    star = txt.count("**")
    tick = txt.count("`")
    mark = "OK " if (star == 0 and tick == 0) else "BAD"
    print(f"  {mark} ** ×{star}  ` ×{tick}   {os.path.relpath(d, PKG)}")

# 顺带确认加粗确实生效
p = os.path.join(PKG, "01_作品方案",
                 "作品方案_基于视觉行为感知的猪只疫病辅助诊断系统.docx")
with zipfile.ZipFile(p) as z:
    xml = z.read("word/document.xml").decode("utf-8", "replace")
n_bold = len(re.findall(r"<w:b/>", xml))
print(f"\n  作品方案中的加粗 run 数：{n_bold}（应远大于表格表头数量，说明 ** 已转为真加粗）")
