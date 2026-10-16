# -*- coding: utf-8 -*-
"""诊断准确率评测：构造案例 -> 跑诊断 -> 算 Top-1 / Top-3 命中率与 MRR。

用例来源：基于文献中描述典型症状构造（不直接用原文，避免病名泄漏），
每条标注 ground truth 疾病。评测集随知识库一起演进。

输出 results/eval_results.json，可直接用于作品方案的「应用成效」章节。
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

# ---------- 评测用例 ----------
# 每条：(描述, 期望疾病, 备注)
CASES = [
    ("7日龄内新生仔猪呕吐，随即出现水样腹泻，脱水严重，发病率高",
     "猪流行性腹泻", "PED 典型：呕吐后水样腹泻，7日龄内高病死率"),
    ("保育猪眼睑和面部水肿，突然死亡，之前有轻度腹泻",
     "猪大肠杆菌病", "仔猪水肿病：眼睑水肿+腹泻"),
    ("仔猪排黄白色糊状稀粪，精神不振，吃奶减少",
     "猪大肠杆菌病", "仔猪黄白痢：黄白色粪便"),
    ("保育猪体温升高，关节肿胀跛行，呼吸困难，耳尖发绀",
     "副猪嗜血杆菌病", "格拉瑟病：多发性浆膜炎，关节肿胀为强证据"),
    ("育肥猪长期干咳，生长迟缓，被毛粗乱，体温不高",
     "猪支原体肺炎", "气喘病：干咳+生长迟缓+被毛粗乱，体温通常不高"),
    ("母猪流产产死胎，仔猪呼吸困难，耳部发绀，断奶后仔猪消瘦",
     "猪繁殖与呼吸综合征", "蓝耳病：繁殖障碍+呼吸困难+发绀"),
    ("仔猪腹泻，粪便带血和黏液，消瘦，生长缓慢",
     "猪流行性腹泻", "肠道病症状群（PED 为主要候选之一）"),
    ("猪只出现皮肤红斑疹块，呈方形，体温升高，关节疼痛跛行",
     "猪丹毒", "猪丹毒：方形红斑疹块为特征"),
    ("仔猪出现神经症状，转圈抽搐，四肢划水，体温升高",
     "猪链球菌病", "链球菌性脑膜炎：神经症状"),
    ("育肥猪高热，皮肤有出血点，精神沉郁，先便秘后腹泻",
     "猪瘟", "猪瘟：出血点+先便秘后腹泻"),
    ("断奶仔猪消瘦，呼吸困难，皮肤可见出血点和紫斑，生长迟缓",
     "猪圆环病毒病", "圆环病毒相关疾病：消瘦+呼吸困难"),
    ("母猪发热流产，仔猪出现神经症状和呼吸困难，死亡率高",
     "猪伪狂犬病", "伪狂犬：流产+仔猪神经症状"),
    ("猪只采食霉变饲料后呕吐腹泻，生长迟缓，部分母猪流产",
     "猪霉菌毒素中毒", "霉菌毒素：有霉变饲料暴露史"),
    ("保育猪突然死亡，口鼻流出泡沫状液体，咽喉部肿胀，呼吸困难",
     "猪肺疫", "猪肺疫：最急性型，咽喉肿胀"),
    ("育肥猪高热，呼吸困难，犬坐姿势，鼻流脓性分泌物，胸膜摩擦音",
     "猪传染性胸膜肺炎", "传染性胸膜肺炎：犬坐+脓性鼻液"),
]


def main(topk=3):
    dx = diagnose.Diagnoser()
    import nlu
    import safety

    rows = []
    hit1 = hit3 = 0
    rr_sum = 0.0

    print(f"评测集：{len(CASES)} 条　知识库：{len(dx.diseases)} 种疾病")
    print("=" * 96)
    for i, (text, expect, note) in enumerate(CASES, 1):
        parsed = nlu.normalize(text)
        res = dx.evaluate(parsed["symptoms"], parsed["ages"], topk=6)
        names = [c["disease"] for c in res["candidates"]]
        rank = names.index(expect) + 1 if expect in names else None
        if rank == 1:
            hit1 += 1
        if rank and rank <= topk:
            hit3 += 1
        rr_sum += (1.0 / rank) if rank else 0.0

        top1 = names[0] if names else "—"
        mark = "✓" if rank == 1 else ("△" if rank and rank <= topk else "✗")
        print(f"[{i:>2}] {mark} 期望 {expect:<14} 实际Top1 {top1:<16} 命中名次 {rank or '未命中'}")
        print(f"     症状识别：{'、'.join(parsed['symptoms'])}")
        rows.append({
            "case": i, "text": text, "expect": expect, "note": note,
            "parsed_symptoms": parsed["symptoms"], "parsed_ages": parsed["ages"],
            "rank": rank, "top": [{"disease": c["disease"], "score": round(c["score"], 3),
                                   "confidence": c["confidence"]} for c in res["candidates"][:5]],
        })

    n = len(CASES)
    metrics = {
        "n_cases": n,
        "top1_accuracy": round(hit1 / n, 4),
        "top3_accuracy": round(hit3 / n, 4),
        "mrr": round(rr_sum / n, 4),
        "kb_diseases": len(dx.diseases),
    }

    # 分层统计：按期望疾病的「知识库支撑强度」分组
    # 目的：区分「算法问题」与「知识库覆盖问题」
    strong_group = {"n": 0, "hit1": 0, "hit3": 0}
    weak_group = {"n": 0, "hit1": 0, "hit3": 0}
    for r in rows:
        d = next((x for x in dx.diseases if x["name"] == r["expect"]), None)
        n_strong = 0
        if d:
            n_strong = sum(1 for v in d["symptoms"].values() if v["tier"] in ("强", "中"))
        grp = strong_group if n_strong >= 3 else weak_group
        grp["n"] += 1
        if r["rank"] == 1:
            grp["hit1"] += 1
        if r["rank"] and r["rank"] <= topk:
            grp["hit3"] += 1
    metrics["stratified"] = {
        "kb_supported(强中证据>=3)": {
            "n": strong_group["n"],
            "top1": round(strong_group["hit1"] / strong_group["n"], 4) if strong_group["n"] else None,
            "top3": round(strong_group["hit3"] / strong_group["n"], 4) if strong_group["n"] else None,
        },
        "kb_weak(强中证据<3)": {
            "n": weak_group["n"],
            "top1": round(weak_group["hit1"] / weak_group["n"], 4) if weak_group["n"] else None,
            "top3": round(weak_group["hit3"] / weak_group["n"], 4) if weak_group["n"] else None,
        },
    }

    print("=" * 96)
    print(f"Top-1 命中率：{metrics['top1_accuracy']:.1%}  ({hit1}/{n})")
    print(f"Top-3 命中率：{metrics['top3_accuracy']:.1%}  ({hit3}/{n})")
    print(f"MRR         ：{metrics['mrr']:.3f}")
    print("\n分层结果（用于区分算法问题与知识库覆盖问题）：")
    for k, v in metrics["stratified"].items():
        t1 = f"{v['top1']:.1%}" if v["top1"] is not None else "—"
        t3 = f"{v['top3']:.1%}" if v["top3"] is not None else "—"
        print(f"  {k:<28} n={v['n']:<3} Top-1 {t1:<8} Top-3 {t3}")

    # 安全层专项测试
    safety_cases = [
        ("仔猪腹泻，之前用了氯霉素和呋喃唑酮", ["氯霉素", "呋喃唑酮"]),
        ("育肥猪咳嗽，建议用诺氟沙星治疗", ["诺氟沙星"]),
        ("猪只发热，使用克伦特罗促进生长", ["克伦特罗"]),
        ("保育猪关节肿胀，用阿莫西林治疗", []),
    ]
    print("\n" + "=" * 96)
    print("安全层测试（禁用药物拦截）")
    s_ok = 0
    s_rows = []
    for text, should_block in safety_cases:
        hits = [b["name"] for b in safety.scan_banned(text)]
        ok = set(should_block).issubset(set(hits)) if should_block else not hits
        s_ok += ok
        print(f"  {'✓' if ok else '✗'} {text[:34]:<36} 应拦截 {should_block or '无'} -> 实拦 {hits or '无'}")
        s_rows.append({"text": text, "expect_block": should_block, "got": hits, "pass": ok})
    block_metrics = {"n": len(safety_cases), "passed": s_ok,
                     "accuracy": round(s_ok / len(safety_cases), 4)}
    print(f"  拦截测试通过：{s_ok}/{len(safety_cases)}")

    out_dir = os.path.join(BASE, "results")
    os.makedirs(out_dir, exist_ok=True)
    payload = {"metrics": metrics, "safety_metrics": block_metrics,
               "cases": rows, "safety_cases": s_rows}
    path = os.path.join(out_dir, "eval_results.json")
    io.open(path, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"\n结果已写入 {path}")
    return payload


if __name__ == "__main__":
    main()
