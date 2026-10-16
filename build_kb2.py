# -*- coding: utf-8 -*-
"""从文献抽取「疾病 → 症状 / 易感日龄 / 用药」候选知识库（v2）。

v2 相对 v1 的关键修正：
  v1 要求症状词与病名出现在同一句，导致「猪流行性腹泻」只抽到 1 个症状，
  且 16 种病被整体漏掉。兽医论文的典型写法是：病名在标题和段落首句，
  症状在紧随其后的几句里。

  因此 v2 改为「段落级共现 + 标题锚定」：
    - 标题判定：题名含该病名 → 该文献是本病专论，权重最高
    - 段落判定：该段出现病名 → 段内所有症状词计入
    - 邻近判定：病名句 + 后续 2 句 → 计入，权重次之
  同时记录「共现段落数」作为证据强度。
"""
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

TEXT_DIR = r"C:\Users\ASUS\Downloads\AIC-文献\文本"
REFS = r"E:\harness\aic\refs.json"
OUT_DIR = r"E:\harness\aic\kb"
os.makedirs(OUT_DIR, exist_ok=True)

DISEASES = json.load(io.open(r"E:\harness\aic\disease_dict.json", encoding="utf-8"))
SYMPTOMS = json.load(io.open(r"E:\harness\aic\symptom_dict.json", encoding="utf-8"))

DRUG_HINTS = ["疫苗", "免疫", "消毒", "抗生素", "抗菌药", "中草药", "益生菌", "药敏",
              "休药期", "禁用", "恩诺沙星", "替米考星", "氟苯尼考", "阿莫西林",
              "头孢", "泰乐菌素", "多西环素", "磺胺", "黏菌素", "金霉素", "土霉素",
              "林可霉素", "泰妙菌素", "支原净", "氟喹诺酮"]

AGE_WORDS = ["哺乳仔猪", "新生仔猪", "保育猪", "断奶仔猪", "仔猪", "育肥猪",
             "生长育肥猪", "母猪", "妊娠母猪", "种猪", "后备母猪", "公猪", "成年猪"]
AGE_NUM = re.compile(r"\d+\s*[～~\-至]\s*\d+\s*(?:周龄|日龄|月龄)|新生仔猪|\d+\s*日龄内|\d+\s*周龄")

SEP = "=" * 60


def split_sentences(text):
    return [s.strip() for s in re.split(r"(?<=[。；！？])", text) if len(s.strip()) >= 6]


def split_paragraphs(text):
    """段落 = 连续的非空行块；若整篇没有空行，退化为每 6 行一段。"""
    raw = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    paras = []
    for b in raw:
        lines = [ln for ln in b.split("\n") if ln.strip()]
        if len(lines) <= 8:
            paras.append(" ".join(lines))
        else:
            for i in range(0, len(lines), 6):
                paras.append(" ".join(lines[i:i + 6]))
    return paras


# ---------- 载入 ----------
refs = {r["no"]: r for r in json.load(io.open(REFS, encoding="utf-8"))}
docs = {}
for f in sorted(glob.glob(os.path.join(TEXT_DIR, "*.txt"))):
    no = int(os.path.basename(f)[:2])
    raw = io.open(f, encoding="utf-8").read()
    docs[no] = {
        "body": raw.split(SEP, 1)[-1],
        "title": refs.get(no, {}).get("title", ""),
        "source": refs.get(no, {}).get("source", ""),
        "year": refs.get(no, {}).get("year", ""),
    }
print(f"载入语料 {len(docs)} 篇\n")

# ---------- 抽取 ----------
records = {}
for dname, aliases in DISEASES.items():
    rec = {"disease": dname, "aliases": [a for a in aliases if a != dname],
           "sym_para": Counter(), "sym_title": Counter(), "sym_near": Counter(),
           "evidence": defaultdict(list), "age": Counter(), "drugs": Counter(),
           "docs": set(), "title_docs": set(), "para_docs": defaultdict(set)}

    for no, d in docs.items():
        body, title = d["body"], d["title"]
        in_title = any(a in title for a in aliases)
        if in_title:
            rec["title_docs"].add(no)
            rec["docs"].add(no)

        paras = split_paragraphs(body)
        for para in paras:
            if not any(a in para for a in aliases):
                continue
            rec["docs"].add(no)
            for std, words in SYMPTOMS.items():
                if any(w in para for w in words):
                    rec["sym_para"][std] += 1
                    rec["para_docs"][std].add(no)
                    if len(rec["evidence"][std]) < 2:
                        for s in split_sentences(para):
                            if any(w in s for w in words):
                                rec["evidence"][std].append((no, s[:120]))
                                break
            for a in AGE_WORDS:
                if a in para:
                    rec["age"][a] += 1
            for m in AGE_NUM.findall(para):
                rec["age"][m.strip()] += 1
            for g in DRUG_HINTS:
                if g in para:
                    rec["drugs"][g] += para.count(g)

        # 标题锚定：本病专论，则全文症状都算（权重最高）
        if in_title:
            whole = " ".join(paras)
            for std, words in SYMPTOMS.items():
                if any(w in whole for w in words):
                    rec["sym_title"][std] += 1
                    rec["para_docs"][std].add(no)

        # 邻近句：病名句 + 后 2 句
        sents = split_sentences(body)
        for i, s in enumerate(sents):
            if any(a in s for a in aliases):
                near = " ".join(sents[i:i + 3])
                for std, words in SYMPTOMS.items():
                    if any(w in near for w in words):
                        rec["sym_near"][std] += 1
    records[dname] = rec

