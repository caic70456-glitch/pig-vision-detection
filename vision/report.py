# -*- coding: utf-8 -*-
"""多模态报告层：把视觉分析结果转成自然语言描述与结构化报告。

「多模态」在本项目中的含义：视觉输入 → 结构化场景理解 → 语言输出。
提供两级实现：
    L1 模板叙述（默认，完全离线）：把结构化特征按养殖报告的话术组织成文字
    L2 大模型增强（可选）：把结构化结果交给 LLM，生成更自然、更贴合上下文的叙述，
                          并可由 LLM 结合知识库给出排查建议

安全约束：L2 只允许基于结构化结果做语言组织，不允许 LLM 自行发明检测结论或用药建议。
"""
import json
import os
import urllib.error
import urllib.request
from typing import List, Optional

from behavior import BEHAVIOR_CN, BehaviorResult
from health import HealthResult, humanize_signals
from scene import SceneFeature


def template_narrative(scene: SceneFeature, behavior: BehaviorResult,
                       health: HealthResult, result_meta: dict = None) -> str:
    """L1：模板化自然语言叙述。"""
    lines = []
    n = scene.animal_count

    if n == 0:
        lines.append("本画面未检出目标个体。可能是拍摄角度、距离或光照不适宜，"
                     "也可能栏舍为空。建议确认镜头视野后重拍。")
        return "\n".join(lines)

    # 总量与分布
    lines.append(f"本画面共呈现 {n} 个目标个体"
                 + (f"，同时检出 {scene.person_count} 名人员。" if scene.person_count else "。"))

    order = sorted(behavior.distribution_pct.items(), key=lambda x: -x[1])
    dist_txt = "、".join(f"{BEHAVIOR_CN.get(k, k)} {v:.0f}%"
                        for k, v in order if v > 0)
    if dist_txt:
        lines.append(f"行为构成：{dist_txt}。")

    # 设施使用
    rmap = {"feeder": "食槽", "drinker": "饮水器", "creep": "保温区"}
    used = [(rmap.get(k, k), v) for k, v in scene.region_counts.items() if v > 0]
    if used:
        lines.append("设施区占用：" + "、".join(f"{k} {v} 个" for k, v in used) + "。")
    else:
        lines.append("设施区内未见个体停留。")

    # 空间与体型
    if scene.animal_count > 1:
        crowd = scene.crowding
        if crowd >= 1.5:
            lines.append(f"个体间接触较频繁（平均每头与 {crowd:.1f} 个其他个体框重叠），"
                         "画面偏拥挤，建议核查饲养密度与料位水位。")
        elif crowd <= 0.3:
            lines.append("个体分布较分散，相互接触少。")
    if scene.area_cv >= 0.45 and scene.animal_count >= 3:
        lines.append(f"个体占画面面积离散度较高（变异系数 {scene.area_cv:.2f}），"
                     "提示画面内个体大小差异明显，可能存在日龄差异、站位远近差别，"
                     "或个别个体消瘦，建议结合现场确认。")

    # 异常
    if behavior.conflict_pairs:
        pairs = "、".join(f"#{i+1}–#{j+1}" for i, j in behavior.conflict_pairs[:5])
        lines.append(f"检出 {len(behavior.conflict_pairs)} 组个体存在明显框重叠：{pairs}，"
                     "可能为争斗，也可能为并排休息，需结合连续帧确认。")

    # 健康
    lines.append("")
    lines.append(f"健康/福利评估：{health.level_cn}（评分 {health.score:.0f}/100）。")
    if health.signals:
        lines.extend(humanize_signals(health))

    if health.suggestions:
        lines.append("")
        lines.append("建议：")
        for s in health.suggestions:
            lines.append(f"  · {s}")

    # 检测可信度声明
    if result_meta:
        if result_meta.get("approximate"):
            lines.append("")
            lines.append("【识别可信度提示】" + result_meta.get("approx_note", ""))
    return "\n".join(lines)


def llm_narrative(scene: SceneFeature, behavior: BehaviorResult, health: HealthResult,
                  result_meta: dict = None, model: str = None) -> tuple:
    """L2：调用大模型把结构化结果组织成更自然的叙述。

    严格约束：只传结构化结果，要求模型不得新增检测结论；
    返回 (text, error)。
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = model or os.environ.get("PIGVISION_LLM_MODEL", "gpt-4o-mini")
    if not api_key:
        return None, "未配置 OPENAI_API_KEY"

    payload = {
        "scene": scene.to_dict(),
        "behavior": behavior.to_dict(),
        "health": health.to_dict(),
        "detector": (result_meta or {}).get("backend"),
        "approximate_detection": (result_meta or {}).get("approximate"),
    }
    prompt = (
        "你是规模化猪场的智能巡检助手。下面是对一张（或一段）栏舍监控画面做视觉分析后"
        "得到的结构化结果。请把它写成一段给场长看的中文巡检简报，要求：\n"
        "1. 只用给定数据，不得新增任何未出现在数据中的检测结论或数字；\n"
        "2. 明确区分「观察到的事实」与「推测」，推测必须写明依据；\n"
        "3. 若 approximate_detection 为 true，必须提醒检测器不识别猪只类别，结果仅供流程演示；\n"
        "4. 不得给出任何用药建议；提到疾病时只能建议现场检查；\n"
        "5. 最后给出不超过 3 条可执行建议。\n\n"
        f"结构化结果：\n{json.dumps(payload, ensure_ascii=False)}"
    )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"], None
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as e:
        return None, f"LLM 调用失败: {e}"


def build_report(scene: SceneFeature, behavior: BehaviorResult, health: HealthResult,
                 result_meta: dict = None, use_llm: bool = None) -> dict:
    """组装完整报告。"""
    if use_llm is None:
        use_llm = os.environ.get("PIGVISION_LLM") == "1"

    narrative = template_narrative(scene, behavior, health, result_meta)
    llm_text, llm_err = (None, None)
    if use_llm:
        llm_text, llm_err = llm_narrative(scene, behavior, health, result_meta)

    return {
        "scene": scene.to_dict(),
        "behavior": behavior.to_dict(),
        "health": health.to_dict(),
        "detector": result_meta or {},
        "narrative": llm_text or narrative,
        "narrative_source": "llm" if llm_text else "template",
        "template_narrative": narrative,
        "llm_error": llm_err,
        "disclaimer": ("本报告由视觉分析自动生成，仅反映画面中的行为分布，"
                       "不构成疾病诊断或用药依据。异常情况请由执业兽医现场检查。"),
    }
