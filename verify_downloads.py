# -*- coding: utf-8 -*-
"""核验已下载文献：匹配清单、检查文件头、生成清单报告。"""
import glob
import io
import json
import os
import re

DL = r"C:\Users\ASUS\Downloads"
REFS = r"E:\harness\aic\refs.json"
OUT = r"E:\harness\aic\已下载文献清单.tsv"

refs = json.load(io.open(REFS, encoding="utf-8"))

files = []
for p in glob.glob(os.path.join(DL, "*.pdf")) + glob.glob(os.path.join(DL, "*.caj")):
    st = os.stat(p)
    files.append({"name": os.path.basename(p), "path": p, "size": st.st_size, "mtime": st.st_mtime})

# 只看今天下载的
import datetime
today = datetime.date(2026, 10, 3)
files = [f for f in files if datetime.date.fromtimestamp(f["mtime"]) == today]


def norm(s):
    return re.sub(r"[\s（）()【】\[\]，,。.、；;：:\"'']", "", s or "")


def head_ok(path):
    with open(path, "rb") as fh:
        head = fh.read(8)
    if path.lower().endswith(".pdf"):
        return head.startswith(b"%PDF")
    return head[:4] in (b"CAJ", b"\xca\xca") or head[:2] == b"CA"


report = []
used = set()
for r in refs:
    key = norm(r["title"])
    hit = None
    for f in files:
        if f["name"] in used:
            continue
        if key and (key in norm(f["name"]) or norm(f["name"]).startswith(key[:14])):
            hit = f
            break
    if hit:
        used.add(hit["name"])
        valid = head_ok(hit["path"])
        report.append((r["no"], "已下载" if valid else "文件异常", r["title"], r["firstAuthor"],
                       r["source"], r["year"], hit["name"], round(hit["size"] / 1024), valid))
    else:
        report.append((r["no"], "缺失", r["title"], r["firstAuthor"], r["source"], r["year"], "", "", ""))

unmatched = [f for f in files if f["name"] not in used]

lines = ["#\t状态\t题名\t第一作者\t来源\t年份\t文件名\t大小KB\t文件头有效"]
lines += ["\t".join(str(x) for x in row) for row in report]
lines.append("")
lines.append("# 未匹配到清单的文件")
lines += ["\t\t" + f["name"] + "\t" + str(round(f["size"] / 1024)) + "\t" + str(head_ok(f["path"])) for f in unmatched]

io.open(OUT, "w", encoding="utf-8").write("\n".join(lines))

got = [r for r in report if r[1] == "已下载"]
bad = [r for r in report if r[1] == "文件异常"]
miss = [r for r in report if r[1] == "缺失"]
print("=" * 70)
print(f"清单总数 {len(refs)} 篇")
print(f"  已下载且文件头有效 : {len(got)} 篇")
print(f"  文件头异常         : {len(bad)} 篇 {[r[0] for r in bad]}")
print(f"  缺失               : {len(miss)} 篇 {[r[0] for r in miss]}")
print(f"  多余文件           : {len(unmatched)} 个")
print("=" * 70)
print("缺失明细：")
for r in miss:
    print(f"  [{r[0]:>2}] {r[2][:40]:<42} | {r[3] or '(机构文献)':<8} | {r[4]}")
print("\n多余文件：")
for f in unmatched:
    print(f"  {f['name']}  ({round(f['size']/1024)} KB)")
print(f"\n报告已写入 {OUT}")
