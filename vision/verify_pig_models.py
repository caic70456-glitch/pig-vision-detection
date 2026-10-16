# -*- coding: utf-8 -*-
"""验证猪只检测模型：类别数、训练数据集、是否真为单类猪检测器。"""
import os
import sys

sys.path.insert(0, r"E:\harness\aic\vision")
import bootstrap  # noqa: F401,E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import torch  # noqa: E402

MODELS = r"E:\harness\aic\vision\models"
FILES = ["yolov8n-pig.pt", "yolov8s-pig.pt", "yolov8m-pig.pt", "yolov8n-coco.pt"]

print(f"{'文件':<20}{'大小MB':>8}{'head.nc':>9}{'训练数据':>14}{'轮数':>7}  类别名")
print("-" * 100)
for f in FILES:
    p = os.path.join(MODELS, f)
    if not os.path.isfile(p):
        print(f"{f:<20}{'缺失':>8}")
        continue
    mb = os.path.getsize(p) / 1e6
    try:
        sd = torch.load(p, map_location="cpu", weights_only=False)
        ta = sd.get("train_args") or {}
        m = sd.get("model")
        head = m.model[-1]
        nc = getattr(head, "nc", None)
        names = m.names
        if isinstance(names, dict):
            shown = list(names.values())[:4]
        else:
            shown = list(names)[:4]
        print(f"{f:<20}{mb:>8.2f}{str(nc):>9}{str(ta.get('data')):>14}"
              f"{str(ta.get('epochs')):>7}  {shown}")
    except Exception as e:
        print(f"{f:<20}{mb:>8.2f}   读取失败: {str(e)[:40]}")

print("\n判据：真正的猪只单类检测器应满足 head.nc == 1 且 names 为 ['pig'] 之类；")
print("      head.nc == 80 说明是 COCO 预训练模型，不是猪检测器。")
