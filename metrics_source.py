# -*- coding: utf-8 -*-
"""统一从各结果文件读取指标，供文档生成使用。

为什么要有这个模块：
    文档里的数字原先靠手写，改过抽取算法后忘记同步，导致《作品方案》里
    写成「22 种疾病、259 条症状关联」，而知识库实际是 21 种、211 条。
    评测时被逐项核对发现。改为运行时读取，从根上避免这类漂移。
"""
import io
import json
import os

AIC = r"E:\harness\aic"
VISION = os.path.join(AIC, "vision")
PIGDX = os.path.join(AIC, "pigdisease")


def _load(path):
    if not os.path.isfile(path):
        return None
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def kb_stats():
    """知识库规模：文献数、疾病数、症状关联数（逐病统计，不用 meta 缓存值）。"""
    d = _load(os.path.join(PIGDX, "data", "diseases.json"))
    if not d:
        return {"docs": 0, "diseases": 0, "symptoms": 0}
    docs = 0
    built = (d.get("meta") or {}).get("built_from", "")
    # built_from 形如「41 篇中文文献（CNKI 检索，…）」
    import re
    m = re.search(r"(\d+)\s*篇", built)
    if m:
        docs = int(m.group(1))
    return {
        "docs": docs,
        # 逐病统计，避免 meta.disease_count 与内容不一致
        "diseases": len(d.get("diseases", [])),
        "symptoms": sum(len(x.get("symptoms", {})) for x in d.get("diseases", [])),
    }


def dx_eval():
    """疾病诊断评测：Top-1 / Top-3 / MRR / 安全测试 / 分层。"""
    d = _load(os.path.join(PIGDX, "results", "eval_results.json"))
    if not d:
        return {}
    m = d.get("metrics", {})
    s = d.get("safety_metrics", {})
    st = m.get("stratified") or {}
    out = {
        "n_cases": m.get("n_cases"),
        "top1": m.get("top1_accuracy"),
        "top3": m.get("top3_accuracy"),
        "mrr": m.get("mrr"),
        "safety_passed": s.get("passed"),
        "safety_n": s.get("n"),
    }
    for k, v in st.items():
        # 键名形如 kb_supported(强中证据>=3)
        if k.startswith("kb_supported"):
            out["strong_n"] = v.get("n")
            out["strong_top3"] = v.get("top3")
        elif k.startswith("kb_weak"):
            out["weak_n"] = v.get("n")
            out["weak_top3"] = v.get("top3")
    return out


def region_calibration():
    """设施标定的效果对比（真实猪舍图片）。"""
    d = _load(os.path.join(VISION, "results", "region_calibration_effect.json"))
    if not d:
        return {}
    return {"n_images": d.get("n_images"), "n_targets": d.get("n_targets"),
            "inferred": d.get("inferred_pct") or {},
            "calibrated": d.get("calibrated_pct") or {}}


def detection():
    """检测器最终指标（取训练日志最后一行）。"""
    import csv
    p = os.path.join(VISION, "runs", "pig_yolov8n", "results.csv")
    if not os.path.isfile(p):
        return {}
    rows = list(csv.DictReader(io.open(p, encoding="utf-8")))
    if not rows:
        return {}
    k = {kk.strip(): vv for kk, vv in rows[-1].items()}

    def f(name):
        try:
            return float(k.get(name, 0))
        except (TypeError, ValueError):
            return 0.0
    return {"epoch": int(float(k.get("epoch", 0))),
            "map50": f("metrics/mAP50(B)"),
            "map5095": f("metrics/mAP50-95(B)"),
            "precision": f("metrics/precision(B)"),
            "recall": f("metrics/recall(B)")}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print("知识库:", kb_stats())
    print("诊断评测:", dx_eval())
    print("标定效果:", region_calibration())
    print("检测指标:", detection())
