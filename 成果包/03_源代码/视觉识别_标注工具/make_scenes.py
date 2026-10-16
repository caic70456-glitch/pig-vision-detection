# -*- coding: utf-8 -*-
"""合成栏舍场景生成器 + 已知答案校验。

用途：本机拿不到任何带猪标注的公开数据集，也无法访问 GitHub/HuggingFace 下载模型。
      为了在「没有真实数据」的条件下仍能验证整条流水线（检测→特征→行为→健康→报告）
      的工程正确性，本模块按「已知标准答案」合成场景，再检查行为推理是否给出预期结论。

重要声明：
    合成图像只用于验证流程正确性，不能用于评估真实识别精度。
    真实精度必须在真实栏舍图像上评估。
"""
import argparse
import json
import math
import os
import random
import sys
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "synthetic")

# 场景模板：每个场景给出目标框、类别与「预期行为」
# box 用像素坐标；图像 800x600
W, H = 800, 600

# 与 scene.py 的设施先验布局保持一致
REGIONS = {
    "feeder": (0.02 * W, 0.55 * H, 0.35 * W, 0.98 * H),
    "drinker": (0.68 * W, 0.55 * H, 0.98 * W, 0.98 * H),
    "creep": (0.02 * W, 0.02 * H, 0.30 * W, 0.35 * H),
}


def box_w_at(region: str, i: int, n: int) -> Tuple[float, float, float, float]:
    """在指定设施区域内生成一个与该区域高度重叠的目标框。

    尺寸与间距经过计算，保证同区域内多个目标框互不重叠——
    否则会触发「框重叠」判据，把同槽采食误判为争斗（实测踩过这个坑）。
    """
    x1, y1, x2, y2 = REGIONS[region]
    rw, rh = x2 - x1, y2 - y1
    bw, bh = rw * 0.30, rh * 0.34
    cols = max(1, n)
    cx = x1 + rw * (i + 0.5) / cols
    cy = y1 + rh * 0.55
    return (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)


