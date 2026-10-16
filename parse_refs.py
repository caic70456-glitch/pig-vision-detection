# -*- coding: utf-8 -*-
"""解析 CNKI 导出的参考文献清单为结构化 JSON。

格式示例：
[1]伍柏宇,林慧敏,陈惠玲.规模化养殖场保育猪饲养管理的有效措施[J].吉林畜牧兽医,2026,47(9):58-60.
   ^-- 作者 --^ ^------- 题名 -------^ ^文献类型^ ^--- 来源 ---^ ^年^
"""
import io
import json
import re

SRC = r"C:\Users\ASUS\Downloads\CNKI-20261003192821228.txt"
OUT = r"E:\harness\aic\refs.json"

lines = io.open(SRC, encoding="utf-8-sig").read().splitlines()
refs = []
problems = []

for raw in lines:
    s = raw.strip()
    if not s:
        continue
    m = re.match(r"^\[(\d+)\]\s*(.+)$", s)
    if not m:
        problems.append(("无法匹配编号", s[:60]))
        continue
    no = int(m.group(1))
    body = m.group(2)

    # 1) 定位文献类型标记 [J]/[D]/[N]/[C]/[M]
    mt = re.search(r"\[(J|D|N|C|M|R|S|P)\]", body)
    if not mt:
        problems.append(("无文献类型标记", body[:60]))
        continue
    kind = mt.group(1)
    head = body[:mt.start()]
    tail = body[mt.end():]

    # 2) 在 [类型] 之前按句点切分：最后一个句点之前是作者，之后是题名
    #    题名本身极少含中文句号，作者段以 "." 结尾
    cut = head.rfind(".")
    if cut == -1:
        # 没有作者段，整段就是题名
        authors_raw, title = "", head.strip()
    else:
        authors_raw, title = head[:cut].strip(), head[cut + 1:].strip()
    title = title.strip().rstrip("．. ")

    first_author = ""
    if authors_raw:
        names = [n.strip() for n in re.split(r"[,，]", authors_raw) if n.strip()]
        if names:
            first_author = names[0]

    # 3) 尾部：.来源,年,卷(期):页. 或 ,年,(期):页.
    tail = tail.lstrip(".． ")
    source, year = "", ""
    ms = re.match(r"^(.*?)[,，]\s*(\d{4})\s*[,，]", tail)
    if ms:
        source, year = ms.group(1).strip(), ms.group(2)
    else:
        # 会议论文/报纸等格式
        ms2 = re.match(r"^(.*?)[,，]\s*(\d{4})", tail)
        if ms2:
            source, year = ms2.group(1).strip(), ms2.group(2)
        else:
            # 形如 "南方科技报,2026-07-22(005)"
            ms3 = re.match(r"^([^,，]*?)[,，]\s*(\d{4})-\d{2}-\d{2}", tail)
            if ms3:
                source, year = ms3.group(1).strip(), ms3.group(2)
            else:
                year_m = re.search(r"(\d{4})", tail)
                year = year_m.group(1) if year_m else ""
                source = tail.split(",")[0].split("，")[0].strip()

    refs.append({
        "no": no, "title": title, "firstAuthor": first_author,
        "source": source, "year": year, "kind": kind, "raw": s,
    })

io.open(OUT, "w", encoding="utf-8").write(json.dumps(refs, ensure_ascii=False, indent=1))

print(f"共解析 {len(refs)} 条 -> {OUT}\n")
for r in refs:
    print(f"[{r['no']:>2}] {r['title'][:34]:<36} | {r['firstAuthor']:<6} | {r['source'][:12]:<14} | {r['year']} | {r['kind']}")

bad = [r["no"] for r in refs if not r["title"] or not r["firstAuthor"] or not r["source"]]
print("\n字段缺失编号:", bad if bad else "无")
if problems:
    print("解析问题:", problems)
