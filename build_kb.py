# -*- coding: utf-8 -*-
"""从 40 篇文献抽取「疾病 → 症状 / 易感日龄 / 用药」候选知识库。

设计原则：
  - 每条症状关联都带【出处文档编号】和【原文证据句】，供人工复核
  - 不做任何推理补全，只做「共现」统计；判断留给人和后续的加权打分
  - 输出 TSV（便于核对）+ Markdown（便于阅读）
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
OUT_DIR = r"E:\harness\aic\kb"
os.makedirs(OUT_DIR, exist_ok=True)

# ---------- 疾病词表（别名分组，同组视为同一疾病） ----------
DISEASES = {
    "猪流行性腹泻": ["猪流行性腹泻", "流行性腹泻", "PEDV", "PED"],
    "猪传染性胃肠炎": ["猪传染性胃肠炎", "传染性胃肠炎", "TGEV", "TGE"],
    "猪轮状病毒腹泻": ["轮状病毒"],
    "猪瘟": ["猪瘟", "古典猪瘟", "CSF"],
    "非洲猪瘟": ["非洲猪瘟", "ASFV", "ASF"],
    "猪繁殖与呼吸综合征": ["猪繁殖与呼吸综合征", "蓝耳病", "PRRSV", "PRRS"],
    "猪圆环病毒病": ["猪圆环病毒", "圆环病毒", "PCV2", "PCV"],
    "猪支原体肺炎": ["猪支原体肺炎", "支原体肺炎", "猪气喘病", "气喘病", "猪肺炎支原体", "Mhp"],
    "猪沙门氏菌病": ["猪沙门氏菌", "沙门氏菌", "仔猪副伤寒", "副伤寒"],
    "副猪嗜血杆菌病": ["副猪嗜血杆菌", "格拉瑟病"],
    "猪链球菌病": ["猪链球菌", "链球菌"],
    "猪大肠杆菌病": ["大肠杆菌", "仔猪白痢", "仔猪黄痢", "仔猪水肿病", "水肿病"],
    "猪增生性肠炎": ["增生性肠炎", "回肠炎", "胞内劳森菌"],
    "猪痢疾": ["猪痢疾", "猪血痢", "密螺旋体"],
    "猪丹毒": ["猪丹毒", "红斑丹毒丝菌"],
    "猪肺疫": ["猪肺疫", "巴氏杆菌", "多杀性巴氏杆菌"],
    "猪传染性胸膜肺炎": ["传染性胸膜肺炎", "胸膜肺炎", "放线杆菌"],
    "猪流感": ["猪流感", "猪流行性感冒"],
    "口蹄疫": ["口蹄疫", "FMD"],
    "猪伪狂犬病": ["伪狂犬", "PRV"],
    "猪细小病毒病": ["猪细小病毒", "细小病毒"],
    "猪乙型脑炎": ["乙型脑炎", "流行性乙型脑炎"],
    "猪弓形虫病": ["弓形虫"],
    "猪球虫病": ["球虫"],
    "猪蛔虫病": ["蛔虫"],
    "猪疥螨病": ["疥螨"],
    "猪附红细胞体病": ["附红细胞体"],
    "猪葡萄球菌病": ["葡萄球菌", "渗出性皮炎"],
    "猪霉菌毒素中毒": ["霉菌毒素", "霉变饲料", "黄曲霉毒素"],
}

# ---------- 症状词表（标准词 → 同义/口语表达） ----------
SYMPTOMS = {
    "腹泻": ["腹泻", "拉稀", "下痢", "稀粪", "水样便"],
    "呕吐": ["呕吐", "吐奶"],
    "食欲减退": ["食欲减退", "食欲下降", "采食量下降", "厌食"],
    "食欲废绝": ["食欲废绝", "不吃食", "不食", "废食"],
    "粪便异常-黄白": ["黄白色", "黄色稀粪", "灰白色", "灰黄色", "白色稀粪"],
    "粪便异常-血便": ["血便", "带血", "血痢", "血色"],
    "脱水": ["脱水"],
    "消瘦": ["消瘦", "掉膘"],
    "生长迟缓": ["生长迟缓", "生长缓慢", "增重下降", "僵猪", "发育不良"],
    "咳嗽": ["咳嗽", "干咳", "湿咳", "深咳"],
    "喘气": ["喘气", "气喘", "呼吸急促", "腹式呼吸"],
    "呼吸困难": ["呼吸困难", "张口呼吸", "犬坐", "窒息"],
    "喷嚏/鼻液": ["喷嚏", "鼻液", "流鼻涕", "鼻腔分泌物", "脓性鼻液", "浆液性鼻液"],
    "发热": ["体温升高", "发热", "高热", "发烧", "体温达"],
    "精神沉郁": ["精神沉郁", "精神不振", "萎靡", "嗜睡", "不愿走动"],
    "被毛粗乱": ["被毛粗乱", "毛乱", "被毛无光"],
    "皮肤发红/发绀": ["皮肤发红", "发绀", "皮肤发紫", "紫斑", "皮下紫斑", "皮肤苍白"],
    "出血点/红斑": ["出血点", "红斑", "疹块", "出血斑"],
    "关节肿胀/跛行": ["关节肿胀", "跛行", "关节炎", "站立困难", "卧地不起"],
    "神经症状": ["抽搐", "共济失调", "转圈", "角弓反张", "瘫痪", "惊厥", "神经症状", "麻痹"],
    "淋巴结肿大": ["淋巴结肿大", "淋巴结肿胀"],
    "流产": ["流产"],
    "死胎/木乃伊胎": ["死胎", "木乃伊胎", "死产"],
    "产弱仔": ["弱仔", "产弱"],
    "繁殖障碍": ["返情", "屡配不孕", "不孕", "繁殖障碍"],
    "眼结膜潮红": ["眼结膜潮红", "结膜潮红", "眼结膜充血"],
    "黄疸/贫血": ["黄疸", "贫血"],
    "水肿": ["水肿", "眼睑水肿"],
    "口腔/蹄部水疱": ["水疱", "水泡", "蹄部溃烂", "口腔溃疡"],
}

DRUG_HINTS = ["疫苗", "免疫", "消毒", "抗生素", "抗菌药", "中草药", "益生菌", "药敏",
              "休药期", "禁用", "恩诺沙星", "替米考星", "氟苯尼考", "阿莫西林",
              "头孢", "泰乐菌素", "多西环素", "磺胺", "黏菌素", "金霉素", "土霉素",
              "林可霉素", "泰妙菌素", "支原净"]

AGE_PAT = re.compile(r"[^。；\n]{0,18}(哺乳仔猪|保育猪|断奶仔猪|仔猪|育肥猪|生长育肥猪|母猪|种猪|后备母猪|公猪)[^。；\n]{0,18}")
NUM_AGE_PAT = re.compile(r"(\d+\s*[～~\-至]\s*\d+\s*(?:周龄|日龄|月龄)|新生仔猪|\d+\s*日龄内|\d+\s*周龄)")


def sentences_of(text):
    """按中文句末标点切句，并保留较长句内的分句。"""
    parts = re.split(r"(?<=[。；！？])", text)
    return [p.strip() for p in parts if len(p.strip()) >= 8]


# ---------- 读取语料 ----------
docs = {}
for f in sorted(glob.glob(os.path.join(TEXT_DIR, "*.txt"))):
    no = os.path.basename(f)[:2]
    raw = io.open(f, encoding="utf-8").read()
    body = raw.split("=" * 60, 1)[-1]
    docs[no] = body

print(f"载入语料 {len(docs)} 篇\n")

# ---------- 抽取 ----------
records = {}
symptom_docs = defaultdict(set)      # disease -> symptom -> {doc}
for dname, aliases in DISEASES.items():
    rec = {"disease": dname, "aliases": [], "symptoms": {}, "age": Counter(),
           "drugs": Counter(), "docs": set(), "evidence": defaultdict(list)}
    for no, body in docs.items():
        sents = sentences_of(body)
        hit_sents = [s for s in sents if any(a in s for a in aliases)]
        if not hit_sents:
            continue
        rec["docs"].add(no)
        joined = " ".join(hit_sents)
        for std, words in SYMPTOMS.items():
            for w in words:
                if w in joined:
                    rec["symptoms"][std] = rec["symptoms"].get(std, 0) + joined.count(w)
                    symptom_docs[dname].add(std)
                    if len(rec["evidence"][std]) < 2:
                        for s in hit_sents:
                            if w in s:
                                rec["evidence"][std].append((no, s[:110]))
                                break
        for a in AGE_PAT.findall(joined):
            rec["age"][a] += 1
        for m in NUM_AGE_PAT.findall(joined):
            rec["age"][m.strip()] += 1
        for g in DRUG_HINTS:
            if g in joined:
                rec["drugs"][g] += joined.count(g)
    records[dname] = rec

# 只要症状维度有内容的疾病才纳入
kept = {k: v for k, v in records.items() if v["symptoms"]}
dropped = [k for k in records if k not in kept]

# ---------- 输出 ----------
rows = [["疾病", "别名", "支持文献数", "文献编号", "症状维度数", "症状(标准词: 证据文献数)",
         "易感日龄线索", "用药/防治线索"]]
for dname, rec in sorted(kept.items(), key=lambda x: -len(x[1]["symptoms"])):
    aliases = [a for a in DISEASES[dname] if a != dname]
    sym = []
    for s, c in sorted(rec["symptoms"].items(), key=lambda x: -x[1]):
        nd = len({e[0] for e in rec["evidence"].get(s, [])})
        sym.append(f"{s}({nd})")
    age = "、".join([a for a, _ in rec["age"].most_common(4)]) if rec["age"] else ""
    drugs = "、".join([g for g, _ in rec["drugs"].most_common(6)]) if rec["drugs"] else ""
    rows.append([dname, "/".join(aliases), len(rec["docs"]), ",".join(sorted(rec["docs"])),
                 len(rec["symptoms"]), "；".join(sym), age, drugs])

io.open(os.path.join(OUT_DIR, "疾病知识库候选.tsv"), "w", encoding="utf-8").write(
    "\n".join("\t".join(str(x) for x in r) for r in rows))

# Markdown：带证据句，便于人工判断
md = ["# 猪病知识库候选表（供人工核对）", "",
      f"语料：{len(docs)} 篇文献　|　识别出疾病 {len(kept)} 种（症状维度可用）　|　",
      f"仅提及但症状信息不足而未纳入：{'、'.join(dropped) if dropped else '无'}", "",
      "> **核对方法**：看「症状」列是否符合你的专业判断，删掉误匹配的，补上漏掉的。",
      "> 「证据」给的是原文句子，括号里是文献编号，可对照 `Downloads\\AIC-文献\\` 里的原文。", ""]

for dname, rec in sorted(kept.items(), key=lambda x: -len(x[1]["symptoms"])):
    md.append(f"## {dname}")
    aliases = [a for a in DISEASES[dname] if a != dname]
    if aliases:
        md.append(f"*别名*：{'、'.join(aliases)}　")
    md.append(f"*支持文献*：{len(rec['docs'])} 篇（编号 {', '.join(sorted(rec['docs']))}）")
    if rec["age"]:
        md.append(f"*易感日龄线索*：{'、'.join(a for a, _ in rec['age'].most_common(5))}")
    if rec["drugs"]:
        md.append(f"*用药/防治线索*：{'、'.join(g for g, _ in rec['drugs'].most_common(6))}")
    md.append("")
    md.append("| 症状（标准词） | 证据文献数 | 原文证据 |")
    md.append("|---|---|---|")
    for s, c in sorted(rec["symptoms"].items(), key=lambda x: -x[1]):
        evs = rec["evidence"].get(s, [])
        ev_txt = " <br> ".join(f"[{n}] {t}" for n, t in evs) if evs else "—"
        nd = len({e[0] for e in evs})
        md.append(f"| {s} | {nd} | {ev_txt} |")
    md.append("")

io.open(os.path.join(OUT_DIR, "疾病知识库候选.md"), "w", encoding="utf-8").write("\n".join(md))

print("=" * 70)
print(f"识别疾病 {len(kept)} 种；症状信息不足未纳入 {len(dropped)} 种")
print(f"输出：\n  {os.path.join(OUT_DIR, '疾病知识库候选.tsv')}\n  {os.path.join(OUT_DIR, '疾病知识库候选.md')}\n")
print(f"{'疾病':<18}{'文献数':>5}{'症状数':>7}   主要症状")
for dname, rec in sorted(kept.items(), key=lambda x: -len(x[1]["symptoms"]))[:20]:
    top = "、".join([s for s, _ in sorted(rec["symptoms"].items(), key=lambda x: -x[1])[:6]])
    print(f"{dname:<18}{len(rec['docs']):>5}{len(rec['symptoms']):>7}   {top}")
if dropped:
    print(f"\n未纳入：{'、'.join(dropped)}")
