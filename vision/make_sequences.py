# -*- coding: utf-8 -*-
"""合成帧序列生成器：验证时序行为判定（站立 / 行走 / 卧倒）。

为什么需要它：
    行为识别里「站立 vs 行走」必须靠连续帧位移才能区分，单帧无解。
    本机没有 opencv，无法从真实视频抽帧，因此用合成序列验证时序逻辑。
    （真实视频验证仍需用户提供素材。）

场景设计（每场景 12 帧，帧率 2fps 等价）：
    T1 静止不动      -> 预期：站立
    T2 匀速横移      -> 预期：行走
    T3 由站到卧      -> 预期：末期休息（面积缩小）
    T4 两头持续重叠且移动 -> 预期：争斗
    T5 采食后离开食槽 -> 预期：前期采食，后期行走
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "synthetic_frames")
W, H = 800, 600
N_FRAMES = 12

REGIONS = {
    "feeder": (0.02 * W, 0.55 * H, 0.35 * W, 0.98 * H),
    "drinker": (0.68 * W, 0.55 * H, 0.98 * W, 0.98 * H),
    "creep": (0.02 * W, 0.02 * H, 0.30 * W, 0.35 * H),
}

# 栏中安全区（不落入任何设施区域）用于静止/移动场景
SAFE_CENTER = (390, 200)


def box(cx, cy, bw=110, bh=56):
    return (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)


def make_sequences():
    seqs = []

    # T1 静止
    s = {"name": "T1_静止不动", "desc": "个体位置不变", "frames": [], "expected_last": {}}
    for _ in range(N_FRAMES):
        s["frames"].append([{"box": box(*SAFE_CENTER), "label": "animal", "score": 0.9}])
    s["expected_last"] = {0: "standing"}
    seqs.append(s)

    # T2 匀速横移（速度 0.05*W/帧 = 40px，归一化位移远大于阈值）
    s = {"name": "T2_匀速行走", "desc": "个体持续横向移动", "frames": [], "expected_last": {}}
    for f in range(N_FRAMES):
        cx = 120 + f * 40
        s["frames"].append([{"box": box(cx, 200), "label": "animal", "score": 0.9}])
    s["expected_last"] = {0: "walking"}
    seqs.append(s)

    # T3 由站到卧：末 4 帧面积明显缩小且不动
    s = {"name": "T3_站立转卧倒", "desc": "末期面积缩小表示卧倒", "frames": [], "expected_last": {}}
    for f in range(N_FRAMES):
        if f < 6:
            b = box(*SAFE_CENTER, bw=110, bh=56)
        else:
            b = box(SAFE_CENTER[0], SAFE_CENTER[1] + 10, bw=132, bh=34)  # 面积显著变小
        s["frames"].append([{"box": b, "label": "animal", "score": 0.9}])
    s["expected_last"] = {0: "resting"}
    seqs.append(s)

    # T4 争斗：两框持续重叠且都在移动
    s = {"name": "T4_持续争斗", "desc": "两框重叠且双方移动", "frames": [], "expected_last": {}}
    for f in range(N_FRAMES):
        cx1 = 300 + (f % 3) * 18
        cx2 = 360 + (f % 3) * 18
        s["frames"].append([
            {"box": box(cx1, 200), "label": "animal", "score": 0.9},
            {"box": box(cx2, 205), "label": "animal", "score": 0.9},
        ])
    s["expected_last"] = {0: "aggressive", 1: "aggressive"}
    seqs.append(s)

    # T5 采食后离开：前 6 帧在食槽，后 6 帧在栏中移动
    s = {"name": "T5_采食后离开", "desc": "前期采食，后期行走", "frames": [],
         "expected_last": {}, "expected_first": {}}
    for f in range(N_FRAMES):
        if f < 6:
            b = box(120, 470)          # 食槽区域内
        else:
            b = box(200 + (f - 6) * 55, 200)
        s["frames"].append([{"box": b, "label": "animal", "score": 0.9}])
    s["expected_last"] = {0: "walking"}
    s["expected_first"] = {0: "eating"}
    seqs.append(s)

    return seqs


def draw(frame_path, dets):
    img = Image.new("RGB", (W, H), (226, 232, 236))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W - 1, H - 1], outline=(150, 160, 170), width=3)
    for name, (x1, y1, x2, y2) in REGIONS.items():
        fill = {"feeder": (198, 178, 140), "drinker": (158, 196, 214),
                "creep": (222, 214, 180)}[name]
        d.rectangle([x1, y1, x2, y2], fill=fill, outline=(140, 150, 158), width=2)
    for det in dets:
        x1, y1, x2, y2 = det["box"]
        col = (90, 110, 200) if det["label"] == "person" else (232, 168, 178)
        d.ellipse([x1, y1, x2, y2], fill=col, outline=(120, 90, 95), width=2)
    img.save(frame_path)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DIR)
    args = ap.parse_args()

    seqs = make_sequences()
    index = []
    for s in seqs:
        d = os.path.join(args.out, s["name"])
        os.makedirs(d, exist_ok=True)
        for i, dets in enumerate(s["frames"]):
            draw(os.path.join(d, f"{i:03d}.png"), dets)
        index.append({"name": s["name"], "desc": s["desc"], "dir": d,
                      "n_frames": len(s["frames"]),
                      "frames": s["frames"],
                      "expected_last": s["expected_last"],
                      "expected_first": s.get("expected_first", {})})
        print(f"生成 {s['name']:<16} {len(s['frames'])} 帧 -> {d}")

    p = os.path.join(args.out, "sequences.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"image_size": [W, H], "sequences": index}, fh, ensure_ascii=False, indent=1)
    print(f"\n共 {len(seqs)} 个序列 -> {p}")


if __name__ == "__main__":
    main()
