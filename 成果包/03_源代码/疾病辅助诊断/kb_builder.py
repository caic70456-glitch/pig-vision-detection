# -*- coding: utf-8 -*-
"""知识库构建器 v2：改用「句子级邻近」作为主判据。

v1 用「段落级共现」：只要症状词和病名出现在同一段就计入。
问题：多病综述里一个段落能提到 5-10 种病，段内任何症状都会被挂到所有病名上，
      造成大面积跨病污染（实测副猪嗜血杆菌病被挂上「腹泻/流产/神经症状」）。

v2 改为三级证据来源，按可信度排序：
    1. 专论文献（题名含病名）→ 全文症状计入，最高可信
    2. 句子级邻近：症状与病名出现在同一句，或相距 <= 2 句 → 计入
    3. 段落级共现：仅当该段只提到一种疾病时才计入（排除多病综述段落）
不再使用「整段共现」这一粗粒度判据。
"""
import argparse
import glob
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
TEXT_DIR = r"C:\Users\ASUS\Downloads\AIC-文献\文本"
DATA_DIR = os.path.join(BASE, "data")
REFS = os.path.join(DATA_DIR, "refs.json")

DISEASES = json.load(io.open(os.path.join(DATA_DIR, "disease_dict.json"), encoding="utf-8"))
SYMPTOMS = json.load(io.open(os.path.join(DATA_DIR, "symptom_dict.json"), encoding="utf-8"))
SEP = "=" * 60

DRUG_HINTS = ["疫苗", "免疫", "消毒", "抗生素", "抗菌药", "中草药", "益生菌", "药敏",
              "休药期", "禁用", "恩诺沙星", "替米考星", "氟苯尼考", "阿莫西林",
              "头孢", "泰乐菌素", "多西环素", "磺胺", "黏菌素", "金霉素", "土霉素",
              "林可霉素", "泰妙菌素", "支原净", "氟喹诺酮"]
AGE_WORDS = ["哺乳仔猪", "新生仔猪", "保育猪", "断奶仔猪", "仔猪", "育肥猪",
             "生长育肥猪", "妊娠母猪", "母猪", "种猪", "后备母猪", "公猪", "成年猪"]

_CJK = r"[\u3400-\u4dbf\u4e00-\u9fff]"
_CJK_SPACE = re.compile(rf"(?<={_CJK})\s+(?={_CJK})")


def normalize_cjk(text):
    """压掉中文字符之间的空白。

    PDF 抽取常把「黄疸」切成「黄 疸」、把「紫斑」切成「紫 斑」，
    不做这一步，跨空格的症状词全部匹配不到——这是知识库精度的前提。
    """
    prev = None
    while prev != text:
        prev = text
        text = _CJK_SPACE.sub("", text)
    return text


def split_sentences(text):
    return [s.strip() for s in re.split(r"(?<=[。；！？])", text) if len(s.strip()) >= 6]


def load_corpus():
    refs = {r["no"]: r for r in json.load(io.open(REFS, encoding="utf-8"))}
    docs = {}
    for f in sorted(glob.glob(os.path.join(TEXT_DIR, "*.txt"))):
        no = int(os.path.basename(f)[:2])
        raw = io.open(f, encoding="utf-8").read()
        docs[no] = {
            "body": normalize_cjk(raw.split(SEP, 1)[-1]),
            "title": refs.get(no, {}).get("title", ""),
            "source": refs.get(no, {}).get("source", ""),
            "year": refs.get(no, {}).get("year", ""),
            "first_author": refs.get(no, {}).get("firstAuthor", ""),
        }
    return docs


def symptom_hits(text):
    """返回 text 中命中的标准症状集合（长词优先，同一症状只记一次）。"""
    hits = {}
    for std, words in SYMPTOMS.items():
        for w in words:
            if w in text:
                if std not in hits or len(w) > len(hits[std]):
                    hits[std] = w
    return hits


