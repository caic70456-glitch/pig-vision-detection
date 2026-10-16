# -*- coding: utf-8 -*-
"""把疾病词表与症状词表导出为独立 JSON，方便非程序员直接编辑扩充。"""
import ast
import io
import json
import re

src = io.open(r"E:\harness\aic\build_kb.py", encoding="utf-8").read()


def grab(name):
    m = re.search(rf"^{name} = (\{{.*?^\}})", src, re.S | re.M)
    if not m:
        raise SystemExit(f"找不到 {name}")
    return ast.literal_eval(m.group(1))


diseases = grab("DISEASES")
symptoms = grab("SYMPTOMS")

io.open(r"E:\harness\aic\disease_dict.json", "w", encoding="utf-8").write(
    json.dumps(diseases, ensure_ascii=False, indent=1))
io.open(r"E:\harness\aic\symptom_dict.json", "w", encoding="utf-8").write(
    json.dumps(symptoms, ensure_ascii=False, indent=1))

print(f"disease_dict.json: {len(diseases)} 种疾病，{sum(len(v) for v in diseases.values())} 个匹配词")
print(f"symptom_dict.json: {len(symptoms)} 个标准症状，{sum(len(v) for v in symptoms.values())} 个同义词")
