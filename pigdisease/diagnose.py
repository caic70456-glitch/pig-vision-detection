# -*- coding: utf-8 -*-
"""诊断推理层：症状加权匹配 -> 候选疾病排序 + 逐条匹配依据。

算法（可解释、可复现，不需要训练数据）：
    evidence(d) = Σ_symptom  tier_weight × (1 - prevalence) × (0.6 + 0.4 × coverage)
    explain(d)  = |命中症状| / |输入症状|          # 症状解释力：别漏掉用户说的
    age_bonus(d)= 0.15 若日龄分组命中该病的 age_hints
    score(d)    = evidence × (0.7 + 0.3 × explain) + age_bonus

设计说明：
  - tier_weight 体现证据强度（强/中/弱 = 3/2/1）
  - (1 - prevalence) 是症状特异性：几乎所有病都有的症状（如腹泻）区分度低，权重自然被压低
  - coverage 是该病文献中对这一症状的记载一致度
  - explain 防止「只靠一个高频症状就冲到第一」
  - age_bonus 是兽医鉴别诊断里极重要的维度（同一症状在仔猪和育肥猪指向不同病）
"""
import json
import math
import os

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")

TIER_WEIGHT = {"强": 3.0, "中": 2.0, "弱": 1.0}
# 说明：tier 权重经过参数扫描（tune_tiers.py），强3/中2/弱1.0 在 Top-3 与
# kb_supported 分层上都是最优。把弱权重压到 0.5 会明显变差（Top-3 60%→46.7%），
# 说明弱证据里含有效信号，不应一概压制。调整前请先跑 tune_tiers.py 验证。


