# -*- coding: utf-8 -*-
"""确认 COCO 预训练检测器中的猪相关类别索引，并测试推理速度。"""
import os
import sys
import time

PYLIBS = r"E:\harness\aic\vision\pylibs"
sys.path.insert(0, PYLIBS)
os.environ["TORCH_HOME"] = r"E:\harness\aic\vision\models"

import torch  # noqa: E402
import torchvision  # noqa: E402
from torchvision.models.detection import (  # noqa: E402
    fasterrcnn_mobilenet_v3_large_320_fpn,
    FasterRCNN_MobileNet_V3_Large_320_FPN_Weights,
)

print("torch", torch.__version__, "| torchvision", torchvision.__version__)
print("线程数:", torch.get_num_threads())

w = FasterRCNN_MobileNet_V3_Large_320_FPN_Weights.COCO_V1
cats = w.meta["categories"]
print(f"\nCOCO 类别总数: {len(cats)}")
print("与畜禽相关的类别：")
for i, c in enumerate(cats):
    if c in ("pig", "cow", "sheep", "dog", "horse", "bird", "cat", "person",
             "chicken", "duck", "goat"):
        print(f"  index {i:>2}: {c}")

# 找到 pig
pig_idx = [i for i, c in enumerate(cats) if c == "pig"]
print(f"\n★ pig 类别索引: {pig_idx}")

t0 = time.time()
model = fasterrcnn_mobilenet_v3_large_320_fpn(weights=w)
model.eval()
print(f"模型加载完成，耗时 {time.time() - t0:.1f}s")

# 推理速度测试（用随机图，模拟 320 输入）
from torchvision.transforms.functional import to_tensor  # noqa: E402
from PIL import Image  # noqa: E402
import numpy as np  # noqa: E402

img = Image.fromarray((np.random.rand(480, 640, 3) * 255).astype("uint8"))
x = to_tensor(img)

with torch.no_grad():
    for _ in range(2):
        model([x])
    t0 = time.time()
    for _ in range(3):
        out = model([x])[0]
    dt = (time.time() - t0) / 3
print(f"单张推理耗时: {dt*1000:.0f} ms  (随机噪声图，无真实目标)")
print(f"输出框数量: {len(out['boxes'])}")
