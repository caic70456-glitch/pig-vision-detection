# -*- coding: utf-8 -*-
"""场景结构特征层：把「检测框」翻译成「可用于行为推理的几何与时间特征」。

设计原则（这是本项目最重要的方法论修正）：
    行为不是物体的静态属性。单帧图像里，猪头低着可能是采食、可能是嗅探；
    「争斗」与「并排休息」在单帧上高度相似；「行走」必须靠连续帧位移才能判断。
    所以本层只产出客观的几何/时间量，把「行为」的判断留给 behavior.py 的显式规则，
    而**不让检测器直接输出行为类别**（那是把时序动作当成物体类别的常见错误）。
"""
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from detector import Detection, DetectionResult


@dataclass
class Region:
    """栏位设施区域（食槽/饮水器/保温区等）。可手工框选，也可由配置给出。"""
    name: str           # feeder / drinker / pen / creep
    box: Tuple[float, float, float, float]
    label_cn: str = ""

    def contains_center(self, det: Detection) -> bool:
        cx, cy = det.center
        x1, y1, x2, y2 = self.box
        return x1 <= cx <= x2 and y1 <= cy <= y2

    def overlap_ratio(self, det: Detection) -> float:
        """检测框与区域的重叠面积 / 检测框面积。用于判断「猪是否在食槽处」。"""
        ax1, ay1, ax2, ay2 = det.box
        bx1, by1, bx2, by2 = self.box
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
        inter = iw * ih
        return inter / det.area if det.area > 0 else 0.0

    def to_dict(self):
        return {"name": self.name, "label_cn": self.label_cn,
                "box": [round(float(v), 1) for v in self.box]}


DEFAULT_REGION_LABELS = {
    "feeder": "食槽", "drinker": "饮水器", "pen": "栏舍", "creep": "保温区",
}


@dataclass
class AnimalFeature:
    """单个动物的几何特征。"""
    index: int
    box: Tuple[float, float, float, float]
    center: Tuple[float, float]
    area: float
    area_ratio: float                     # 占整图面积比，用于估相对体型
    aspect: float                         # 宽高比：站立/行走时偏横长，躺卧时偏扁
    in_regions: List[str] = field(default_factory=list)
    region_overlap: Dict[str, float] = field(default_factory=dict)
    touch_count: int = 0                  # 与多少其他个体框重叠（疑似接触/拥挤）
    max_iou: float = 0.0
    neighbor_speed: float = 0.0           # 重叠最多的那个邻居的运动速度（时序判据用）
    neighbor_index: int = -1

    def to_dict(self):
        return {
            "index": self.index,
            "box": [round(float(v), 1) for v in self.box],
            "center": [round(float(v), 1) for v in self.center],
            "area_ratio": round(self.area_ratio, 4),
            "aspect": round(self.aspect, 3),
            "in_regions": self.in_regions,
            "region_overlap": {k: round(v, 3) for k, v in self.region_overlap.items()},
            "touch_count": self.touch_count,
            "max_iou": round(self.max_iou, 3),
        }


@dataclass
class SceneFeature:
    """整幅场景的聚合特征。"""
    animal_count: int = 0
    animals: List[AnimalFeature] = field(default_factory=list)
    person_count: int = 0
    image_size: Tuple[int, int] = (0, 0)
    # 空间分布
    mean_area_ratio: float = 0.0
    area_cv: float = 0.0                  # 体型离散度：混合日龄或个别消瘦时升高
    mean_aspect: float = 0.0
    crowding: float = 0.0                 # 平均接触数，反映拥挤度
    # 分区统计
    region_counts: Dict[str, int] = field(default_factory=dict)
    layout_hint: str = ""                 # 栏舍布局推断说明
    regions: List[Region] = field(default_factory=list)

    def to_dict(self):
        return {
            "animal_count": self.animal_count,
            "person_count": self.person_count,
            "image_size": list(self.image_size),
            "mean_area_ratio": round(self.mean_area_ratio, 4),
            "area_cv": round(self.area_cv, 4),
            "mean_aspect": round(self.mean_aspect, 3),
            "crowding": round(self.crowding, 3),
            "region_counts": self.region_counts,
            "layout_hint": self.layout_hint,
            "regions": [r.to_dict() for r in self.regions],
            "animals": [a.to_dict() for a in self.animals],
        }


def infer_regions(image_size: Tuple[int, int], num_animals: int) -> List[Region]:
    """无人工标注时，按常见栏舍布局推断设施区域。

    真实部署时应改为「首次部署时人工框选一次并保存为配置」——
    这在养殖场是完全可接受的工程做法，也省掉训练设施检测器的工作量。
    这里给出的是保守的先验布局，并在 layout_hint 中明确声明为推断值。
    """
    w, h = image_size
    regions = [
        Region("feeder", (0.02 * w, 0.55 * h, 0.35 * w, 0.98 * h), "食槽（推断）"),
        Region("drinker", (0.68 * w, 0.55 * h, 0.98 * w, 0.98 * h), "饮水器（推断）"),
        Region("creep", (0.02 * w, 0.02 * h, 0.30 * w, 0.35 * h), "保温区（推断）"),
    ]
    return regions


