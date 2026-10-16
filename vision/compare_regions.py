# -*- coding: utf-8 -*-
"""对比「布局先验推断」与「人工标定」两种设施区域下的行为识别结果。

目的：量化标定带来的改善，并说明标定为何必要。
用同一个自训猪检测器的检测结果，只切换设施区域来源，保证对比公平。
"""
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, r"E:\harness\aic\vision")
import bootstrap  # noqa: F401,E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import detector  # noqa: E402
import regions as R  # noqa: E402
from behavior import BEHAVIOR_CN, classify_scene  # noqa: E402
from scene import compute_scene  # noqa: E402

BASE = r"E:\harness\aic\vision"
IMG_DIR = os.path.join(BASE, "data", "pigdetect", "extract", "test", "images")
CFG = os.path.join(BASE, "data", "pigdetect", "extract", "test", "regions.json")
OUT = os.path.join(BASE, "results", "region_calibration_effect.json")

N_IMAGES = 8


def run(backend, image_path, region_objs):
    from PIL import Image
    img = Image.open(image_path)
    res = backend.detect(img)
    scene = compute_scene(res, regions=region_objs)
    beh = classify_scene(scene, tracks=[], track_scenes=1)
    return res, scene, beh


def summarize(beh):
    return Counter(v.behavior for v in beh.verdicts)


def main():
    cfg = R.load_config(CFG)
    if not cfg:
        print(f"未找到标定配置 {CFG}，请先运行 make_demo_regions.py")
        return

    backend = detector.build_backend(kind="auto")
    print(f"检测后端：{backend.describe()['name']}")
    print(f"标定配置：{os.path.basename(CFG)}")
    print(f"对比图片：{N_IMAGES} 张\n")

    imgs = sorted(f for f in os.listdir(IMG_DIR) if f.endswith(".jpg"))[:N_IMAGES]

    tot_inferred = Counter()
    tot_calibrated = Counter()
    rows = []

    print(f"{'图片':<26}{'检出':>5}   "
          f"{'先验推断 (采食/饮水/争斗)':<30}{'人工标定 (采食/饮水/争斗)':<30}")
    print("-" * 96)

    for n in imgs:
        p = os.path.join(IMG_DIR, n)
        from PIL import Image
        W, H = Image.open(p).size

        # A) 先验推断（regions=None）
        res_a, sc_a, bh_a = run(backend, p, None)
        # B) 人工标定
        region_objs = R.to_pixel_regions(cfg, (W, H))
        res_b, sc_b, bh_b = run(backend, p, region_objs)

        ca, cb = summarize(bh_a), summarize(bh_b)
        tot_inferred += ca
        tot_calibrated += cb
        na = len(res_a.animals)

        def fmt(c):
            return (f"采食{c.get('eating',0):>2}/饮水{c.get('drinking',0):>2}"
                    f"/争斗{c.get('aggressive',0):>2}")

        print(f"{n[:24]:<26}{na:>5}   {fmt(ca):<30}{fmt(cb):<30}")
        rows.append({
            "image": n, "n_pigs": na,
            "inferred": dict(ca), "calibrated": dict(cb),
        })

    print("-" * 96)

    def pct(c):
        t = sum(c.values()) or 1
        return {k: round(v * 100 / t, 1) for k, v in c.items()}

    pa, pb = pct(tot_inferred), pct(tot_calibrated)
    print("\n【汇总行为占比】")
    print(f"{'行为':<8}{'先验推断':>12}{'人工标定':>12}{'变化':>10}")
    for k in ("eating", "drinking", "resting", "standing", "walking", "aggressive"):
        a, b = pa.get(k, 0.0), pb.get(k, 0.0)
        mark = ""
        if k == "aggressive":
            mark = "  ← 误报应显著下降"
        print(f"{BEHAVIOR_CN.get(k,k):<8}{a:>11.1f}%{b:>11.1f}%{b-a:>+9.1f}%{mark}")

    print(f"\n总目标数：{sum(tot_inferred.values())}")

    # 记录区域来源
    out = {
        "note": ("同一检测结果下，仅切换设施区域来源做对比。"
                 "演示用的标定配置为目视估计，真实部署应在图上重新框选。"),
        "config": CFG,
        "regions_calibrated": {k: len(v.get("boxes", [])) for k, v in cfg["regions"].items()},
        "n_images": len(imgs),
        "n_targets": sum(tot_inferred.values()),
        "inferred_pct": pa, "calibrated_pct": pb,
        "per_image": rows,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"结果已写入 {OUT}")


if __name__ == "__main__":
    main()
