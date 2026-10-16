# -*- coding: utf-8 -*-
"""把 AIC-文献 目录下的 PDF 全文抽取为文本，作为疾病知识库原料。

输出：文本/<编号>_<题名前30字>.txt（含来源头），以及 extraction_report.tsv
"""
import glob
import io
import json
import os
import re
import sys

sys.path.insert(0, r"E:\harness\aic\pylibs")
from pypdf import PdfReader  # noqa: E402

DEST = r"C:\Users\ASUS\Downloads\AIC-文献"
TEXT_DIR = os.path.join(DEST, "文本")
REPORT = r"E:\harness\aic\extraction_report.tsv"
REFS = r"E:\harness\aic\refs.json"

os.makedirs(TEXT_DIR, exist_ok=True)
refs = {r["no"]: r for r in json.load(io.open(REFS, encoding="utf-8"))}


def clean(text):
    """轻度清洗：统一换行、去掉零宽字符、压缩过多空行。保留正文原貌。"""
    text = text.replace("\u200b", "").replace("\ufeff", "").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(lines).strip()


rows = [["文件", "编号", "题名", "页数", "抽取字符数", "有效字符数", "状态"]]
pdfs = sorted(glob.glob(os.path.join(DEST, "*.pdf")))
print(f"待抽取 PDF：{len(pdfs)} 个\n")

total_chars = 0
for p in pdfs:
    base = os.path.basename(p)
    m = re.match(r"^(\d+)_", base)
    no = int(m.group(1)) if m else -1
    ref = refs.get(no, {})
    title = ref.get("title", base)

    try:
        reader = PdfReader(p)
        pages = []
        for pg in reader.pages:
            try:
                pages.append(pg.extract_text() or "")
            except Exception:
                pages.append("")
        raw = "\n".join(pages)
        text = clean(raw)
        # 中文有效字符占比（判断是否扫描版/乱码）
        cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
        total = len(text)
        ratio = cjk / total if total else 0

        if total < 200:
            status = "抽取失败(可能是扫描版)"
        elif ratio < 0.15:
            status = "疑似乱码/非文本层"
        else:
            status = "正常"

        header = (
            f"# 来源: CNKI\n# 编号: {no}\n# 题名: {title}\n"
            f"# 第一作者: {ref.get('firstAuthor') or '(机构文献)'}\n"
            f"# 来源刊物: {ref.get('source','')}  {ref.get('year','')}\n"
            f"# 原文件: {base}\n# 页数: {len(reader.pages)}  抽取字符: {total}  中文字符: {cjk} ({ratio:.0%})\n"
            + "=" * 60 + "\n"
        )
        safe = re.sub(r"[\\/:*?\"<>|\s]", "_", title)[:30]
        out = os.path.join(TEXT_DIR, f"{no:02d}_{safe}.txt")
        io.open(out, "w", encoding="utf-8").write(header + text)
        total_chars += total
        rows.append([base, no, title, len(reader.pages), total, cjk, status])
        print(f"[{no:>2}] {status:<18} {total:>7} 字  中文占比 {ratio:>4.0%}  {title[:30]}")
    except Exception as e:
        rows.append([base, no, title, 0, 0, 0, "异常:" + str(e)[:40]])
        print(f"[{no:>2}] 异常: {e}")

io.open(REPORT, "w", encoding="utf-8").write("\n".join("\t".join(str(x) for x in r) for r in rows))
ok = [r for r in rows[1:] if r[6] == "正常"]
bad = [r for r in rows[1:] if r[6] != "正常"]
print(f"\n{'='*60}")
print(f"正常 {len(ok)} 篇 / 异常 {len(bad)} 篇；总抽取 {total_chars:,} 字")
print(f"文本目录：{TEXT_DIR}")
print(f"报告：{REPORT}")
if bad:
    print("\n需人工处理的：")
    for r in bad:
        print(f"  [{r[1]}] {r[6]}  {r[2][:36]}")
