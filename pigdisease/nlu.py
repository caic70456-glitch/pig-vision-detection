# -*- coding: utf-8 -*-
"""口语症状归一化（NLU 层）。

两条路线：
  A 规则引擎（默认，离线可用）：同义词匹配 + 否定/排除处理 + 日龄抽取 + 病程抽取
  B 大模型增强（可选）：设置环境变量 PIGDISEASE_LLM=1 且提供 OPENAI_API_KEY 时启用，
    仅用于 A 方案没能识别的残句，把口语映射到标准症状词表。

设计要点：B 方案永远不能绕过 A 的白名单——LLM 只能从已知标准症状里选，
不允许自创症状名，否则会把不可控的概念注进诊断链路。
"""
import json
import os
import re
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")

with open(os.path.join(DATA_DIR, "symptom_dict.json"), encoding="utf-8") as fh:
    SYMPTOM_DICT = json.load(fh)

# 反查：匹配词 -> 标准症状。长词优先，避免「水样腹泻」被「腹泻」抢先匹配
WORD2SYM = []
for std, words in SYMPTOM_DICT.items():
    for w in words:
        WORD2SYM.append((w, std))
WORD2SYM.sort(key=lambda x: -len(x[0]))

STANDARD_SYMPTOMS = sorted(SYMPTOM_DICT)

# 否定词：出现在症状词前若干字内，则视为「不存在该症状」
NEG_PATTERNS = ["无", "没有", "不", "未", "未见", "非", "排除", "不出现", "无明显", "无异常"]

# 日龄分组
AGE_GROUPS = {
    "新生仔猪": ["新生仔猪", "初生", "1日龄", "2日龄", "3日龄", "一周内", "7日龄内", "7 日龄内"],
    "哺乳仔猪": ["哺乳仔猪", "哺乳期", "吃奶"],
    "保育猪": ["保育猪", "断奶仔猪", "断奶后", "保育期"],
    "育肥猪": ["育肥猪", "生长育肥猪", "生长猪", "中大猪", "出栏前"],
    "母猪": ["母猪", "妊娠母猪", "经产母猪", "后备母猪", "产房"],
    "公猪": ["公猪", "种公猪"],
    "成年猪": ["成年猪", "种猪"],
}

AGE_NUM_PAT = re.compile(r"(\d+)\s*[～~\-至到]\s*(\d+)\s*(日龄|周龄|月龄)")
AGE_SINGLE_PAT = re.compile(r"(\d+)\s*(日龄|周龄|月龄)")

DURATION_PAT = re.compile(r"(\d+)\s*(天|日|小时|h|周)")


def _is_negated(text, pos, window=6):
    """判断 text 中 pos 处的症状词是否被否定。"""
    seg = text[max(0, pos - window):pos]
    return any(n in seg for n in NEG_PATTERNS)


def rule_extract(text):
    """规则抽取。返回 (命中症状集合, 命中片段, 日龄线索, 病程线索)。

    去重策略：长词优先匹配并占用字符位；同一标准症状只记一次，
    避免「红斑疹块」被「红斑」「疹块」两个词重复计入导致虚高。
    """
    text = (text or "").strip()
    spans = []
    used = [False] * len(text)

    for word, std in WORD2SYM:
        start = 0
        while True:
            i = text.find(word, start)
            if i < 0:
                break
            start = i + len(word)
            if any(used[i:i + len(word)]):
                continue
            if _is_negated(text, i):
                continue
            for j in range(i, min(i + len(word), len(used))):
                used[j] = True
            spans.append((std, word))

    # 同一标准症状只保留最长的那次匹配
    best = {}
    for std, w in spans:
        if std not in best or len(w) > len(best[std]):
            best[std] = w
    found = sorted(best)
    spans = [(std, best[std]) for std in found]

    ages = []
    for grp, kws in AGE_GROUPS.items():
        if any(k in text for k in kws):
            ages.append(grp)
    for m in AGE_NUM_PAT.finditer(text):
        ages.append(f"{m.group(1)}-{m.group(2)}{m.group(3)}")
    for m in AGE_SINGLE_PAT.finditer(text):
        ages.append(f"{m.group(1)}{m.group(2)}")

    dur = None
    m = DURATION_PAT.search(text)
    if m:
        dur = m.group(0)

    return found, spans, sorted(set(ages)), dur


def llm_extract(text, candidates):
    """B 方案：让大模型把残句映射到已知标准症状。失败返回空列表。"""
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("PIGDISEASE_LLM_MODEL", "gpt-4o-mini")
    if not api_key:
        return [], "未配置 OPENAI_API_KEY"

    prompt = (
        "你是兽医助手。请从下面这段养殖户口语描述中，抽取符合给定词表的临床症状。\n"
        f"只能从这个词表里选，不得自创：{json.dumps(STANDARD_SYMPTOMS, ensure_ascii=False)}\n"
        '只输出 JSON：{"symptoms": ["标准症状1", ...]}\n'
        f"描述：{text}"
    )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        picked = json.loads(content).get("symptoms", [])
        # 白名单过滤：LLM 不得引入词表外的症状
        return [s for s in picked if s in SYMPTOM_DICT], None
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as e:
        return [], f"LLM 调用失败: {e}"


def normalize(text, use_llm=None):
    """对外主接口。返回结构化解析结果。"""
    if use_llm is None:
        use_llm = os.environ.get("PIGDISEASE_LLM") == "1"

    symptoms, spans, ages, dur = rule_extract(text)
    llm_used = False
    llm_note = None

    if use_llm:
        llm_syms, err = llm_extract(text, symptoms)
        if err:
            llm_note = err
        elif llm_syms:
            added = [s for s in llm_syms if s not in symptoms]
            if added:
                symptoms = sorted(set(symptoms) | set(added))
                llm_used = True

    return {
        "raw": text,
        "symptoms": symptoms,
        "spans": spans,
        "ages": ages,
        "duration": dur,
        "llm_used": llm_used,
        "llm_note": llm_note,
    }


if __name__ == "__main__":
    tests = [
        "仔猪拉稀，黄白色的，两天了，不吃食",
        "育肥猪咳嗽喘气，体温升高到41度，精神沉郁",
        "母猪流产，产死胎，没有腹泻",
        "7日龄内新生仔猪呕吐、水样腹泻，脱水严重",
        "猪皮肤有红斑疹块，关节肿胀跛行",
    ]
    for t in tests:
        r = normalize(t)
        print(f"输入: {t}")
        print(f"  症状: {'、'.join(r['symptoms']) or '（无）'}")
        print(f"  匹配: {[f'{s}<-{w}' for s, w in r['spans']]}")
        print(f"  日龄: {r['ages']}   病程: {r['duration']}")
        print()
