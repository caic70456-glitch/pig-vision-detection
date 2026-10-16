# -*- coding: utf-8 -*-
"""快速评估文献语料的可用性：疾病覆盖面、症状词覆盖、药物提及。

不产生知识库，只回答一个问题：这 40 篇够不够撑起一个猪病诊断知识库？
"""
import glob
import io
import os
import re
import sys
from collections import Counter, defaultdict

# Windows 控制台默认 GBK，含 ✓ 等字符会崩，统一切到 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TEXT_DIR = r"C:\Users\ASUS\Downloads\AIC-文献\文本"

# 猪病名称词表（覆盖常见病毒性/细菌性/寄生虫性/营养代谢病）
DISEASES = [
    "猪流行性腹泻", "流行性腹泻", "传染性胃肠炎", "轮状病毒", "猪瘟", "非洲猪瘟",
    "猪蓝耳病", "蓝耳病", "繁殖与呼吸综合征", "猪圆环病毒", "圆环病毒", "支原体肺炎",
    "气喘病", "猪沙门氏菌", "沙门氏菌", "副猪嗜血杆菌", "链球菌", "大肠杆菌",
    "仔猪白痢", "仔猪黄痢", "水肿病", "回肠炎", "增生性肠炎", "猪丹毒", "猪肺疫",
    "巴氏杆菌", "口蹄疫", "伪狂犬", "细小病毒", "乙型脑炎", "猪痢疾", "密螺旋体",
    "弓形虫", "球虫", "蛔虫", "疥螨", "附红细胞体", "猪流感", "胸膜肺炎",
    "放线杆菌", "葡萄球菌", "渗出性皮炎", "破伤风", "炭疽", "布氏杆菌",
]

# 症状/体征词表（用于诊断匹配的输入维度）
SYMPTOMS = {
    "消化": ["腹泻", "拉稀", "下痢", "呕吐", "食欲减退", "食欲废绝", "不吃", "便秘",
             "腹胀", "脱水", "粪便", "水样", "黄白", "灰白", "血便", "消化不良"],
    "呼吸": ["咳嗽", "喘气", "呼吸急促", "呼吸困难", "腹式呼吸", "喷嚏", "流鼻涕",
             "鼻液", "张口呼吸", "犬坐"],
    "全身": ["发热", "体温升高", "高烧", "精神沉郁", "嗜睡", "消瘦", "生长迟缓",
             "被毛粗乱", "皮肤发红", "皮肤发绀", "发绀", "贫血", "黄疸", "抽搐",
             "卧地不起", "跛行", "关节肿胀", "淋巴结肿大"],
    "繁殖": ["流产", "死胎", "木乃伊胎", "返情", "不孕", "产弱仔", "少乳", "无乳"],
    "皮肤": ["皮疹", "红斑", "紫斑", "出血点", "结痂", "脱毛", "瘙痒", "水疱", "溃烂"],
    "神经": ["共济失调", "转圈", "角弓反张", "瘫痪", "惊厥", "麻痹"],
}

# 药物/防治词
DRUGS = ["疫苗", "免疫", "消毒", "抗生素", "抗菌药", "中草药", "益生菌", "休药期",
         "禁用", "恩诺沙星", "替米考星", "氟苯尼考", "阿莫西林", "头孢", "泰乐菌素",
         "多西环素", "磺胺", "硫酸黏菌素", "金霉素", "土霉素", "林可霉素"]

files = sorted(glob.glob(os.path.join(TEXT_DIR, "*.txt")))
print(f"文本文件：{len(files)} 个\n")

doc_diseases = defaultdict(set)
doc_symptoms = defaultdict(set)
doc_drugs = defaultdict(set)
disease_counter = Counter()
symptom_counter = Counter()
drug_counter = Counter()
symptom_cat_counter = Counter()

for f in files:
    no = os.path.basename(f)[:2]
    txt = io.open(f, encoding="utf-8").read()
    for d in DISEASES:
        if d in txt:
            doc_diseases[no].add(d)
            disease_counter[d] += txt.count(d)
    for cat, words in SYMPTOMS.items():
        for w in words:
            if w in txt:
                doc_symptoms[no].add(w)
                symptom_counter[w] += txt.count(w)
                symptom_cat_counter[cat] += 1
    for g in DRUGS:
        if g in txt:
            doc_drugs[no].add(g)
            drug_counter[g] += txt.count(g)

print("=" * 66)
print(f"疾病名称：出现 {len(disease_counter)} 种，覆盖 {len(doc_diseases)} 篇文献")
print("  高频疾病 Top 15：")
for d, c in disease_counter.most_common(15):
    print(f"    {d:<16} 出现 {c:>4} 次，涉及 {sum(1 for v in doc_diseases.values() if d in v):>2} 篇")
print()
print(f"症状词：命中 {len(symptom_counter)} 个，覆盖 {len(doc_symptoms)} 篇文献")
print(f"  按类别命中词数：{dict(symptom_cat_counter)}")
print("  高频症状 Top 15：")
for s, c in symptom_counter.most_common(15):
    print(f"    {s:<12} 出现 {c:>4} 次")
print()
print(f"防治/药物词：命中 {len(drug_counter)} 个，覆盖 {len(doc_drugs)} 篇")
print("  高频词 Top 12：")
for g, c in drug_counter.most_common(12):
    print(f"    {g:<12} 出现 {c:>4} 次")

print("=" * 66)
print("结论判断：")
ok_disease = len(disease_counter) >= 20
ok_symptom = len(symptom_counter) >= 30
ok_multi = sum(1 for v in doc_diseases.values() if len(v) >= 3) >= 5
print(f"  疾病种类 ≥20 种        : {'✓' if ok_disease else '✗'} ({len(disease_counter)})")
print(f"  症状词 ≥30 个          : {'✓' if ok_symptom else '✗'} ({len(symptom_counter)})")
print(f"  有 ≥5 篇同时讲 3+ 种病  : {'✓' if ok_multi else '✗'}")
print(f"  → 语料{'足够' if (ok_disease and ok_symptom) else '不足'}支撑一个猪病诊断知识库")