def compute_scene(result: DetectionResult, regions: Optional[List[Region]] = None,
                  infer_layout: bool = True) -> SceneFeature:
    """把检测结果转换为场景特征。"""
    w, h = result.image_size
    img_area = float(w * h) if w and h else 1.0

    animals = result.animals
    if regions is None and infer_layout:
        regions = infer_regions(result.image_size, len(animals))

    feats: List[AnimalFeature] = []
    for i, d in enumerate(animals):
        bw, bh = d.size
        aspect = bw / bh if bh > 0 else 0.0
        in_reg, ov = [], {}
        for r in regions or []:
            ratio = r.overlap_ratio(d)
            ov[r.name] = ratio
            # 归属判定用单一准则：中心点落在区域内，或与该区域重叠过半。
            # 最初写成「两者取或后再统计」，导致一个目标被同时计入多个设施区域，
            # 出现「只有 1 头在饮水器却统计出 2 头」的重复计数。
            if r.contains_center(d) or ratio >= 0.5:
                in_reg.append(r.name)

        touch, max_iou, best_j = 0, 0.0, -1
        for j, o in enumerate(animals):
            if i == j:
                continue
            v = d.iou(o)
            if v > max_iou:
                max_iou, best_j = v, j
            if v > 0.05:
                touch += 1

        feats.append(AnimalFeature(
            index=i, box=d.box, center=d.center, area=d.area,
            area_ratio=d.area / img_area, aspect=aspect,
            in_regions=in_reg, region_overlap=ov,
            touch_count=touch, max_iou=max_iou,
            neighbor_index=best_j,
        ))

    area_ratios = [f.area_ratio for f in feats]
    aspects = [f.aspect for f in feats]
    mean_area = sum(area_ratios) / len(area_ratios) if area_ratios else 0.0
    if len(area_ratios) > 1 and mean_area > 0:
        var = sum((a - mean_area) ** 2 for a in area_ratios) / len(area_ratios)
        area_cv = math.sqrt(var) / mean_area
    else:
        area_cv = 0.0

    region_counts = {}
    for f in feats:
        for r in f.in_regions:
            region_counts[r] = region_counts.get(r, 0) + 1

    crowding = (sum(f.touch_count for f in feats) / len(feats)) if feats else 0.0

    hint = ""
    if infer_layout and regions:
        hint = ("设施区域由布局先验推断（食槽左下、饮水器右下、保温区左上），"
                "未经过人工标定。真实部署应改为首次部署时人工框选并保存配置。")

    return SceneFeature(
        animal_count=len(feats), animals=feats,
        person_count=len([d for d in result.detections if d.label == "person"]),
        image_size=result.image_size,
        mean_area_ratio=mean_area,
        area_cv=area_cv,
        mean_aspect=(sum(aspects) / len(aspects)) if aspects else 0.0,
        crowding=crowding,
        region_counts=region_counts,
        layout_hint=hint,
        regions=regions or [],
    )


# ============================================================
# 时序特征（跨帧）
# ============================================================

@dataclass
class TrackFeature:
    """一个目标在时间窗内的运动特征（由相邻帧框匹配得到）。"""
    track_id: int
    frames: int
    displacement: float          # 归一化累计位移（除以图像对角线）
    speed: float                 # 每帧平均位移
    area_change: float           # 面积相对变化（起身/卧倒会变）
    present_frames: int

    def to_dict(self):
        return {
            "track_id": self.track_id, "frames": self.frames,
            "displacement": round(self.displacement, 4),
            "speed": round(self.speed, 4),
            "area_change": round(self.area_change, 3),
        }


def compute_tracks(scenes: List[SceneFeature]) -> List[TrackFeature]:
    """最简跨帧关联：按中心点最近邻贪心匹配，估计位移与速度。

    这是轻量替代方案，不引入深度跟踪模型（ByteTrack/DeepSORT 需要额外权重）。
    对「站立 vs 行走」这种粗粒度运动判断足够。
    """
    if len(scenes) < 2:
        return []

    def diag(sf: SceneFeature) -> float:
        w, h = sf.image_size
        return math.hypot(w, h) or 1.0

    tracks = []
    prev = scenes[0]
    # 逐帧配对（步长 1），保证覆盖整个时间窗。
    # 最初写成按 frame_stride 跳帧配对，导致只统计到前半段，
    # 「末期卧倒」这类后段发生的变化被漏掉（实测踩过这个坑）。
    for i, cur in enumerate(scenes[1:], start=1):
        d = diag(cur)
        used_prev = set()
        for a in cur.animals:
            best, best_dist = None, 1e18
            for j, b in enumerate(prev.animals):
                if j in used_prev:
                    continue
                dist = math.dist(a.center, b.center) / d
                if dist < best_dist:
                    best, best_dist = j, dist
            if best is None:
                continue
            used_prev.add(best)
            b = prev.animals[best]
            prev_area = b.area or 1.0
            tracks.append(TrackFeature(
                track_id=best, frames=i, displacement=best_dist, speed=best_dist,
                area_change=(a.area - b.area) / prev_area,
                present_frames=1,
            ))
        prev = cur

    # 按 track_id 聚合：位移取累计，面积变化取「首帧到末帧」的总变化
    # （而不是各帧差值的平均——平均会把前后抵消，看不出卧倒）
    agg: Dict[int, List[TrackFeature]] = {}
    for t in tracks:
        agg.setdefault(t.track_id, []).append(t)
    out = []
    for tid, ts in agg.items():
        total_area = sum(x.area_change for x in ts)
        out.append(TrackFeature(
            track_id=tid, frames=ts[-1].frames,
            displacement=sum(x.displacement for x in ts),
            speed=sum(x.speed for x in ts) / len(ts),
            area_change=total_area,
            present_frames=len(ts),
        ))
    return out
