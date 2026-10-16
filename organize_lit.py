# -*- coding: utf-8 -*-
"""把已下载的文献 PDF 归集到 Downloads\\AIC-文献\\ ，并同时把全文文本抽取出来。

只移动文件，不改内容。每一步都校验绝对路径，移动前确认目标是 Downloads 下的预期目录。
"""
import io
import json
import os
import re
import shutil
import datetime

HOME = r"C:\Users\ASUS"
DL = os.path.join(HOME, "Downloads")
DEST = os.path.join(DL, "AIC-文献")
TEXT_DIR = os.path.join(DEST, "文本")
REFS = r"E:\harness\aic\refs.json"

# 安全检查：目标必须确实在 Downloads 下
assert os.path.normcase(os.path.dirname(DEST)) == os.path.normcase(DL), "目标目录越界"
assert os.path.isdir(DL), "Downloads 不存在"

os.makedirs(DEST, exist_ok=True)
os.makedirs(TEXT_DIR, exist_ok=True)

refs = json.load(io.open(REFS, encoding="utf-8"))


def norm(s):
    return re.sub(r"[\s（）()【】\[\]，,。.、；;：:\"'']", "", s or "")


# 今日下载的 PDF/CAJ
today = datetime.date(2026, 10, 3)
cands = []
for name in os.listdir(DL):
    p = os.path.join(DL, name)
    if not os.path.isfile(p):
        continue
    if os.path.splitext(name)[1].lower() not in (".pdf", ".caj"):
        continue
    if datetime.date.fromtimestamp(os.path.getmtime(p)) != today:
        continue
    cands.append(name)

print(f"Downloads 中今日新增文献文件：{len(cands)} 个")

# 编号 -> 文件名映射
mapping = {}
for r in refs:
    key = norm(r["title"])
    best = None
    for name in cands:
        if key and (key in norm(name) or norm(name).startswith(key[:14])):
            best = name
            break
    if best:
        mapping[r["no"]] = best

moved, skipped = [], []
for no in sorted(mapping):
    name = mapping[no]
    src = os.path.join(DL, name)
    dst = os.path.join(DEST, f"{no:02d}_{name}")
    if not os.path.isfile(src):
        skipped.append((no, name, "源文件不存在"))
        continue
    if os.path.abspath(os.path.dirname(src)) != os.path.abspath(DL):
        skipped.append((no, name, "源不在 Downloads"))
        continue
    shutil.move(src, dst)
    moved.append((no, os.path.basename(dst)))

print(f"已归集 {len(moved)} 个 -> {DEST}")

# 剩下没被认领的，列出来让用户判断
left = [n for n in cands if n not in mapping.values()]
print(f"\n未归集（需你确认）：{len(left)} 个")
for n in left:
    print("   ", n)

# 导出编号->文件名对照
with io.open(os.path.join(DEST, "_编号对照.txt"), "w", encoding="utf-8") as fh:
    for no in sorted(mapping):
        r = next(x for x in refs if x["no"] == no)
        fh.write(f"[{no:02d}] {r['title']}\n      文件: {mapping[no]}\n")

json.dump({str(k): v for k, v in mapping.items()},
          io.open(r"E:\harness\aic\file_map.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"\n对照表已写入 {os.path.join(DEST, '_编号对照.txt')}")
