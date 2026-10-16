# -*- coding: utf-8 -*-
"""端到端流水线：图像/视频 → 检测 → 场景特征 → 行为识别 → 健康评估 → 多模态报告。

这是整个视觉系统的入口，把各层串起来。
"""
import os
from typing import Dict, List, Optional

from behavior import classify_scene, BehaviorResult
from detector import Detection, DetectionResult, build_backend, MockBackend
from health import assess, HealthResult
from report import build_report
from scene import compute_scene, compute_tracks, SceneFeature


def _approx_note(result: DetectionResult) -> str:
    if not result.approximate:
        return ""
    return ("当前检测器不认识「猪」这一类别（COCO 无 pig 类），输出的是近邻动物粗类别，"
            "可能把猪计为 cow/sheep/horse 或漏检；本结果仅用于验证流程，"
            "真实识别需提供猪只检测模型（ONNX）。")


def _resolve_regions(regions, image_path=None, image_size=None):
    """解析设施区域来源，优先级：
        1) 显式传入的 Region 列表
        2) 显式传入的配置字典 -> 转成 Region
        3) 从图像路径自动查找同名/上级目录的 regions.json
        4) 都不满足 -> None（由 scene 层用布局先验推断，并标注为「推断」）
    """
    if regions is not None:
        if isinstance(regions, dict):
            import regions as R
            return R.to_pixel_regions(regions, image_size)
        return regions

    if image_path:
        try:
            import regions as R
            p = R.find_config_for(image_path)
            if p:
                cfg = R.load_config(p)
                if cfg and image_size:
                    return R.to_pixel_regions(cfg, image_size)
        except Exception:
            pass
    return None


def analyze_detections(dets: List[Detection], image_size, backend_name="custom",
                       approximate=False, regions=None,
                       baseline=None, use_llm=None) -> dict:
    """对一组检测结果做完整分析（供 CLI、Web、评测脚本共用）。"""
    result = DetectionResult(detections=list(dets), backend=backend_name,
                             approximate=approximate, image_size=tuple(image_size),
                             warnings=[])
    region_objs = _resolve_regions(regions, image_size=image_size)
    scene = compute_scene(result, regions=region_objs)
    behavior = classify_scene(scene, tracks=[], track_scenes=1)
    health = assess(behavior, baseline=baseline)
    meta = {
        "backend": backend_name,
        "can_detect_pig": not approximate,
        "approximate": approximate,
        "approx_note": _approx_note(result),
        "regions_calibrated": bool(region_objs),
    }
    return build_report(scene, behavior, health, result_meta=meta, use_llm=use_llm)


def analyze_image(path: str, backend=None, regions=None, baseline=None,
                  use_llm=None, min_score: float = 0.25) -> dict:
    """分析单张图像。regions 可为 Region 列表、配置字典，或 None（自动查找 regions.json）。"""
    from PIL import Image

    if backend is None:
        backend = build_backend(min_score=min_score)
    img = Image.open(path)
    result = backend.detect(img)
    region_objs = _resolve_regions(regions, image_path=path, image_size=(img.width, img.height))
    scene = compute_scene(result, regions=region_objs)
    behavior = classify_scene(scene, tracks=[], track_scenes=1)
    health = assess(behavior, baseline=baseline)
    meta = {
        "backend": result.backend,
        "can_detect_pig": getattr(backend, "can_detect_pig", False),
        "approximate": result.approximate,
        "approx_note": _approx_note(result),
        "image": os.path.basename(path),
        "regions_calibrated": bool(region_objs),
        "warnings": result.warnings,
    }
    rep = build_report(scene, behavior, health, result_meta=meta, use_llm=use_llm)
    rep["pipeline_warnings"] = result.warnings
    return rep


def analyze_frames(paths: List[str], backend=None, regions=None, baseline=None,
                   use_llm=None, frame_stride: int = 1, max_frames: int = 120) -> dict:
    """分析连续帧（视频抽帧后的图片序列），启用时序行为判定。"""
    from PIL import Image

    if backend is None:
        backend = build_backend()

    scenes: List[SceneFeature] = []
    used, metas = [], None
    region_objs, first_size = None, None
    for i, p in enumerate(paths[:max_frames]):
        if i % frame_stride:
            continue
        img = Image.open(p)
        if first_size is None:
            first_size = (img.width, img.height)
            # 区域只需解析一次；后续帧尺寸不同也能用（归一化坐标）
            region_objs = _resolve_regions(regions, image_path=p, image_size=first_size)
        r = backend.detect(img)
        if metas is None:
            metas = {"backend": r.backend, "approximate": r.approximate,
                     "can_detect_pig": getattr(backend, "can_detect_pig", False),
                     "regions_calibrated": bool(region_objs),
                     "approx_note": _approx_note(r), "warnings": r.warnings}
        scenes.append(compute_scene(r, regions=region_objs, infer_layout=(i == 0)))
        used.append(os.path.basename(p))

    if not scenes:
        return {"error": "没有可用帧"}

    # 统一图像尺寸字段（各帧可能不同）
    tracks = compute_tracks(scenes)

    # 汇总行为：以帧平均分布为准（统计行为时间占比）
    from behavior import classify_scene as _cs
    all_verdict_counts: Dict[str, int] = {}
    total_v = 0
    for sf in scenes:
        br = _cs(sf, tracks=tracks, track_scenes=len(scenes))
        for k, v in br.distribution.items():
            all_verdict_counts[k] = all_verdict_counts.get(k, 0) + v
        total_v += sum(br.distribution.values())

    agg_pct = ({k: v * 100.0 / total_v for k, v in all_verdict_counts.items()}
               if total_v else {})
    last_scene = scenes[-1]
    behavior = _cs(last_scene, tracks=tracks, track_scenes=len(scenes))
    behavior.distribution = all_verdict_counts
    behavior.distribution_pct = agg_pct

    health = assess(behavior, baseline=baseline)
    meta = dict(metas or {})
    meta.update({"frames_analyzed": len(scenes), "frame_files": used[:10]})
    rep = build_report(last_scene, behavior, health, result_meta=meta, use_llm=use_llm)
    rep["tracks"] = [t.to_dict() for t in tracks]
    rep["frames_analyzed"] = len(scenes)
    rep["pipeline_warnings"] = (metas or {}).get("warnings", [])
    return rep
