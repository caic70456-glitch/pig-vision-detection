# -*- coding: utf-8 -*-
"""行为识别层：用显式规则把「几何/时间特征」映射为猪的行为。

为什么用规则而不是分类器：
    1. 没有带行为标注的数据集，无法训练时序行为分类器。
    2. 行为判断需要可解释——养殖场要能看懂「为什么判定为争斗」。
    3. 规则可以写清动物行为学依据，便于领域专家审核与修正。

六类行为定义（与动物行为学常用划分对齐）：
    采食 eating / 饮水 drinking / 休息 resting / 站立 standing / 行走 walking / 争斗 aggressive

规则依据：
    - 采食、饮水：由「身体与食槽/饮水器区域的重叠比例」判定（空间关系）
    - 行走、站立、休息：由「跨帧位移」+「框的宽高比变化」判定（时间关系）
    - 争斗：由「两两框高 IoU + 双方均有位移」判定（时空联合）

置信度来源：每个判定都给出触发的规则、用到的特征值与阈值，
不输出无依据的分数。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from scene import AnimalFeature, SceneFeature, TrackFeature

# ---------------- 规则阈值（集中配置，便于按现场调整） ----------------
TH = {
    # 与设施区域的重叠比例阈值
    "region_overlap_eat": 0.35,      # 与食槽重叠 >= 此值 -> 采食
    "region_overlap_drink": 0.35,    # 与饮水器重叠 >= 此值 -> 饮水
    # 运动
    "walk_speed": 0.012,             # 每帧归一化位移 >= 此值 -> 行走
    "walk_displacement": 0.05,       # 时间窗累计位移 >= 此值 -> 行走
    # 姿态（宽高比变化用于辅助判断起身/卧倒）
    "rest_area_change": -0.15,       # 面积显著减小 -> 可能卧倒
    "standing_max_speed": 0.006,     # 几乎不动 -> 站立或休息
    # 争斗：双阈值设计
    #   静态图（无时序）：只能靠重叠度，必须保守（0.35），否则密集采食时
    #       相邻框的正常重叠会被大量误判为争斗（实测误报率达 35%）。
    #   视频（有时序）：可以额外验证「双方是否都在移动」，
    #       因此重叠阈值放宽（0.15），此时捕获真实争斗的能力更强。
    #   两者的 IoU 分布本身重叠（真实争斗 ~0.17，密集采食 ~0.15-0.32），
    #   单一阈值无法分开，所以必须按可用证据分级。
    "fight_iou_static": 0.35,
    "fight_iou_temporal": 0.15,
    "fight_min_speed": 0.004,
}

BEHAVIOR_CN = {
    "eating": "采食", "drinking": "饮水", "resting": "休息",
    "standing": "站立", "walking": "行走", "aggressive": "争斗",
    "unknown": "无法判定",
}


@dataclass
class BehaviorVerdict:
    """单个动物的行为判定结果，含全部判定依据。"""
    index: int
    behavior: str
    confidence: float
    rules_fired: List[str] = field(default_factory=list)
    features_used: Dict[str, float] = field(default_factory=dict)
    note: str = ""

    @property
    def behavior_cn(self) -> str:
        return BEHAVIOR_CN.get(self.behavior, self.behavior)

    def to_dict(self):
        return {
            "index": self.index, "behavior": self.behavior,
            "behavior_cn": self.behavior_cn,
            "confidence": round(self.confidence, 3),
            "rules_fired": self.rules_fired,
            "features_used": {k: round(float(v), 4) for k, v in self.features_used.items()},
            "note": self.note,
        }


@dataclass
class BehaviorResult:
    verdicts: List[BehaviorVerdict] = field(default_factory=list)
    distribution: Dict[str, int] = field(default_factory=dict)
    distribution_pct: Dict[str, float] = field(default_factory=dict)
    conflict_pairs: List[Tuple[int, int]] = field(default_factory=list)
    temporal_available: bool = False
    warnings: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "verdicts": [v.to_dict() for v in self.verdicts],
            "distribution": self.distribution,
            "distribution_pct": {k: round(v, 1) for k, v in self.distribution_pct.items()},
            "conflict_pairs": [list(p) for p in self.conflict_pairs],
            "temporal_available": self.temporal_available,
            "warnings": self.warnings,
        }


def _track_for(tracks: List[TrackFeature], idx: int) -> Optional[TrackFeature]:
    for t in tracks:
        if t.track_id == idx:
            return t
    return None


def classify_one(a: AnimalFeature, tracks: List[TrackFeature],
                 has_temporal: bool) -> BehaviorVerdict:
    """对单个目标做行为判定。

    优先级设计（重要，经过实测修正）：
        1. 采食 / 饮水 —— 设施绑定行为，有明确空间锚点，最可靠
        2. 争斗 —— 需要「框重叠 + 位移」的时空联合证据
        3. 行走 —— 需要跨帧位移
        4. 休息 / 站立 —— 静止状态的细分

    最初把「争斗」排在「采食」之前，导致「4 头同槽采食」因框相邻重叠而被
    全部误判为争斗。设施绑定行为应优先于基于框重叠的推断。
    """
    rules, feats = [], {}
    ov = a.region_overlap or {}
    eat_ov = ov.get("feeder", 0.0)
    drink_ov = ov.get("drinker", 0.0)
    feats["feeder_overlap"] = eat_ov
    feats["drinker_overlap"] = drink_ov

    t = _track_for(tracks, a.index)
    speed = t.speed if t else 0.0
    disp = t.displacement if t else 0.0
    area_chg = t.area_change if t else 0.0
    feats["speed"] = speed
    feats["displacement"] = disp
    feats["area_change"] = area_chg
    feats["aspect"] = a.aspect
    feats["touch_count"] = a.touch_count
    feats["max_iou"] = a.max_iou

    # ---- 规则 1：采食（设施锚定，优先级最高）----
    if eat_ov >= TH["region_overlap_eat"]:
        rules.append(f"R-eat: 与食槽区域重叠 {eat_ov:.2f} >= {TH['region_overlap_eat']}"
                     "（设施锚定判据）")
        conf = min(1.0, 0.55 + eat_ov * 0.45)
        if a.max_iou >= TH["fight_iou_static"]:
            rules.append(f"提示：与相邻个体框重叠 IoU={a.max_iou:.3f}，"
                         "在高密度采食时属正常现象，不据此判定争斗")
        return BehaviorVerdict(a.index, "eating", conf, rules, feats)

    # ---- 规则 2：饮水 ----
    if drink_ov >= TH["region_overlap_drink"]:
        rules.append(f"R-drink: 与饮水器区域重叠 {drink_ov:.2f} >= {TH['region_overlap_drink']}"
                     "（设施锚定判据）")
        return BehaviorVerdict(a.index, "drinking", min(1.0, 0.55 + drink_ov * 0.45), rules, feats)

    # ---- 规则 3：争斗（双阈值，按可用证据分级）----
    if has_temporal:
        # 视频：可验证双方是否都在动，用宽松重叠阈值 + 运动证据
        partner = a.neighbor_speed if hasattr(a, "neighbor_speed") else 0.0
        both_move = (speed >= TH["fight_min_speed"] and partner >= TH["fight_min_speed"])
        if a.max_iou >= TH["fight_iou_temporal"] and both_move:
            rules.append(f"R-fight: 与相邻个体 IoU={a.max_iou:.3f} >= "
                         f"{TH['fight_iou_temporal']}（时序阈值），"
                         f"且双方均有位移（自身 {speed:.4f}、对方 {partner:.4f}）")
            return BehaviorVerdict(a.index, "aggressive",
                                   min(1.0, 0.5 + a.max_iou * 1.5), rules, feats)
    elif a.max_iou >= TH["fight_iou_static"]:
        # 静态图：仅重叠度可用，必须用保守阈值
        rules.append(f"R-fight: 与相邻个体 IoU={a.max_iou:.3f} >= "
                     f"{TH['fight_iou_static']}（静态阈值）")
        return BehaviorVerdict(a.index, "aggressive",
                               min(1.0, (0.5 + a.max_iou) * 0.6), rules, feats,
                              "单帧静态判据，已用保守阈值降低误报；"
                              "确认请结合视频（视频下会自动启用运动验证）")

    # ---- 规则 4：姿态变化（卧倒）——面积显著变化优先于运动判据 ----
    # 猪从站立到卧倒时，检测框面积会明显缩小；这是姿态证据，比位移更能说明状态。
    # 规则顺序上必须先判姿态：否则「刚卧下、位移很小」会被误判为站立（实测踩过）。
    if has_temporal and area_chg <= TH["rest_area_change"]:
        rules.append(f"R-rest: 框面积相对变化 {area_chg:.2f} <= {TH['rest_area_change']}，"
                     "判断为姿态由站转卧")
        return BehaviorVerdict(a.index, "resting", 0.72, rules, feats)

    # ---- 规则 5：行走（需要时序）----
    if has_temporal and (speed >= TH["walk_speed"] or disp >= TH["walk_displacement"]):
        rules.append(f"R-walk: speed={speed:.4f} >= {TH['walk_speed']} "
                     f"或 displacement={disp:.4f} >= {TH['walk_displacement']}")
        return BehaviorVerdict(a.index, "walking", min(1.0, 0.5 + speed * 12), rules, feats)

    # ---- 规则 6：休息 / 站立 ----
    if not has_temporal:
        rules.append("R-pose: 无时序信息，仅能依据静止与重叠关系粗判")
        # 无时序时，面积占比大且宽高比偏扁，倾向判休息
        if a.aspect >= 1.5:
            rules.append(f"R-rest: 宽高比 {a.aspect:.2f} >= 1.5，形态偏卧姿")
            return BehaviorVerdict(a.index, "resting", 0.45, rules, feats,
                                  "缺少跨帧信息，站/卧判定不可靠")
        return BehaviorVerdict(a.index, "standing", 0.4, rules, feats,
                              "缺少跨帧信息，站/走判定不可靠")

    if speed < TH["standing_max_speed"] and disp < TH["walk_displacement"]:
        rules.append(f"R-stand: 位移极小（speed={speed:.4f} < {TH['standing_max_speed']}），"
                     f"面积变化 {area_chg:+.2f} 未达卧倒阈值 {TH['rest_area_change']}")
        return BehaviorVerdict(a.index, "standing", 0.65, rules, feats)

    return BehaviorVerdict(a.index, "unknown", 0.3, rules, feats, "未命中任何规则")


def classify_scene(scene: SceneFeature, tracks: Optional[List[TrackFeature]] = None,
                   track_scenes: int = 0) -> BehaviorResult:
    """对整幅场景做行为识别。"""
    tracks = tracks or []
    has_temporal = track_scenes >= 2 and bool(tracks)

    # 回填「重叠最多的邻居的速度」：时序判据里「双方都在动」是争斗的必要证据。
    # 放在这里做是因为速度来自 tracks，而 AnimalFeature 在 scene 层构造时还拿不到 tracks。
    for a in scene.animals:
        a.neighbor_speed = 0.0
        if has_temporal and a.neighbor_index is not None and a.neighbor_index >= 0:
            t = _track_for(tracks, a.neighbor_index)
            if t is not None:
                a.neighbor_speed = t.speed

    verdicts = [classify_one(a, tracks, has_temporal) for a in scene.animals]

    dist: Dict[str, int] = {}
    for v in verdicts:
        dist[v.behavior] = dist.get(v.behavior, 0) + 1
    total = len(verdicts) or 1
    pct = {k: v * 100.0 / total for k, v in dist.items()}

    # 冲突对：IoU 较高的个体对（阈值与判定用的静态阈值一致）
    pairs = []
    for i, a in enumerate(scene.animals):
        for j, b in enumerate(scene.animals):
            if j <= i:
                continue
            from detector import Detection
            da = Detection(a.box, "animal", 1.0)
            db = Detection(b.box, "animal", 1.0)
            if da.iou(db) >= TH["fight_iou_static"]:
                pairs.append((i, j))

    warns = []
    if not has_temporal:
        warns.append(
            "本次为单帧分析：无法区分「站立」与「行走」，也无法可靠区分「争斗」与「并排休息」。"
            "要获得完整行为识别，请分析连续多帧或视频。"
        )
    if scene.animal_count == 0:
        warns.append("未检测到任何目标，无法进行行为识别。")

    return BehaviorResult(
        verdicts=verdicts, distribution=dist, distribution_pct=pct,
        conflict_pairs=pairs, temporal_available=has_temporal, warnings=warns,
    )