def load_kb(path=None):
    path = path or os.path.join(DATA_DIR, "diseases.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class Diagnoser:
    def __init__(self, kb=None):
        self.kb = kb or load_kb()
        self.diseases = self.kb["diseases"]
        self.sources = self.kb.get("sources", {})
        # 症状 -> 出现在多少种疾病中（用于运行时特异性，和构建期口径保持一致）
        self.sym_disease_count = {}
        for d in self.diseases:
            for s in d["symptoms"]:
                self.sym_disease_count[s] = self.sym_disease_count.get(s, 0) + 1
        self.n_disease = max(len(self.diseases), 1)
        # 可按医生经验调整的优先/排除表（数据文件驱动，不写死在代码里）
        self.overrides = self._load_overrides()

    def _load_overrides(self):
        p = os.path.join(DATA_DIR, "overrides.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        return {"boost": {}, "suppress": {}, "note": "可选：人工校正表"}

    def _specificity(self, symptom):
        """症状特异性 = 1 - 该症状在多少种疾病中出现。越独特越有鉴别价值。"""
        prev = self.sym_disease_count.get(symptom, 0) / self.n_disease
        return max(0.0, 1.0 - prev)

    def evaluate(self, symptoms, ages=None, topk=3, min_explain=0.2):
        """核心：给定标准症状集合，返回排序后的候选疾病。"""
        symptoms = [s for s in (symptoms or []) if s]
        ages = ages or []
        if not symptoms:
            return {"query": {"symptoms": [], "ages": ages}, "candidates": [],
                    "note": "未识别到任何标准症状，请补充描述"}

        results = []
        for d in self.diseases:
            dsym = d["symptoms"]
            hits, misses = [], []
            evidence = 0.0
            for s in symptoms:
                if s in dsym:
                    info = dsym[s]
                    w = TIER_WEIGHT.get(info["tier"], 1.0)
                    spec = self._specificity(s)
                    cov = info.get("coverage", 0.0)
                    contrib = w * spec * (0.6 + 0.4 * cov)
                    hits.append({"symptom": s, "tier": info["tier"], "contrib": round(contrib, 3),
                                 "coverage": cov, "prevalence": info.get("prevalence"),
                                 "n_docs": info.get("n_docs_with", 0),
                                 "title_support": info.get("title_support", 0),
                                 "evidence": info.get("evidence", [])})
                    evidence += contrib
                else:
                    misses.append(s)

            # 该病常见但用户未提及的症状（用于提示鉴别与追问）
            unreported = sorted(
                [s for s in dsym if s not in symptoms],
                key=lambda s: -(TIER_WEIGHT.get(dsym[s]["tier"], 1.0) * dsym[s].get("coverage", 0))
            )[:6]

            explain = len(hits) / len(symptoms)
            age_hit = any(a in d.get("age_hints", []) for a in ages)
            age_bonus = 0.15 if age_hit else 0.0

            # 长度归一化：症状表越大的疾病越容易「碰巧」命中，属于类别不平衡。
            # 按该病症状表规模做次线性抑制，避免广谱病名（如 18-19 个症状的病）
            # 靠数量优势霸占所有 Top-3 名额。
            k = max(len(dsym), 1)
            len_norm = (4.0 / (4.0 + k)) ** 0.5

            score = (evidence * (0.7 + 0.3 * explain) + age_bonus) * len_norm
            score *= self.overrides.get("boost", {}).get(d["name"], 1.0)
            score *= self.overrides.get("suppress", {}).get(d["name"], 1.0)

            if score > 0:
                results.append({
                    "disease": d["name"],
                    "aliases": d.get("aliases", []),
                    "score": score,
                    "evidence": round(evidence, 3),
                    "len_norm": round(len_norm, 3),
                    "n_symptoms_kb": k,
                    "explain": round(explain, 3),
                    "age_hit": age_hit,
                    "matched": hits,
                    "unreported": unreported,
                    "docs": d.get("docs", []),
                    "title_docs": d.get("title_docs", []),
                    "drugs": d.get("drugs", []),
                })

        results.sort(key=lambda r: -r["score"])
        top = results[:topk]
        # 置信度：以本候选自身的证据绝对强度为主，避免"矮子里拔将军"被算成高置信
        for r in top:
            r["confidence"] = round(min(1.0, r["evidence"] / 6.0), 3)

        out = {"query": {"symptoms": symptoms, "ages": ages}, "candidates": top}
        if top:
            best = top[0]
            if best["evidence"] < 1.0 or best["explain"] < min_explain:
                out["note"] = ("知识库对当前描述覆盖不足，结果仅供参考；"
                               "建议补充更多症状或咨询执业兽医。")
            elif len(top) > 1 and (best["score"] - top[1]["score"]) / max(best["score"], 1e-9) < 0.15:
                out["note"] = "前两位候选得分接近，需结合流行病学与现场检查进一步鉴别。"
        return out

    def differential(self, result):
        """生成鉴别诊断说明：候选之间的关键区分点。"""
        cands = result.get("candidates", [])
        if len(cands) < 2:
            return []
        a = cands[0]
        lines = []
        a_syms = {h["symptom"] for h in a["matched"]}
        for b in cands[1:]:
            b_syms = {h["symptom"] for h in b["matched"]}
            only_a = sorted(a_syms - b_syms)
            only_b = sorted(b_syms - a_syms)
            lines.append({
                "pair": f"{a['disease']} vs {b['disease']}",
                "supports_top1": [s for s in only_a if s in {h['symptom'] for h in a['matched']}],
                "supports_other": only_b,
            })
        return lines


def diagnose_text(text, topk=3, use_llm=None):
    """便捷函数：原始口语文本 -> 完整诊断结果（含 NLU 与安全层）。"""
    import nlu  # 同目录
    import safety

    parsed = nlu.normalize(text, use_llm=use_llm)
    dx = Diagnoser()
    result = dx.evaluate(parsed["symptoms"], parsed["ages"], topk=topk)
    result["parsed"] = parsed
    result["differential"] = dx.differential(result)
    result["safety"] = safety.check(result, raw_text=text)
    return result


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    dx = Diagnoser()
    meta = dx.kb.get("meta", {})
    print(f"知识库：{meta.get('disease_count')} 种疾病，来源 {meta.get('built_from')}")
    print(f"人工校正表：{dx.overrides.get('note', '无')}\n")

    for t in ["仔猪拉稀，黄白色的，两天了，不吃食",
              "育肥猪咳嗽喘气，体温升高到41度，精神沉郁",
              "母猪流产，产死胎",
              "7日龄内新生仔猪呕吐、水样腹泻，脱水严重"]:
        r = diagnose_text(t)
        print("=" * 72)
        print(f"输入：{t}")
        print(f"识别症状：{'、'.join(r['parsed']['symptoms'])}   日龄：{r['parsed']['ages']}")
        for i, c in enumerate(r["candidates"], 1):
            mt = "、".join(f"{h['symptom']}({h['tier']})" for h in c["matched"])
            print(f"  {i}. {c['disease']:<16} 得分 {c['score']:>5.2f}  "
                  f"置信 {c['confidence']:.0%}  命中 {len(c['matched'])}/{len(r['parsed']['symptoms'])}")
            print(f"     命中症状：{mt}")
        if r.get("note"):
            print(f"  提示：{r['note']}")
        if r["safety"].get("warnings"):
            for w in r["safety"]["warnings"]:
                print(f"  ⚠ {w}")
        print()