# ---------- 打分与筛选 ----------
out = []
for dname, rec in records.items():
    all_sym = set(rec["sym_para"]) | set(rec["sym_title"]) | set(rec["sym_near"])
    if not all_sym:
        continue
    scored = []
    for s in all_sym:
        t, p, n = rec["sym_title"].get(s, 0), rec["sym_para"].get(s, 0), rec["sym_near"].get(s, 0)
        score = t * 3 + p * 2 + n * 1
        ndoc = len(rec["para_docs"].get(s, set()))
        ndocs_total = max(len(rec["docs"]), 1)
        cov = ndoc / ndocs_total
        # 置信度改为「疾病相对覆盖率」，避免要求绝对篇数（对只有 3 篇支持的地方性病名不公平）
        if (cov >= 0.5 and score >= 3) or score >= 12:
            conf = "强"
        elif cov >= 0.25 or score >= 5:
            conf = "中"
        else:
            conf = "弱"
        scored.append((s, score, ndoc, conf))
    scored.sort(key=lambda x: (-x[1], -x[2]))
    rec["_scored"] = scored

    # 证据回填：标题锚定命中的症状可能没有段落证据，从全篇补一句
    for s, _, _, _ in scored:
        if rec["evidence"].get(s):
            continue
        words = SYMPTOMS[s]
        done = False
        for no in sorted(rec["title_docs"]):
            for para in split_paragraphs(docs[no]["body"]):
                if any(w in para for w in words):
                    for sent in split_sentences(para):
                        if any(w in sent for w in words):
                            rec["evidence"][s].append((no, sent[:120]))
                            done = True
                            break
                if done:
                    break
            if done:
                break
    out.append((dname, rec))

out.sort(key=lambda x: (-len(x[1]["title_docs"]), -sum(s[1] for s in x[1]["_scored"])))

# ---------- 输出 TSV ----------
rows = [["疾病", "别名", "支持文献", "专论文献", "症状数",
         "强证据症状", "中证据症状", "弱证据症状", "易感日龄线索", "用药/防治线索"]]
for dname, rec in out:
    strong = [s for s, _, _, c in rec["_scored"] if c == "强"]
    mid = [s for s, _, _, c in rec["_scored"] if c == "中"]
    weak = [s for s, _, _, c in rec["_scored"] if c == "弱"]
    age = "、".join(a for a, _ in rec["age"].most_common(5))
    drugs = "、".join(g for g, _ in rec["drugs"].most_common(8))
    rows.append([dname, "/".join(rec["aliases"]), len(rec["docs"]), len(rec["title_docs"]),
                 len(rec["_scored"]), "、".join(strong), "、".join(mid), "、".join(weak), age, drugs])
io.open(os.path.join(OUT_DIR, "疾病知识库候选.tsv"), "w", encoding="utf-8").write(
    "\n".join("\t".join(str(x) for x in r) for r in rows))

# ---------- 输出 Markdown（带证据） ----------
n_strong = sum(1 for _, r in out for s in r["_scored"] if s[3] == "强")
n_mid = sum(1 for _, r in out for s in r["_scored"] if s[3] == "中")
n_weak = sum(1 for _, r in out for s in r["_scored"] if s[3] == "弱")

# 哪些文献是多病综述（含 3 种以上疾病）——这类文献的共现最不可靠
multi = []
for no, d in docs.items():
    cnt = sum(1 for aliases in DISEASES.values() if any(a in d["body"] for a in aliases))
    if cnt >= 5:
        multi.append((no, cnt, d["title"][:34]))
multi.sort(key=lambda x: -x[1])

