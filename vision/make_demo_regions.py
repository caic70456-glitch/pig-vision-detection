# -*- coding: utf-8 -*-
"""为示例图片生成一份标定配置（按目视估计），用于验证标定对行为识别的影响。

真实使用时请用 annotate_regions.py 在图上拖框：
    python annotate_regions.py 你的猪舍照片.jpg
"""
import io
import json
import os
import sys

sys.path.insert(0, r"E:\harness\aic\vision")
import regions as R  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

IMG = r"E:\harness\aic\vision\data\pigdetect\extract\test\images\danuma_1262.jpg"
OUT = r"E:\harness\aic\vision\data\pigdetect\extract\test\regions.json"

# 目视估计（归一化坐标 x1,y1,x2,y2）：
#   画面上方边缘处有一排采食的猪 —— 推测为料槽/料线，取上方带状区域
#   右下角有明显的猪只聚集区 —— 推测为饮水或躺卧热点
#   ⚠ 这是演示值，实际使用时必须在图上重新框选
PIXEL = {
    "feeder": [(150, 8, 520, 62)],         # 上方采食带
    "drinker": [(430, 230, 640, 350)],     # 右下聚集区
    "creep": [],
    "pen": [(90, 5, 640, 355)],            # 栏舍整体范围
}

from PIL import Image  # noqa: E402

im = Image.open(IMG)
W, H = im.size
print(f"图像尺寸: {W}x{H}")

cfg = R.empty_config((W, H), os.path.basename(IMG))
for k, boxes in PIXEL.items():
    cfg["regions"][k]["boxes"] = [
        [round(x1 / W, 6), round(y1 / H, 6), round(x2 / W, 6), round(y2 / H, 6)]
        for (x1, y1, x2, y2) in boxes
    ]
cfg["note"] = ("演示用标定（目视估计），仅用于验证标定流程。"
               "实际部署请用 annotate_regions.py 在图上重新框选。")

R.save_config(cfg, OUT)
print(f"已写入 {OUT}")
print()
print("各区域（像素）：")
for k, boxes in PIXEL.items():
    meta = R.REGION_TYPES[k]
    req = "必需" if meta["required"] else "可选"
    print(f"  {meta['label_cn']:<6} {req}  {boxes if boxes else '（未标定）'}")

problems = R.validate(cfg)
print()
print("校验：" + ("通过" if not problems else ""))
for p in problems:
    print("  -", p)
