# -*- coding: utf-8 -*-
"""健康与福利评估层。

设计原则（吸取之前方案书的教训）：
    1. 不使用没有文献依据的固定阈值。默认基线明确标注为「待标定」。
    2. 首选「个体自身历史基线对比」，而不是全场统一阈值——
       不同日龄、不同栏舍的正常行为分布差异很大，统一阈值会产生大量误报。
    3. 只有采食/饮水时长下降 且 异常行为上升 这类「多指标联合」偏离才触发预警，
       避免单指标抖动造成的误报。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from behavior import BEHAVIOR_CN, BehaviorResult

# 默认参考分布：明确标注为待标定，不作为临床依据
DEFAULT_BASELINE = {
    "eating": 10.0, "drinking": 4.0, "resting": 65.0,
    "standing": 8.0, "walking": 12.0, "aggressive": 1.0,
}
BASELINE_NOTE = ("默认行为分布为示例基线，未经现场标定，不可作为临床判断依据。"
                 "部署后应采集本栏至少 3-7 天的数据建立自身基线。")

# 预警阈值（偏离比例）
TEV = {
    "intake_drop": 0.40,      # 采食+饮水占比相对基线下降 40%
    "abnormal_rise": 0.50,    # 异常行为（争斗）相对基线上升 50%
    "activity_drop": 0.45,    # 活动（行走+站立）占比下降 45%
    "rest_rise": 0.35,        # 休息占比上升 35%
}

LEVEL_CN = {"normal": "正常", "watch": "需关注", "alert": "异常预警", "insufficient": "数据不足"}


@dataclass
class HealthResult:
    level: str = "insufficient"
    score: float = 0.0                     # 0-100，越高越正常
    signals: List[dict] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    baseline_used: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    @property
    def level_cn(self) -> str:
        return LEVEL_CN.get(self.level, self.level)

    def to_dict(self):
        return {
            "level": self.level, "level_cn": self.level_cn,
            "score": round(self.score, 1),
            "signals": [{k: (round(v, 2) if isinstance(v, float) else v)
                         for k, v in s.items()} for s in self.signals],
            "suggestions": self.suggestions,
            "baseline_used": self.baseline_used,
            "notes": self.notes,
        }


def assess(behavior: BehaviorResult,
           baseline: Optional[Dict[str, float]] = None,
           min_frames: int = 1) -> HealthResult:
    """基于行为分布做健康/福利评估。"""
    baseline = baseline or DEFAULT_BASELINE
    notes = [BASELINE_NOTE]
    res = HealthResult(baseline_used=dict(baseline))

    total = sum(behavior.distribution.values())
    if total == 0:
        res.level = "insufficient"
        res.notes.append("没有行为识别结果，无法评估。")
        res.level = "insufficient"
        return res

    if not behavior.temporal_available:
        res.notes.append(
            "本次为单帧分析，行为分布不具统计意义，评估结果仅供参考。"
            "健康评估需要基于连续视频累计的行为时间占比。"
        )
        res.level = "insufficient"
        res.score = 0.0
        return res

    obs = dict(behavior.distribution_pct)

    def rel(key_a: str, key_b: str, base_key: str = None) -> float:
        got = obs.get(key_a, 0.0) + (obs.get(key_b, 0.0) if key_b else 0.0)
        base = baseline.get(base_key or key_a, 0.0)
        return (got - base) / base if base > 0 else 0.0

    # 信号 1：采食+饮水下降
    intake_delta = rel("eating", "drinking")
    res.signals.append({
        "name": "采食饮水占比", "observed": obs.get("eating", 0) + obs.get("drinking", 0),
        "baseline": baseline.get("eating", 0) + baseline.get("drinking", 0),
        "delta_pct": intake_delta * 100})
    if intake_delta <= -TEV["intake_drop"]:
        res.suggestions.append(
            f"采食与饮水合计占比比基线低 {abs(intake_delta)*100:.0f}%，"
            "建议检查饲料适口性、饮水器出水量与猪群精神状态。")

    # 信号 2：异常行为上升
    abn_delta = rel("aggressive", None)
    res.signals.append({
        "name": "争斗行为占比", "observed": obs.get("aggressive", 0),
        "baseline": baseline.get("aggressive", 0), "delta_pct": abn_delta * 100})
    if abn_delta >= TEV["abnormal_rise"]:
        res.suggestions.append(
            f"争斗行为占比比基线高 {abn_delta*100:.0f}%，"
            "建议核查饲养密度、混群情况、料位与水位是否充足，并排查环境应激。")

    # 信号 3：活动量下降
    act_delta = rel("walking", "standing")
    res.signals.append({
        "name": "活动占比", "observed": obs.get("walking", 0) + obs.get("standing", 0),
        "baseline": baseline.get("walking", 0) + baseline.get("standing", 0),
        "delta_pct": act_delta * 100})
    if act_delta <= -TEV["activity_drop"]:
        res.suggestions.append(
            f"活动占比比基线低 {abs(act_delta)*100:.0f}%，"
            "建议检查舍温、通风与躺卧区舒适度，排除热应激或呼吸道问题。")

    # 信号 4：休息占比上升
    rest_delta = rel("resting", None)
    res.signals.append({
        "name": "休息占比", "observed": obs.get("resting", 0),
        "baseline": baseline.get("resting", 0), "delta_pct": rest_delta * 100})

    # 多指标联合判级
    alerts = 0
    if intake_delta <= -TEV["intake_drop"]:
        alerts += 1
    if abn_delta >= TEV["abnormal_rise"]:
        alerts += 1
    if act_delta <= -TEV["activity_drop"]:
        alerts += 1
    if rest_delta >= TEV["rest_rise"]:
        alerts += 1

    if alerts >= 2:
        res.level = "alert"
    elif alerts == 1:
        res.level = "watch"
    else:
        res.level = "normal"

    # 打分：100 分减去各信号偏离量（截断到 0-100）
    penalty = 0.0
    for s in res.signals:
        d = abs(s["delta_pct"])
        penalty += min(30.0, d * 0.6)
    res.score = max(0.0, min(100.0, 100.0 - penalty))

    if res.level == "normal":
        res.suggestions.append("各项行为指标在合理范围内，保持现有管理方式并继续观察。")
    res.notes.append(
        "本评估为行为层面的偏离提示，不是疾病诊断。异常时应结合采食量、体温、"
        "粪便性状等生产记录，并由执业兽医现场检查。")
    return res


def humanize_signals(health: HealthResult) -> List[str]:
    """把信号转成中文可读句子。"""
    out = []
    for s in health.signals:
        d = s["delta_pct"]
        arrow = "↑" if d > 0 else ("↓" if d < 0 else "→")
        out.append(f"  · {s['name']}：观测 {s['observed']:.1f}% / 基线 {s['baseline']:.1f}%"
                   f"　偏离 {arrow}{abs(d):.0f}%")
    return out
