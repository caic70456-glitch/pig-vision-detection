# -*- coding: utf-8 -*-
"""争斗判据阈值扫描：在标定区域下寻找更合理的 IoU 阈值。

背景：密集采食时相邻个体框难免重叠，把「框重叠」当成争斗会大量误报。
本脚本扫描 fight_iou 阈值，观察「争斗」占比的变化，为定参提供依据。
"""
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, r"E:\harness\aic\vision")
import bootstrap  # noqa: F401,E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import behavior  # noqa: E402
import detector  # noqa: E402
import regions as R  # noqa: E402
from behavior import BEHAVIOR_CN, classify_scene  # noqa: E402
from scene import compute_scene  # noqa: E402

BASE = r"E:\harness\aic\vision"
IMG_DIR = os.path.join(BASE, "data", "pigdetect", "extract", "test", "images")
CFG = os.path.join(BASE, "data", "pigdetect", "extract", "test", "regions.json")
OUT = os.path.join(BASE, "results", "fight_threshold_sweep.json")

N_IMAGES = 12
THRESHOLDS = [0.12, 0.18, 0.25, 0.35, 0.45, 0.60]


def main():
    cfg = R.load_config(CFG)
    backend = detector.build_backend(kind="auto")
    imgs = sorted(f for f in os.listdir(IMG_DIR) if f.endswith(".jpg"))[:N_IMAGES]

    # 预先检测一次，避免阈值扫描时重复推理（CPU 上很贵）
    from PIL import Image
    print(f"预检测 {len(imgs)} 张图……")
    cached = []
    for n in imgs:
        p = os.path.join(IMG_DIR, n)
        img = Image.open(p)
        W, H = img.size
        res = backend.detect(img)
        cached.append((n, res, (W, H)))
    total = sum(len(r.animals) for _, r, _ in cached)
    print(f"共 {total} 个目标\n")

    print(f"{'fight_iou':>10}{'争斗数':>8}{'争斗占比':>10}{'采食占比':>10}{'站立占比':>10}")
    print("-" * 52)

    results = []
    for th in THRESHOLDS:
        behavior.TH["fight_iou"] = th
        cnt = Counter()
        for n, res, (W, H) in cached:
            region_objs = R.to_pixel_regions(cfg, (W, H))
            sc = compute_scene(res, regions=region_objs)
            bh = classify_scene(sc, tracks=[], track_scenes=1)
            cnt.update(v.behavior for v in bh.verdicts)
        t = sum(cnt.values()) or 1
        row = {
            "fight_iou": th,
            "aggressive": cnt.get("aggressive", 0),
            "aggressive_pct": round(cnt.get("aggressive", 0) * 100 / t, 1),
            "eating_pct": round(cnt.get("eating", 0) * 100 / t, 1),
            "standing_pct": round(cnt.get("standing", 0) * 100 / t, 1),
            "resting_pct": round(cnt.get("resting", 0) * 100 / t, 1),
            "drinking_pct": round(cnt.get("drinking", 0) * 100 / t, 1),
        }
        results.append(row)
        print(f"{th:>10.2f}{row['aggressive']:>8}{row['aggressive_pct']:>9.1f}%"
              f"{row['eating_pct']:>9.1f}%{row['standing_pct']:>9.1f}%")

    print("-" * 52)
    print("\n参考：猪群实际争斗行为通常只占很小比例（<5%）。")
    print("阈值越高越保守，误报越少但可能漏检真实争斗。")
    print("注意：这是单帧静态判据，真实视频中还应要求「双方均有位移」。")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(
        {"note": "标定区域下的争斗阈值扫描；数据为真实猪舍图片，检测器为自训模型",
         "n_images": len(imgs), "n_targets": total, "sweep": results},
        ensure_ascii=False, indent=1))
    print(f"\n结果已写入 {OUT}")


if __name__ == "__main__":
    main()
