# -*- coding: utf-8 -*-
"""检查猪只检测模型的内部结构：类别数、任务类型、输入尺寸。"""
import os
import sys

sys.path.insert(0, r"E:\harness\aic\vision")
import bootstrap  # noqa: F401,E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import torch  # noqa: E402

P = r"E:\harness\aic\vision\models\yolov8n-pig.pt"
sd = torch.load(P, map_location="cpu", weights_only=False)

print("顶层键:", list(sd.keys())[:12])
print("train_args:", sd.get("train_args"))
print("date:", sd.get("date"), "| version:", sd.get("version"))

m = sd.get("model")
print("\nmodel 类型:", type(m).__name__)
if hasattr(m, "yaml"):
    y = m.yaml
    print("yaml nc =", y.get("nc"), "| scale =", y.get("scale"), "| task =", y.get("task"))
    print("yaml names =", y.get("names"))
if hasattr(m, "names"):
    print("m.names =", m.names)

# 直接从检测头读类别数
try:
    head = m.model[-1]
    print("\n检测头类型:", type(head).__name__)
    for attr in ("nc", "no", "nl", "reg_max"):
        if hasattr(head, attr):
            print(f"  head.{attr} =", getattr(head, attr))
    if hasattr(head, "cv3") and len(head.cv3) > 0:
        conv = head.cv3[0][-1]
        print("  cv3 最后一层 out_channels =", conv.out_channels)
except Exception as e:
    print("读检测头失败:", e)

# 统计参数量
try:
    n = sum(p.numel() for p in m.parameters())
    print(f"\n参数量: {n/1e6:.2f} M")
except Exception as e:
    print("统计参数失败:", e)
