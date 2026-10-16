# -*- coding: utf-8 -*-
"""可视化：把检测框、设施区域、行为标签画到图上，用于报告与演示。"""
import os
from typing import Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont

from behavior import BEHAVIOR_CN, BehaviorResult
from detector import Detection, DetectionResult
from scene import Region, SceneFeature

# 行为配色（RGB）
BEHAVIOR_COLOR = {
    "eating": (46, 160, 67),
    "drinking": (31, 119, 180),
    "resting": (255, 165, 0),
    "standing": (110, 110, 110),
    "walking": (150, 60, 200),
    "aggressive": (220, 40, 40),
    "unknown": (150, 150, 150),
}
REGION_COLOR = {
    "feeder": (214, 196, 158),
    "drinker": (176, 210, 226),
    "creep": (232, 226, 196),
}


def _font(size=15):
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf",
              r"C:\Windows\Fonts\simsun.ttc"):
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def annotate(image_path: str, result: DetectionResult, scene: SceneFeature,
             behavior: BehaviorResult, out_path: str,
             title: Optional[str] = None) -> str:
    """在图上绘制检测结果、设施区域与行为标签。"""
    img = Image.open(image_path).convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")

    # 设施区域（半透明填充 + 边框）
    for r in scene.regions:
        col = REGION_COLOR.get(r.name, (220, 220, 220))
        x1, y1, x2, y2 = r.box
        d.rectangle([x1, y1, x2, y2], fill=col + (70,), outline=col, width=2)
        d.text((x1 + 6, y1 + 6), r.label_cn or r.name, fill=(80, 80, 80), font=_font(13))

    # 逐个目标
    animals = result.animals
    for i, det in enumerate(animals):
        v = behavior.verdicts[i] if i < len(behavior.verdicts) else None
        b = v.behavior if v else "unknown"
        col = BEHAVIOR_COLOR.get(b, (120, 120, 120))
        x1, y1, x2, y2 = det.box
        d.rectangle([x1, y1, x2, y2], outline=col, width=3)

        label = f"#{i+1} {BEHAVIOR_CN.get(b, b)}"
        if v:
            label += f" {v.confidence:.0%}"
        f = _font(14)
        tb = d.textbbox((0, 0), label, font=f)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        ty = max(0, y1 - th - 8)
        d.rectangle([x1, ty, x1 + tw + 10, ty + th + 6], fill=col)
        d.text((x1 + 5, ty + 3), label, fill=(255, 255, 255), font=f)

    # 人员
    for det in result.detections:
        if det.label == "person":
            x1, y1, x2, y2 = det.box
            d.rectangle([x1, y1, x2, y2], outline=(90, 110, 200), width=3)
            d.text((x1 + 4, max(0, y1 - 18)), "人员", fill=(40, 60, 160), font=_font(13))

    # 顶部信息条
    if title:
        f = _font(17)
        tb = d.textbbox((0, 0), title, font=f)
        d.rectangle([0, 0, img.width, tb[3] + 12], fill=(30, 40, 50, 210))
        d.text((10, 6), title, fill=(255, 255, 255), font=f)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path)
    return out_path


def highlight_regions_only(image_path: str, regions: List[Region], out_path: str) -> str:
    """只画设施区域，用于说明「首次部署人工标定区域」这一步。"""
    img = Image.open(image_path).convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    for r in regions:
        col = REGION_COLOR.get(r.name, (220, 220, 220))
        x1, y1, x2, y2 = r.box
        d.rectangle([x1, y1, x2, y2], fill=col + (80,), outline=col, width=3)
        d.text((x1 + 8, y1 + 8), r.label_cn or r.name, fill=(60, 60, 60), font=_font(15))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path)
    return out_path
