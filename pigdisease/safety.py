# -*- coding: utf-8 -*-
"""安全约束层：独立于 AI 推理的硬规则。

为什么单独一层：
    用药安全不能依赖概率模型的"自觉"。无论上游诊断给出什么，用药相关内容
    必须经过本层校验才允许呈现。这是本系统可审计性的基础。

三条硬规则：
    R1 禁用药物拦截：命中禁用清单 -> 标红阻断，给出禁用原因
    R2 休药期强制提示：任何具体药物建议 -> 必须附带休药期核对要求
    R3 证据不足提示：诊断证据太弱 -> 明确降级为"仅提示方向"，不输出用药建议
"""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")

DISCLAIMER = ("本系统为学习研究用途的辅助工具，不能替代执业兽医的现场检查与诊断，"
              "不可作为用药依据。确诊与用药请遵循当地兽医指导和产品标签规定。")

# 预防/管理类词：属于防控措施，不是可用于治疗的药物，不应作为"用药建议"列出
NON_DRUG_TERMS = {"疫苗", "免疫", "消毒", "药敏", "休药期", "禁用", "益生菌", "中草药"}


def load_banned(path=None):
    path = path or os.path.join(DATA_DIR, "banned_drugs.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    table = {}
    for item in data.get("banned", []):
        for alias in {item["name"], *item.get("aliases", [])}:
            table[alias] = item
    return data, table


_BANNED_DATA, _BANNED_TABLE = load_banned()


def scan_banned(text):
    """在任意文本里扫描禁用药物名。"""
    hits = []
    for name, item in _BANNED_TABLE.items():
        if name and name in text:
            hits.append(item)
    # 去重
    seen, uniq = set(), []
    for h in hits:
        if h["name"] not in seen:
            seen.add(h["name"])
            uniq.append(h)
    return uniq


def check(result, raw_text=None):
    """对诊断结果做安全校验，返回 warnings / blocked / drug_advice。

    raw_text 是用户原始输入。必须一起扫描：养殖户常会在描述里直接写
    「我用了氯霉素」，这种禁用药物出现在输入中就必须立刻阻断，
    不能只在知识库的药物线索里查。
    """
    warnings, blocked = [], []
    candidates = result.get("candidates", [])
    best = candidates[0] if candidates else None

    # ---- R0：扫描用户原始输入中的禁用药物 ----
    if raw_text is None:
        raw_text = (result.get("parsed") or {}).get("raw", "") or ""
    input_banned = scan_banned(raw_text)
    for item in input_banned:
        blocked.append({
            "drug": item["name"], "disease": "（用户描述中提及）",
            "reason": item["reason"], "scope": item["scope"],
        })

    # ---- R3：证据不足则不给用药建议 ----
    evidence_ok = bool(best and best.get("evidence", 0) >= 1.0 and best.get("explain", 0) >= 0.2)

    # ---- 收集候选疾病提到的药物线索 ----
    drug_advice = []
    blocked_names = {b["drug"] for b in blocked}
    for c in candidates[:2]:
        for g in c.get("drugs", []):
            if g in NON_DRUG_TERMS:
                continue
            banned = _BANNED_TABLE.get(g)
            if banned:
                if banned["name"] not in blocked_names:
                    blocked.append({
                        "drug": g, "disease": c["disease"],
                        "reason": banned["reason"], "scope": banned["scope"],
                    })
                    blocked_names.add(banned["name"])
            else:
                drug_advice.append({"drug": g, "disease": c["disease"], "source": "文献共现线索"})

    # 同一药物多病重复时去重
    seen, uniq_drugs = set(), []
    for d in drug_advice:
        if d["drug"] not in seen:
            seen.add(d["drug"])
            uniq_drugs.append(d)
    drug_advice = uniq_drugs

    # ---- R1 ----
    if blocked:
        names = "、".join(b["drug"] for b in blocked)
        warnings.append(
            f"检测到禁用药物「{names}」，已阻断相关建议。"
            "氯霉素、硝基呋喃类、β-兴奋剂等属食品动物禁用药物，使用违法且存在食品安全风险。"
            "如已使用，请立即停止并咨询执业兽医，同时注意产品休药期与上市规定。"
        )

    # ---- R2 ----
    if drug_advice and evidence_ok:
        warnings.append(
            "以下药物名称来自文献共现线索，不是处方。任何用药前必须核对产品标签与"
            "农业农村部最新公告规定的休药期、用法用量与靶动物，并遵守弃奶期/休药期。"
        )

    # ---- R3 ----
    if not evidence_ok:
        warnings.append(
            "当前证据强度不足，系统不提供具体用药建议，仅提示可能的疾病方向。"
            "请补充症状描述，或直接联系执业兽医。"
        )
        drug_advice = []

    if best and len(best.get("title_docs", [])) == 0:
        warnings.append(
            f"知识库中缺少「{best['disease']}」的专论文献，其症状依据较弱，请谨慎采信。"
        )

    return {
        "disclaimer": DISCLAIMER,
        "evidence_sufficient": evidence_ok,
        "input_banned_drugs": [b["name"] for b in input_banned],
        "blocked": blocked,
        "drug_advice": drug_advice,
        "warnings": warnings,
        "banned_list_meta": {
            "source": _BANNED_DATA["_meta"]["source"],
            "note": _BANNED_DATA["_meta"]["IMPORTANT"],
        },
    }


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    import diagnose

    # 自测：正常案例 + 构造一个含禁用药物的文本
    for t in ["育肥猪咳嗽喘气，体温升高，精神沉郁",
              "仔猪拉稀，黄白色，使用氯霉素和呋喃唑酮治疗后无好转"]:
        r = diagnose.diagnose_text(t)
        print("=" * 72)
        print(f"输入：{t}")
        s = r["safety"]
        print(f"证据是否充分：{s['evidence_sufficient']}")
        if s["blocked"]:
            for b in s["blocked"]:
                print(f"  ✗ 阻断：{b['drug']}（{b['reason']}）")
        if s["drug_advice"]:
            print("  药物线索：" + "、".join(d["drug"] for d in s["drug_advice"]))
        for w in s["warnings"]:
            print(f"  ⚠ {w}")
        # 直接测扫描器
        print(f"  文本级扫描：{[b['name'] for b in scan_banned(t)]}")
