# -*- coding: utf-8 -*-
"""把训练好的猪检测器导出为 ONNX（便于脱离 ultralytics 部署）。"""
import os
import shutil
import sys

sys.path.insert(0, r"E:\harness\aic\vision")
import bootstrap  # noqa: F401,E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MODELS = r"E:\harness\aic\vision\models"
PT = os.path.join(MODELS, "pig-detector-yolov8n.pt")

from ultralytics import YOLO  # noqa: E402

m = YOLO(PT)
out = m.export(format="onnx", imgsz=640, opset=17, simplify=True, dynamic=False)
print("导出的 ONNX:", out)

# 移到 models/ 根目录并起个清楚的名字
dst = os.path.join(MODELS, "pig-detector-yolov8n.onnx")
if os.path.abspath(out) != os.path.abspath(dst):
    shutil.move(out, dst)
print(f"已就位: {dst}  ({os.path.getsize(dst)/1e6:.2f} MB)")
