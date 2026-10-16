# -*- coding: utf-8 -*-
"""命令行演示：输入症状描述，输出候选疾病与依据。

用法：
    python cli.py                                  # 交互模式
    python cli.py "仔猪拉稀，黄白色的，两天了"       # 单次查询
    python cli.py --json "仔猪拉稀"                 # 输出 JSON
    python cli.py --disease 猪流行性腹泻             # 查看某病的知识库记录
    python cli.py --list                            # 列出知识库疾病
"""
import argparse
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
import safety  # noqa: E402

TIER_MARK = {"强": "★★★", "中": "★★", "弱": "★"}


def render(result, sources=None):
    p = result.get("parsed", {})
    lines = []
    lines.append("┌" + "─" * 74)
    lines.append(f"│ 输入：{p.get('raw', '')}")
    lines.append(f"│ 识别症状：{'、'.join(p.get('symptoms', [])) or '（无）'}")
    if p.get("ages"):
        lines.append(f"│ 日龄线索：{'、'.join(p['ages'])}")
    if p.get("duration"):
        lines.append(f"│ 病程：{p['duration']}")
    if p.get("llm_used"):
        lines.append("│ （已启用大模型辅助口语归一化）")
    if p.get("llm_note"):
        lines.append(f"│ （大模型未启用：{p['llm_note']}）")
    lines.append("└" + "─" * 74)

    cands = result.get("candidates", [])
    if not cands:
        lines.append("\n未匹配到候选疾病。" + (result.get("note") or ""))
        return "\n".join(lines)

    lines.append("")
    for i, c in enumerate(cands, 1):
        tag = "首选" if i == 1 else f"候选{i}"
        lines.append(f"【{tag}】{c['disease']}    置信度 {c['confidence']:.0%}"
                     f"    症状解释率 {c['explain']:.0%}")
        if c.get("aliases"):
            lines.append(f"        别名：{'、'.join(c['aliases'])}")
        lines.append(f"        命中症状（{len(c['matched'])} 个）：")
        for h in c["matched"]:
            mark = TIER_MARK.get(h["tier"], "")
            ev = ""
            if h.get("evidence"):
                no, sent = h["evidence"][0]
                src = (sources or {}).get(str(no), {})
                ev = f"　← [{no}] {src.get('source', '')}{src.get('year', '')}：{sent[:52]}…"
            lines.append(f"          {mark} {h['symptom']}（证据{h['tier']}，"
                         f"权重{h['contrib']}，{h['n_docs']}篇支持）{ev}")
        if c.get("unreported"):
            lines.append(f"        该病常见但本次未提及：{'、'.join(c['unreported'])}")
        if not c.get("title_docs"):
            lines.append("        ⚠ 知识库中缺少本病专论文献，症状依据较弱")
        lines.append("")

    if result.get("differential"):
        lines.append("鉴别要点：")
        for d in result["differential"]:
            a = "、".join(d["supports_top1"]) or "—"
            b = "、".join(d["supports_other"]) or "—"
            lines.append(f"  {d['pair']}：前者支持症状 {a}；后者支持症状 {b}")
        lines.append("")

    if result.get("note"):
        lines.append(f"提示：{result['note']}")
        lines.append("")

    s = result.get("safety", {})
    if s.get("blocked"):
        lines.append("【已阻断】")
        for b in s["blocked"]:
            lines.append(f"  ✗ {b['drug']}：{b['reason']}（{b['scope']}）")
    if s.get("drug_advice"):
        lines.append("【药物线索（非处方）】")
        for d in s["drug_advice"]:
            lines.append(f"  · {d['drug']}（{d['disease']}，{d['source']}）")
    for w in s.get("warnings", []):
        lines.append(f"⚠ {w}")
    if s.get("disclaimer"):
        lines.append("")
        lines.append(f"免责声明：{s['disclaimer']}")
    return "\n".join(lines)


def show_disease(name, dx):
    d = next((x for x in dx.diseases if x["name"] == name or name in x.get("aliases", [])), None)
    if not d:
        print(f"知识库中没有「{name}」。可用 --list 查看全部疾病。")
        return
    print(f"疾病：{d['name']}")
    if d.get("aliases"):
        print(f"别名：{'、'.join(d['aliases'])}")
    print(f"支持文献：{len(d['docs'])} 篇（{', '.join(d['docs'])}）；"
          f"专论文献：{len(d['title_docs'])} 篇")
    print(f"易感/日龄线索：{'、'.join(d.get('age_hints', []))}")
    print(f"用药/防治线索：{'、'.join(d.get('drugs', []))}")
    print(f"\n症状（{len(d['symptoms'])} 条）：")
    for tier in ("强", "中", "弱"):
        items = sorted([(s, v) for s, v in d["symptoms"].items() if v["tier"] == tier],
                       key=lambda x: -x[1]["score"])
        for s, v in items:
            ev = v.get("evidence") or []
            evs = f"　← [{ev[0][0]}] {ev[0][1][:56]}…" if ev else ""
            print(f"  {TIER_MARK[tier]} {s:<14} 专论支持{v['title_support']}篇/"
                  f"共{v['n_docs_with']}篇  特异性{1-v['prevalence']:.2f}{evs}")


def main():
    ap = argparse.ArgumentParser(description="猪病辅助诊断（命令行）")
    ap.add_argument("text", nargs="*", help="症状描述")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--disease", help="查看某疾病的知识库记录")
    ap.add_argument("--list", action="store_true", help="列出知识库疾病")
    ap.add_argument("--llm", action="store_true", help="启用大模型辅助口语归一化")
    ap.add_argument("--topk", type=int, default=3)
    args = ap.parse_args()

    dx = diagnose.Diagnoser()

    if args.list:
        print(f"知识库共 {len(dx.diseases)} 种疾病：")
        for d in dx.diseases:
            mark = "" if d["title_docs"] else "  ← 无专论文献"
            print(f"  {d['name']:<16} 症状{len(d['symptoms']):>3} 条  "
                  f"文献{len(d['docs']):>2} 篇{mark}")
        return

    if args.disease:
        show_disease(args.disease, dx)
        return

    def run(text):
        parsed = nlu.normalize(text, use_llm=True if args.llm else None)
        res = dx.evaluate(parsed["symptoms"], parsed["ages"], topk=args.topk)
        res["parsed"] = parsed
        res["differential"] = dx.differential(res)
        res["safety"] = safety.check(res, raw_text=text)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=1))
        else:
            print(render(res, dx.sources))

    if args.text:
        run(" ".join(args.text))
        return

    print("猪病辅助诊断（输入症状描述，回车提交；输入 q 退出）")
    print("示例：仔猪拉稀，黄白色的，两天了，不吃食\n")
    while True:
        try:
            t = input("症状> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if t.lower() in ("q", "quit", "exit"):
            break
        if not t:
            continue
        run(t)
        print()


if __name__ == "__main__":
    main()
