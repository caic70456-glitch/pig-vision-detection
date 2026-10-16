# -*- coding: utf-8 -*-
"""设施区域配置：定义、读写、与图像分辨率无关的坐标转换。

设计要点：
    区域坐标以**归一化形式**（0~1，相对图像宽高）保存。
    这样同一份配置可以套用到不同分辨率的图片或视频帧上——
    猪舍相机可能改分辨率、抽帧可能改变尺寸，用归一化坐标就不会错位。

配置格式（regions.json）：
    {
      "image_size": [1280, 720],          # 标定时所用图像尺寸，仅供参考
      "source_image": "pen.jpg",
      "regions": {
        "feeder":  {"label_cn": "食槽",   "boxes": [[x1,y1,x2,y2], ...]},
        "drinker": {"label_cn": "饮水器", "boxes": [[...]]},
        "creep":   {"label_cn": "保温区", "boxes": [[...]]},
        "pen":     {"label_cn": "栏舍边界","boxes": [[...]]}
      },
      "note": "..."
    }
"""
import io
import json
import os
from typing import Dict, List, Optional, Tuple

# 可标定的区域类型。feeder / drinker 是行为识别必需的（采食、饮水依赖它们）；
# creep / pen 用于位置分析与报告，缺失不影响基本行为识别。
REGION_TYPES = {
    "feeder": {"label_cn": "食槽", "color": (214, 196, 158), "required": True},
    "drinker": {"label_cn": "饮水器", "color": (176, 210, 226), "required": True},
    "creep": {"label_cn": "保温区", "color": (232, 226, 196), "required": False},
    "pen": {"label_cn": "栏舍边界", "color": (200, 205, 210), "required": False},
}

DEFAULT_CONFIG_NAME = "regions.json"


def empty_config(image_size=None, source_image=None) -> dict:
    return {
        "image_size": list(image_size) if image_size else None,
        "source_image": source_image,
        "regions": {k: {"label_cn": v["label_cn"], "boxes": []} for k, v in REGION_TYPES.items()},
        "note": "由 annotate_regions.py 生成；坐标为归一化值（0~1），与图像分辨率无关。",
    }


def save_config(cfg: dict, path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=1)
    return path


def load_config(path: str) -> Optional[dict]:
    if not os.path.isfile(path):
        return None
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def find_config_for(image_path: str) -> Optional[str]:
    """在图像同目录及其父目录寻找 regions.json。"""
    d = os.path.dirname(os.path.abspath(image_path))
    for _ in range(3):
        p = os.path.join(d, DEFAULT_CONFIG_NAME)
        if os.path.isfile(p):
            return p
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return None


def to_pixel_regions(cfg: dict, image_size: Tuple[int, int]):
    """把归一化配置转成 scene.Region 列表。

    image_size: (width, height)
    """
    from scene import Region  # 延迟导入，避免循环依赖

    w, h = image_size
    out = []
    for rtype, spec in (cfg.get("regions") or {}).items():
        label_cn = (REGION_TYPES.get(rtype, {}).get("label_cn")
                    or spec.get("label_cn") or rtype)
        for box in spec.get("boxes", []):
            if len(box) != 4:
                continue
            x1, y1, x2, y2 = box
            out.append(Region(rtype, (x1 * w, y1 * h, x2 * w, y2 * h),
                              f"{label_cn}（标定）"))
    return out


def from_pixel_regions(regions_regions, image_size: Tuple[int, int], cfg: dict) -> dict:
    """把像素坐标的区域写回归一化配置（供程序化标定时使用）。"""
    w, h = image_size
    for r in regions_regions:
        spec = cfg["regions"].setdefault(
            r.name, {"label_cn": REGION_TYPES.get(r.name, {}).get("label_cn", r.name),
                     "boxes": []})
        x1, y1, x2, y2 = r.box
        spec["boxes"].append([round(x1 / w, 6), round(y1 / h, 6),
                              round(x2 / w, 6), round(y2 / h, 6)])
    return cfg


def validate(cfg: dict) -> List[str]:
    """检查配置完整性，返回问题列表（空列表表示通过）。"""
    problems = []
    regs = cfg.get("regions") or {}
    for rtype, meta in REGION_TYPES.items():
        boxes = (regs.get(rtype) or {}).get("boxes") or []
        if meta["required"] and not boxes:
            problems.append(f"缺少必需区域：{meta['label_cn']}（{rtype}）")
        for i, b in enumerate(boxes):
            if len(b) != 4:
                problems.append(f"{rtype} 第 {i+1} 个框坐标数量不为 4")
                continue
            x1, y1, x2, y2 = b
            if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
                problems.append(f"{rtype} 第 {i+1} 个框坐标越界或顺序错误: {b}")
    # 重叠提示（不阻断，仅提醒）
    fb = (regs.get("feeder") or {}).get("boxes") or []
    db = (regs.get("drinker") or {}).get("boxes") or []
    for a in fb:
        for b in db:
            if _overlap(a, b) > 0.4:
                problems.append(f"食槽与饮水器区域重叠较多，可能影响区分（{a} 与 {b}）")
    return problems


def _iou_norm(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    return inter / area_a if area_a > 0 else 0.0


_overlap = _iou_norm


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print("可标定区域类型：")
    for k, v in REGION_TYPES.items():
        req = "必需" if v["required"] else "可选"
        print(f"  {k:<9} {v['label_cn']:<6} {req}  颜色 {v['color']}")