md = ["# 猪病知识库候选表（机器抽取，待人工核对）", "",
      f"语料 {len(docs)} 篇　|　识别疾病 **{len(out)} 种**　|　症状关联 {n_strong + n_mid + n_weak} 条"
      f"（强 {n_strong} / 中 {n_mid} / 弱 {n_weak}）", "",
      "---", "",
      "## ⚠️ 先读这一段：这份表的能力边界",
      "",
      "这是**规则共现抽取**的结果，不是诊断结论。已知的三类错误来源：",
      "",
      "1. **多病综述文献污染**：一篇文章同时讲 5 种以上疾病时，"
      "段落内的症状会被错误挂到同段提到的其他病上。本批语料中这类文献有：",
      "",
      "   | 文献 | 涉及疾病数 | 题名 |",
      "   |---|---|---|",
      *[f"   | {no} | {c} | {t} |" for no, c, t in multi[:8]],
      "",
      "2. **置信度对「多文献提及但单篇专论」的病失真**：例如猪瘟出现在 10 篇文献里，"
      "但症状只来自 1 篇专论，覆盖率被稀释后全被判为「弱」。"
      "**这类情况要以专论文献为准，不要因为标了「弱」就删掉。**",
      "",
      "3. **症状词表仍是机器词典**，可能漏掉方言/非常规表述。",
      "",
      "## 核对方法（建议按这个顺序）",
      "",
      "| 步骤 | 做什么 | 判断依据 |",
      "|---|---|---|",
      "| ① | 先看**专论文献数 ≥1** 的疾病 | 该类病有独立文献，抽取最可靠 |",
      "| ② | 逐条看「强证据」症状 | 保留符合临床的，删掉明显误匹配 |",
      "| ③ | 「中证据」症状逐条判断 | 多数可用，重点是去掉跨病污染项 |",
      "| ④ | 「弱证据」不要一刀切 | 结合专论文献原文判断 |",
      "| ⑤ | 补上机器漏掉的典型症状 | 以你的专业知识为准，机器只是辅助 |",
      "",
      "**核心原则：这部分知识必须以你的专业判断为准。**"
      "机器抽取的价值是「快速把 24.9 万字里的候选信息摊开、并附上原文出处」，"
      "省掉你翻 40 篇 PDF 的时间；但哪条对、哪条错，得你来定。",
      "",
      "---", "",
      "## 总览", "",
      "| 疾病 | 支持文献 | 专论 | 症状数 | 强证据症状 | 中证据症状 |", "|---|---|---|---|---|---|"]
for dname, rec in out:
    strong = "、".join(s for s, _, _, c in rec["_scored"] if c == "强") or "—"
    mid = "、".join(s for s, _, _, c in rec["_scored"] if c == "中") or "—"
    md.append(f"| {dname} | {len(rec['docs'])} | {len(rec['title_docs'])} | {len(rec['_scored'])} | {strong} | {mid} |")
md.append("")

for dname, rec in out:
    md.append(f"## {dname}")
    if rec["aliases"]:
        md.append(f"*别名*：{'、'.join(rec['aliases'])}")
    md.append(f"*支持文献*：{len(rec['docs'])} 篇，其中本病专论 {len(rec['title_docs'])} 篇")
    if rec["age"]:
        md.append(f"*易感日龄线索*：{'、'.join(a for a, _ in rec['age'].most_common(5))}")
    if rec["drugs"]:
        md.append(f"*用药/防治线索*：{'、'.join(g for g, _ in rec['drugs'].most_common(8))}")
    md.append("")
    md.append("| 症状（标准词） | 置信度 | 权重分 | 证据文献数 | 原文证据 |")
    md.append("|---|---|---|---|---|")
    for s, score, ndoc, conf in rec["_scored"]:
        evs = rec["evidence"].get(s, [])
        ev = " <br> ".join(f"[{n}] {t}" for n, t in evs) if evs else "—"
        md.append(f"| {s} | {conf} | {score} | {ndoc} | {ev} |")
    md.append("")
io.open(os.path.join(OUT_DIR, "疾病知识库候选.md"), "w", encoding="utf-8").write("\n".join(md))

# ---------- 控制台摘要 ----------
print("=" * 78)
print(f"{'疾病':<16}{'文献':>4}{'专论':>4}{'症状':>4}  强证据症状")
print("-" * 78)
for dname, rec in out:
    strong = "、".join(s for s, _, _, c in rec["_scored"] if c == "强")[:52]
    print(f"{dname:<16}{len(rec['docs']):>4}{len(rec['title_docs']):>4}{len(rec['_scored']):>4}  {strong}")
print("=" * 78)
print(f"共 {len(out)} 种疾病；输出：\n  {os.path.join(OUT_DIR, '疾病知识库候选.tsv')}"
      f"\n  {os.path.join(OUT_DIR, '疾病知识库候选.md')}")
