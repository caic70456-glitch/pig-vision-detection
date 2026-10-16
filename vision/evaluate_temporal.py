# -*- coding: utf-8 -*-
"""时序行为评测：在合成帧序列上验证「站立/行走/卧倒/争斗/采食后离开」的时序判定。

这是单帧无法完成的部分——必须靠跨帧位移与面积变化，因此单独评测。
"""
import io
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import detector  # noqa: E402
import pipeline  # noqa: E402
from behavior import BEHAVIOR_CN, classify_scene  # noqa: E402
from scene import compute_scene, compute_tracks  # noqa: E402


def run_sequence(seq, image_size):
    """在给定序列上跑时序流水线，返回每帧判定与最终聚合结果。"""
    scenes, metas = [], None
    for dets_raw in seq["frames"]:
        dets = [detector.Detection(tuple(d["box"]), d["label"], d["score"]) for d in dets_raw]
        r = detector.DetectionResult(detections=dets, backend="synthetic",
                                     approximate=True, image_size=tuple(image_size))
        scenes.append(compute_scene(r))

    tracks = compute_tracks(scenes)
    first = classify_scene(scenes[0], tracks=tracks, track_scenes=len(scenes))
    last = classify_scene(scenes[-1], tracks=tracks, track_scenes=len(scenes))
    # 聚合分布
    agg = {}
    total = 0
    for sf in scenes:
        br = classify_scene(sf, tracks=tracks, track_scenes=len(scenes))
        for k, v in br.distribution.items():
            agg[k] = agg.get(k, 0) + v
        total += sum(br.distribution.values())
    pct = {k: v * 100.0 / total for k, v in agg.items()} if total else {}
    return first, last, tracks, pct


def main():
    meta_p = os.path.join(BASE, "synthetic_frames", "sequences.json")
    if not os.path.isfile(meta_p):
        print("未找到合成序列，请先运行： python make_sequences.py")
        return
    with io.open(meta_p, encoding="utf-8") as fh:
        data = json.load(fh)

    n_total = n_correct = 0
    rows = []
    print(f"{'序列':<18}{'检查点':<8}{'目标':>5}{'正确':>5}{'准确率':>8}   对比")
    print("-" * 96)

    for seq in data["sequences"]:
        first, last, tracks, pct = run_sequence(seq, data["image_size"])

        checks = [("末帧", last, seq["expected_last"])]
        if seq.get("expected_first"):
            checks.append(("首帧", first, seq["expected_first"]))

        for label, br, expected in checks:
            expected = {int(k): v for k, v in expected.items()}
            det = []
            for k, v in enumerate(br.verdicts):
                if k not in expected:
                    continue
                # br.verdicts 里是 BehaviorVerdict 数据类，用属性访问
                exp, got = expected[k], v.behavior
                ok = exp == got
                n_total += 1
                n_correct += ok
                det.append(f"#{k+1}:{BEHAVIOR_CN.get(exp,exp)}"
                           f"{'✓' if ok else '→' + BEHAVIOR_CN.get(got,got)}")
            acc = sum("✓" in x for x in det) / len(det) if det else 0.0
            print(f"{seq['name']:<18}{label:<8}{len(det):>5}"
                  f"{sum('✓' in x for x in det):>5}{acc:>7.0%}   {' '.join(det)}")

        tr = "、".join(f"#{t.track_id+1} 位移{t.displacement:.3f} 速度{t.speed:.4f}"
                       f" 面积变化{t.area_change:+.2f}" for t in tracks[:3])
        print(f"{'':<18}{'时序特征':<8}  {tr}")
        print(f"{'':<18}{'行为占比':<8}  "
              f"{json.dumps({BEHAVIOR_CN.get(k,k): round(v,1) for k,v in pct.items()}, ensure_ascii=False)}")
        rows.append({"sequence": seq["name"], "track_features": [t.to_dict() for t in tracks],
                     "distribution_pct": pct})

    print("-" * 96)
    overall = n_correct / n_total if n_total else 0.0
    print(f"时序判定总体：{n_correct}/{n_total} = {overall:.1%}")

    out = {"dataset": "synthetic_frames（合成帧序列，验证时序逻辑）",
           "n_checks": n_total, "n_correct": n_correct,
           "accuracy": round(overall, 4), "sequences": rows,
           "disclaimer": "合成序列只验证时序规则逻辑，不代表真实视频识别精度。"}
    p = os.path.join(BASE, "results", "eval_temporal_synthetic.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"结果已写入 {p}")
    return out


if __name__ == "__main__":
    main()
