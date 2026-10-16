# -*- coding: utf-8 -*-
"""行为推理正确性评测：在合成场景上对比「流水线判定」与「已知标准答案」。

作用：在没有真实标注数据的情况下，验证行为规则层的工程正确性。
      （合成图像只验证流程，不代表真实识别精度。）

指标：逐目标行为准确率、宏平均 F1、各行为类别的混淆情况。
"""
import io
import json
import os
import sys
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import detector  # noqa: E402
import pipeline  # noqa: E402
from behavior import BEHAVIOR_CN  # noqa: E402


def main():
    meta_p = os.path.join(BASE, "synthetic", "scenes.json")
    if not os.path.isfile(meta_p):
        print("未找到合成场景，请先运行： python make_scenes.py")
        return
    with io.open(meta_p, encoding="utf-8") as fh:
        data = json.load(fh)

    n_total = n_correct = 0
    per_class = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    rows = []

    print(f"{'场景':<20}{'目标':>5}{'正确':>5}{'准确率':>8}   逐目标对比")
    print("-" * 92)

    for s in data["scenes"]:
        dets = [detector.Detection(tuple(d["box"]), d["label"], d["score"])
                for d in s["detections"]]
        rep = pipeline.analyze_detections(
            dets, data["image_size"], backend_name="synthetic", approximate=True)
        verdicts = rep["behavior"]["verdicts"]
        expected = {int(k): v for k, v in s["expected"].items()}

        # 只比较 label=animal 的目标（person 不参与行为评测）
        animal_idx = [i for i, d in enumerate(s["detections"]) if d["label"] == "animal"]
        details, correct = [], 0
        for k, vi in enumerate(verdicts):
            idx = animal_idx[k] if k < len(animal_idx) else None
            if idx is None or idx not in expected:
                continue
            exp = expected[idx]
            got = vi["behavior"]
            ok = exp == got
            n_total += 1
            correct += ok
            n_correct += ok
            # 混淆统计
            if ok:
                per_class[exp]["tp"] += 1
            else:
                per_class[exp]["fn"] += 1
                per_class[got]["fp"] += 1
            details.append(f"#{idx+1}:{BEHAVIOR_CN.get(exp,exp)}"
                           f"{'✓' if ok else '→' + BEHAVIOR_CN.get(got,got)}")
        acc = correct / len(details) if details else 0.0
        print(f"{s['name']:<20}{len(details):>5}{correct:>5}{acc:>7.0%}   {' '.join(details)}")
        rows.append({"scene": s["name"], "targets": len(details),
                     "correct": correct, "accuracy": round(acc, 4), "details": details})

    print("-" * 92)
    overall = n_correct / n_total if n_total else 0.0
    print(f"总体：{n_correct}/{n_total} = {overall:.1%}")

    # 宏平均 F1
    f1s, lines = [], []
    labels = sorted(set(list(per_class.keys())))
    for c in labels:
        tp, fp, fn = per_class[c]["tp"], per_class[c]["fp"], per_class[c]["fn"]
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        if tp + fp + fn:
            f1s.append(f1)
        lines.append(f"  {BEHAVIOR_CN.get(c,c):<6} P={p:.2f} R={r:.2f} F1={f1:.2f}  (tp{tp} fp{fp} fn{fn})")
    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0
    print(f"宏平均 F1：{macro_f1:.3f}")
    for ln in lines:
        print(ln)

    out = {
        "dataset": "synthetic（合成场景，仅验证流程正确性）",
        "n_targets": n_total, "n_correct": n_correct,
        "accuracy": round(overall, 4), "macro_f1": round(macro_f1, 4),
        "per_class": {c: dict(per_class[c]) for c in labels},
        "scenes": rows,
        "disclaimer": "合成图像上的成绩只反映行为规则层的逻辑正确性，不代表真实栏舍识别精度。"
                      "真实精度必须在真实猪舍图像/视频上评测。",
    }
    p = os.path.join(BASE, "results", "eval_behavior_synthetic.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\n结果已写入 {p}")
    return out


if __name__ == "__main__":
    main()
