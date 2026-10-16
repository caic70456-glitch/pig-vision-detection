# -*- coding: utf-8 -*-
"""生成「待补下载清单」——给用户手动下载用。"""
import io
import json
import glob
import os
import re
import datetime

DL = r"C:\Users\ASUS\Downloads"
REFS = r"E:\harness\aic\refs.json"
OUT_TSV = r"E:\harness\aic\待补下载清单.tsv"
OUT_MD = r"E:\harness\aic\待补下载清单.md"

refs = {r["no"]: r for r in json.load(io.open(REFS, encoding="utf-8"))}
files = []
for p in glob.glob(os.path.join(DL, "*.pdf")) + glob.glob(os.path.join(DL, "*.caj")):
    st = os.stat(p)
    if datetime.date.fromtimestamp(st.st_mtime) == datetime.date(2026, 10, 3):
        files.append(os.path.basename(p))


def norm(s):
    return re.sub(r"[\s（）()【】\[\]，,。.、；;：:\"'']", "", s or "")


got = set()
for r in refs.values():
    key = norm(r["title"])
    for f in files:
        if key and (key in norm(f) or norm(f).startswith(key[:14])):
            got.add(r["no"])
            break

missing = [n for n in sorted(refs) if n not in got]

# 缺失条目的检索方案
PLAN = {
    20: {"priority": "中", "query": "仔猪白痢的治疗方法", "hint": "《农村百事通》2026年第8期，第28-29页；报纸类短文，知网可能有 PDF",
         "alt": "该刊为科普刊物，也可直接跳过"},
    26: {"priority": "★★★ 最高", "query": "农业农村部公告 第1027号", "hint": "《中华人民共和国农业农村部公报》2026年第7期，第41-43页",
         "alt": "农业农村部官网「公告」栏目可免费下载原文，不占知网配额"},
    28: {"priority": "★★ 高", "query": "T/CAAA 145-2025 畜禽养殖臭气减控技术规范", "hint": "团体标准，载于《畜牧产业》2026年第7期第34-38页；直接搜标准号更快",
         "alt": "全国团体标准信息平台 ttbz.org.cn 可查标准信息"},
    30: {"priority": "★★ 高", "query": "规模猪场生物安全体系建设与防控", "hint": "《中国畜牧业》2026年第12期，第38-39页；作者 何江鱼",
         "alt": "标题易与其他文章混淆，建议加作者名检索"},
    46: {"priority": "★★★ 最高", "query": "农业农村部公告 第943号", "hint": "《中华人民共和国农业农村部公报》2025年第11期，第35-76页（篇幅大，很可能是药物清单类公告）",
         "alt": "农业农村部官网可免费下载，强烈建议走官网"},
    48: {"priority": "★★★ 最高", "query": "农业农村部公告 第937号", "hint": "《中华人民共和国农业农村部公报》2025年第10期，第108-110页",
         "alt": "农业农村部官网可免费下载"},
    49: {"priority": "★★★ 最高", "query": "农业农村部公告 第930号", "hint": "《中华人民共和国农业农村部公报》2025年第10期，第44-64页（篇幅大）",
         "alt": "农业农村部官网可免费下载"},
    50: {"priority": "低", "query": "日本家禽和猪饲养标准(摘要)", "hint": "《湖南饲料》2006年第6期，第45-48页；年份久，参考价值有限",
         "alt": "可直接跳过"},
}

lines_tsv = ["#\t优先级\t题名\t第一作者\t来源\t年份\t检索式\t备注/替代来源"]
lines_md = [
    "# 待补下载清单（手动下载用）",
    "",
    f"生成时间：2026-10-03　|　已下载 {len(got)} 篇，待补 {len(missing)} 篇",
    "",
    "> 说明：知网单日下载配额已被之前批量下载用尽。以下条目请手动下载，或优先走免费替代来源。",
    "",
    "| # | 优先级 | 题名 | 第一作者 | 来源 | 年份 | 建议检索式 | 备注 / 免费替代来源 |",
    "|---|---|---|---|---|---|---|---|",
]

for n in missing:
    r = refs[n]
    p = PLAN.get(n, {"priority": "中", "query": r["title"], "hint": "", "alt": ""})
    au = r["firstAuthor"] or "(机构文献)"
    note = p["hint"] + (("；替代：" + p["alt"]) if p["alt"] else "")
    lines_tsv.append("\t".join([str(n), p["priority"], r["title"], au, r["source"], r["year"], p["query"], note]))
    lines_md.append(f"| {n} | {p['priority']} | {r['title']} | {au} | {r['source']} | {r['year']} | `{p['query']}` | {note} |")

lines_md += [
    "",
    "## 建议下载顺序",
    "",
    "1. **先拿 4 份农业农村部公告（26、46、48、49）** ——这是你智能体知识库里「禁用药物清单 + 休药期」的核心权威来源，"
    "而且**可以走农业农村部官网免费下载，不消耗知网配额**。",
    "2. 再补 28（团体标准）、30（生物安全体系）——知识库的规范类素材。",
    "3. 20、50 属于可选项，跳过也不影响作品。",
    "",
    "## 知网手动下载注意事项",
    "",
    "- 检索时把「检索项」切到 **篇名**，命中率最高；",
    "- 若弹出「安全验证」滑块，手动滑一次即可，之后同会话内一般不再弹；",
    "- 每篇下载间隔建议 **1 分钟以上**，一天控制在 **20 篇以内**，避免再次触发限流；",
    "- 若提示需要付费，说明机构当日配额已满，**等第二天再试**，不要反复点击。",
]

io.open(OUT_TSV, "w", encoding="utf-8").write("\n".join(lines_tsv))
io.open(OUT_MD, "w", encoding="utf-8").write("\n".join(lines_md))
print(f"待补 {len(missing)} 篇 -> {OUT_TSV}")
print(f"           -> {OUT_MD}\n")
for n in missing:
    r = refs[n]
    p = PLAN.get(n, {})
    print(f"[{n:>2}] {p.get('priority','中'):<9} {r['title']}")
    print(f"      作者/来源: {r['firstAuthor'] or '(机构文献)'} | {r['source']} {r['year']}")
    print(f"      检索式: {p.get('query', r['title'])}")
