# -*- coding: utf-8 -*-
"""检查 PigBench COCO 标注：图片数、标注框数、类别分布、尺寸分布。"""
import io
import json
import os
import sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

P = r"E:\harness\aic\vision\data\pigdetect\val.json"

with io.open(P, encoding="utf-8") as fh:
    d = json.load(fh)

print("顶层字段:", list(d.keys()))
imgs = d.get("images", [])
anns = d.get("annotations", [])
cats = d.get("categories", [])

print(f"\n图片数 : {len(imgs)}")
print(f"标注框 : {len(anns)}")
print(f"类别   : {json.dumps(cats, ensure_ascii=False)}")

# 类别分布
cc = Counter(a["category_id"] for a in anns)
print("\n按类别统计框数:")
for c in cats:
    print(f"  id={c['id']} {c.get('name')}: {cc.get(c['id'], 0)} 个")

# 每图框数分布
per_img = Counter()
for a in anns:
    per_img[a["image_id"]] += 1
if per_img:
    vals = sorted(per_img.values())
    print(f"\n每图框数: 最少 {vals[0]}, 中位 {vals[len(vals)//2]}, 最多 {vals[-1]}, "
          f"平均 {sum(vals)/len(vals):.1f}")

# 图片尺寸
if imgs:
    ws = [i.get("width", 0) for i in imgs]
    hs = [i.get("height", 0) for i in imgs]
    print(f"图片尺寸: 宽 {min(ws)}-{max(ws)}, 高 {min(hs)}-{max(hs)}")

# 框面积占比分布（判断远景/近景）
areas = []
for a in anns:
    for im in imgs:
        if im["id"] == a["image_id"]:
            bb = a["bbox"]
            if im.get("width") and im.get("height"):
                areas.append((bb[2] * bb[3]) / (im["width"] * im["height"]))
            break
if areas:
    areas.sort()
    print(f"\n框面积占图比例: 中位 {areas[len(areas)//2]:.4f}, "
          f"5%分位 {areas[len(areas)//20]:.4f}, 95%分位 {areas[int(len(areas)*0.95)]:.4f}")
    print(f"  小目标(<1%图面积)占比: {sum(1 for x in areas if x < 0.01)/len(areas):.1%}")

# 样例文件名
print("\n前 5 个图片记录:")
for im in imgs[:5]:
    print("  ", json.dumps(im, ensure_ascii=False))
print("\n前 3 个标注:")
for a in anns[:3]:
    print("  ", json.dumps(a, ensure_ascii=False))
