# -*- coding: utf-8 -*-
"""收集制作 PPT 所需的事实与素材。"""
import io
import json
import os
import sys

sys.path.insert(0, r"E:\harness\aic")
import metrics_source as M  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

VISION = r"E:\harness\aic\vision"

print("=== 时序评测：序列名称与结果 ===")
p = os.path.join(VISION, "results", "eval_temporal_synthetic.json")
d = json.load(io.open(p, encoding="utf-8"))
for s in d.get("sequences", []):
    dist = s.get("distribution_pct") or {}
    top = "、".join(f"{k} {v:.0f}%" for k, v in dist.items() if v > 0)
    print(f"  {s['sequence']:<16} 判定={'OK' if s.get('correct') else 'NG'}  {top}")
print(f"  合计 {d.get('n_correct')}/{d.get('n_checks')}")

print("\n=== 单帧评测：场景列表 ===")
p2 = os.path.join(VISION, "results", "eval_behavior_synthetic.json")
d2 = json.load(io.open(p2, encoding="utf-8"))
for s in d2.get("scenes", []):
    print(f"  {s['scene']:<16} {s['correct']}/{s['targets']}")

print("\n=== 可用图片素材 ===")
TEST_IMG = os.path.join(VISION, "data", "pigdetect", "extract", "test", "images")
if os.path.isdir(TEST_IMG):
    fs = sorted(f for f in os.listdir(TEST_IMG) if f.lower().endswith((".jpg", ".png")))
    print(f"  真实猪舍图片 {len(fs)} 张，示例：{fs[:3]}")
# 可视化输出目录
for sub in ("web/cache", "synthetic", "synthetic_frames"):
    p3 = os.path.join(VISION, sub)
    if os.path.isdir(p3):
        n = sum(len(f) for _r, _d, f in os.walk(p3))
        print(f"  {sub}: {n} 个文件")

print("\n=== 指标 ===")
print("  知识库:", M.kb_stats())
print("  诊断:", M.dx_eval())
print("  检测:", M.detection())
print("  标定:", M.region_calibration())
