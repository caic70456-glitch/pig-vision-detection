# -*- coding: utf-8 -*-
"""tier 权重调参对比：对同一套评测用例，扫描不同 tier 权重，选最优配置。

只改动 diagnose.TIER_WEIGHT，不改其他逻辑，保证对比公平。
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
import diagnose  # noqa: E402
import nlu  # noqa: E402
import evaluate  # noqa: E402

CONFIGS = [
    ("强3/中2/弱1.0（原）", {"强": 3.0, "中": 2.0, "弱": 1.0}),
    ("强3/中2/弱1.5", {"强": 3.0, "中": 2.0, "弱": 1.5}),
    ("强3/中2/弱2.0", {"强": 3.0, "中": 2.0, "弱": 2.0}),
    ("强4/中2/弱1.0", {"强": 4.0, "中": 2.0, "弱": 1.0}),
    ("强5/中2/弱1.0", {"强": 5.0, "中": 2.0, "弱": 1.0}),
    ("强3/中2/弱0.5", {"强": 3.0, "中": 2.0, "弱": 0.5}),
    ("强6/中3/弱1.5", {"强": 6.0, "中": 3.0, "弱": 1.5}),
]

print(f"{'配置':<22}{'Top-1':>8}{'Top-3':>8}{'MRR':>8}   分层(kb_supported Top3)")
print("-" * 78)
best = None
results = []
for name, w in CONFIGS:
    diagnose.TIER_WEIGHT = w
    dx = diagnose.Diagnoser()
    parsed = [nlu.normalize(t) for t, _, _ in evaluate.CASES]
    hit1 = hit3 = 0
    rr = 0.0
    grp_n = grp_h3 = 0
    for (text, expect, note), p in zip(evaluate.CASES, parsed):
        res = dx.evaluate(p["symptoms"], p["ages"], topk=6)
        names = [c["disease"] for c in res["candidates"]]
        rank = names.index(expect) + 1 if expect in names else None
        if rank == 1:
            hit1 += 1
        if rank and rank <= 3:
            hit3 += 1
        rr += (1.0 / rank) if rank else 0.0
        d = next((x for x in dx.diseases if x["name"] == expect), None)
        ns = sum(1 for v in d["symptoms"].values() if v["tier"] in ("强", "中")) if d else 0
        if ns >= 3:
            grp_n += 1
            if rank and rank <= 3:
                grp_h3 += 1
    n = len(evaluate.CASES)
    row = {"config": name, "top1": hit1 / n, "top3": hit3 / n, "mrr": rr / n,
           "grp_n": grp_n, "grp_top3": grp_h3 / grp_n if grp_n else 0}
    results.append(row)
    print(f"{name:<22}{row['top1']:>7.1%}{row['top3']:>8.1%}{row['mrr']:>8.3f}   "
          f"{grp_h3}/{grp_n} = {row['grp_top3']:.0%}")
    if best is None or row["top3"] > best["top3"] or (row["top3"] == best["top3"] and row["mrr"] > best["mrr"]):
        best = row

print("-" * 78)
print(f"最优配置：{best['config']}  Top-1 {best['top1']:.1%}  Top-3 {best['top3']:.1%}  MRR {best['mrr']:.3f}")
out = os.path.join(BASE, "results", "tier_sweep.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
io.open(out, "w", encoding="utf-8").write(json.dumps(
    {"configs": results, "best": best,
     "note": "同一评测集下扫描 tier 权重；仅用于选参，不代表临床性能"}, ensure_ascii=False, indent=1))
print(f"结果写入 {out}")