def extract(docs):
    raw = {}
    # 每篇文献覆盖多少种疾病，用于识别「多病综述」
    doc_dis = {}
    for no, d in docs.items():
        doc_dis[no] = [dn for dn, al in DISEASES.items() if any(a in d["body"] for a in al)]

    for dname, aliases in DISEASES.items():
        rec = {
            "sym_title": Counter(), "sym_adj": Counter(), "sym_para": Counter(),
            "evidence": defaultdict(list), "src_docs": defaultdict(set),
            "age": Counter(), "drugs": Counter(), "docs": set(), "title_docs": set(),
        }
        for no, d in docs.items():
            body, title = d["body"], d["title"]
            in_title = any(a in title for a in aliases)
            sents = split_sentences(body)
            other_dis_in_doc = [x for x in doc_dis[no] if x != dname]

            # ---- 来源1：专论文献，全文症状计入 ----
            if in_title:
                rec["title_docs"].add(no)
                rec["docs"].add(no)
                for std in symptom_hits(body):
                    rec["sym_title"][std] += 1
                    rec["src_docs"][std].add(no)

            # ---- 来源2：句子级邻近（病名句 + 后 2 句）----
            for i, s in enumerate(sents):
                if not any(a in s for a in aliases):
                    continue
                rec["docs"].add(no)
                window = " ".join(sents[i:i + 3])
                for std in symptom_hits(window):
                    rec["sym_adj"][std] += 1
                    rec["src_docs"][std].add(no)
                    if len(rec["evidence"][std]) < 2:
                        rec["evidence"][std].append([no, s[:130]])

            # ---- 来源3：段落级共现，但仅当该段不涉及其他疾病 ----
            for para in re.split(r"\n{2,}", body):
                para = para.strip()
                if len(para) < 20 or not any(a in para for a in aliases):
                    continue
                if any(any(a in para for a in DISEASES[x]) for x in other_dis_in_doc):
                    continue  # 多病段落，判据不可靠，丢弃
                for std in symptom_hits(para):
                    rec["sym_para"][std] += 1
                    rec["src_docs"][std].add(no)

            # 日龄与用药（仅在病名附近统计，避免全院落噪声）
            near_all = " ".join(s for s in sents if any(a in s for a in aliases))
            if in_title:
                near_all = body
            for a in AGE_WORDS:
                if a in near_all:
                    rec["age"][a] += 1
            for g in DRUG_HINTS:
                if g in near_all:
                    rec["drugs"][g] += near_all.count(g)
        raw[dname] = rec
    return raw


def build(docs, raw):
    all_syms = set()
    for rec in raw.values():
        all_syms |= set(rec["sym_title"]) | set(rec["sym_adj"]) | set(rec["sym_para"])
    sym_disease_count = Counter()
    for rec in raw.values():
        for s in set(rec["sym_title"]) | set(rec["sym_adj"]) | set(rec["sym_para"]):
            sym_disease_count[s] += 1
    n_sym_disease = max(len(raw), 1)

    out = []
    for dname, rec in raw.items():
        present = set(rec["sym_title"]) | set(rec["sym_adj"]) | set(rec["sym_para"])
        if not present:
            continue
        n_docs = max(len(rec["docs"]), 1)
        n_title = len(rec["title_docs"])
        symptoms = {}
        for s in present:
            nt = rec["sym_title"].get(s, 0)
            na, np_ = rec["sym_adj"].get(s, 0), rec["sym_para"].get(s, 0)
            score = nt * 3 + na * 2 + np_ * 1
            docs_with = rec["src_docs"].get(s, set())
            n_docs_with = len(docs_with)
            title_support = len(docs_with & rec["title_docs"])
            prevalence = sym_disease_count[s] / n_sym_disease

            # 分级：专论文献支持 + 独立文献数为准
            if title_support >= 1 and n_docs_with >= 2:
                tier = "强"
            elif title_support >= 1:
                tier = "中"
            elif n_docs_with >= 2 and prevalence <= 0.45:
                tier = "中"
            else:
                tier = "弱"

            ev = rec["evidence"].get(s, [])
            if not ev:
                for no in sorted(docs_with):
                    for sent in split_sentences(docs[no]["body"]):
                        if any(w in sent for w in SYMPTOMS[s]):
                            ev = [[no, sent[:130]]]
                            break
                    if ev:
                        break

            symptoms[s] = {
                "score": score, "n_docs_with": n_docs_with,
                "title_support": title_support, "prevalence": round(prevalence, 3),
                "coverage": round(n_docs_with / n_docs, 3), "tier": tier, "evidence": ev,
            }

        out.append({
            "name": dname, "aliases": [a for a in DISEASES[dname] if a != dname],
            "symptoms": symptoms,
            "age_hints": [a for a, _ in rec["age"].most_common(6)],
            "drugs": [g for g, _ in rec["drugs"].most_common(8)],
            "docs": sorted(rec["docs"]), "title_docs": sorted(rec["title_docs"]),
        })
    out.sort(key=lambda r: (-len(r["title_docs"]), -len(r["symptoms"])))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="diseases.json")
    args = ap.parse_args()

    docs = load_corpus()
    raw = extract(docs)
    records = build(docs, raw)

    refs = {r["no"]: r for r in json.load(io.open(REFS, encoding="utf-8"))}
    sources = {str(no): {"title": r["title"], "source": r["source"], "year": r["year"],
                         "author": r["firstAuthor"]} for no, r in refs.items()}
    payload = {
        "meta": {"built_from": f"{len(docs)} 篇中文文献（CNKI 检索，2025-2026 年为主）",
                 "disease_count": len(records), "extractor": "sentence-proximity+title-anchor",
                 "note": "规则抽取，非临床诊断结论；症状置信度需人工复核"},
        "sources": sources, "diseases": records,
    }
    path = os.path.join(DATA_DIR, args.out)
    io.open(path, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False, indent=1))

    n_sym = sum(len(r["symptoms"]) for r in records)
    tc = Counter(s["tier"] for r in records for s in r["symptoms"].values())
    print(f"疾病 {len(records)} 种；症状关联 {n_sym} 条"
          f"（强 {tc['强']} / 中 {tc['中']} / 弱 {tc['弱']}）")
    print(f"-> {path}  ({os.path.getsize(path)/1024:.1f} KB)")
    return path


if __name__ == "__main__":
    main()