def make_scenes() -> List[dict]:
    """构造 6 个场景，覆盖六类行为与若干边界情况。"""
    scenes = []

    # S1 全群采食：4 头都在食槽
    s1 = {"name": "S1_全群采食", "desc": "4 头个体集中在食槽区",
          "detections": [], "expected": {}}
    for i in range(4):
        s1["detections"].append({"box": box_w_at("feeder", i, 4), "label": "animal", "score": 0.9})
        s1["expected"][i] = "eating"
    scenes.append(s1)

    # S2 混合行为：2 采食 + 1 饮水 + 2 休息
    # 休息目标必须放在「栏中」，且中心点不能落进任何设施区域，
    # 否则会被设施锚定规则判成采食/饮水（实测踩过这个坑）。
    s2 = {"name": "S2_混合行为", "desc": "2 头采食、1 头饮水、2 头栏中休息",
          "detections": [], "expected": {}}
    for i in range(2):
        s2["detections"].append({"box": box_w_at("feeder", i, 2), "label": "animal", "score": 0.88})
        s2["expected"][i] = "eating"
    # 饮水器区域为 x 544-784，y 330-588；目标中心取 620 以落在区域内
    s2["detections"].append({"box": (578, 420, 662, 465), "label": "animal", "score": 0.87})
    s2["expected"][2] = "drinking"
    # 栏中休息：中心 (390,337) 与 (480,337)，均在设施区域之外
    s2["detections"].append({"box": (340, 315, 440, 360), "label": "animal", "score": 0.9})
    s2["expected"][3] = "resting"
    s2["detections"].append({"box": (435, 315, 525, 360), "label": "animal", "score": 0.9})
    s2["expected"][4] = "resting"
    scenes.append(s2)

    # S3 争斗：两个框大幅重叠
    s3 = {"name": "S3_争斗重叠", "desc": "两头个体框重叠明显，疑似争斗",
          "detections": [
              {"box": (300, 250, 430, 330), "label": "animal", "score": 0.9},
              {"box": (350, 260, 480, 340), "label": "animal", "score": 0.9},
              {"box": (60, 80, 160, 130), "label": "animal", "score": 0.85}],
          "expected": {0: "aggressive", 1: "aggressive", 2: "resting"}}
    scenes.append(s3)

    # S4 拥挤：6 头密集，多数互相接触
    # 注意：必须全部布置在「栏中」，不能压到设施区域，否则会被设施锚定规则
    # 判成采食/饮水（实测踩过这个坑）。下方 3 头仍保持相互重叠以模拟拥挤。
    s4 = {"name": "S4_高密度拥挤", "desc": "6 头密集分布，普遍相互接触",
          "detections": [], "expected": {}}
    for i in range(6):
        x = 160 + (i % 3) * 130
        y = 180 + (i // 3) * 90
        s4["detections"].append({"box": (x, y, x + 120, y + 70), "label": "animal", "score": 0.86})
        s4["expected"][i] = "resting"
    scenes.append(s4)

    # S5 空栏（负样本）
    s5 = {"name": "S5_空栏负样本", "desc": "栏舍内无个体",
          "detections": [], "expected": {}}
    scenes.append(s5)

    # S6 含人员
    # 三个休息目标中心控制在栏中，避开食槽(x<280,y>330)、饮水器(x>544,y>330)、
    # 保温区(x<240,y<210) 三个设施区域。
    s6 = {"name": "S6_有人作业", "desc": "3 头休息，1 名人员在栏内",
          "detections": [
              {"box": (280, 280, 400, 325), "label": "animal", "score": 0.88},
              {"box": (400, 280, 520, 325), "label": "animal", "score": 0.88},
              {"box": (330, 240, 450, 285), "label": "animal", "score": 0.88},
              {"box": (620, 120, 700, 300), "label": "person", "score": 0.93}],
          "expected": {0: "resting", 1: "resting", 2: "resting"}}
    scenes.append(s6)
    return scenes


def draw_scene(scene: dict, path: str):
    """把场景渲染成图像，便于人工查看与网页演示。"""
    img = Image.new("RGB", (W, H), (226, 232, 236))
    d = ImageDraw.Draw(img)

    # 栏舍地面与设施
    d.rectangle([0, 0, W - 1, H - 1], outline=(150, 160, 170), width=3)
    for name, (x1, y1, x2, y2) in REGIONS.items():
        fill = {"feeder": (198, 178, 140), "drinker": (158, 196, 214),
                "creep": (222, 214, 180)}[name]
        d.rectangle([x1, y1, x2, y2], fill=fill, outline=(140, 150, 158), width=2)
        d.text((x1 + 6, y1 + 6), {"feeder": "FEEDER", "drinker": "DRINKER",
                                  "creep": "CREEP"}[name], fill=(70, 80, 90))

    for det in scene["detections"]:
        x1, y1, x2, y2 = det["box"]
        if det["label"] == "person":
            color = (90, 110, 200)
        else:
            color = (232, 168, 178)
        d.ellipse([x1, y1, x2, y2], fill=color, outline=(120, 90, 95), width=2)

    d.text((10, H - 20), scene["name"] + "  " + scene["desc"], fill=(60, 70, 80))
    img.save(path)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DIR)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    scenes = make_scenes()
    index = []
    for s in scenes:
        p = os.path.join(args.out, s["name"] + ".png")
        draw_scene(s, p)
        index.append({"name": s["name"], "desc": s["desc"], "image": p,
                      "detections": s["detections"], "expected": s["expected"]})
        print(f"生成 {s['name']:<18} {len(s['detections'])} 个目标  -> {os.path.basename(p)}")

    meta = os.path.join(args.out, "scenes.json")
    with open(meta, "w", encoding="utf-8") as fh:
        json.dump({"image_size": [W, H], "scenes": index}, fh, ensure_ascii=False, indent=1)
    print(f"\n共 {len(scenes)} 个场景，元数据 -> {meta}")
    print("说明：合成图像仅用于验证流程正确性，不能用于评估真实识别精度。")


if __name__ == "__main__":
    main()
