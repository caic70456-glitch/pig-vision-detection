# -*- coding: utf-8 -*-
"""网页演示界面（纯标准库，无需 Flask）。

启动：
    python web/app.py                # 默认 http://127.0.0.1:8000
    python web/app.py --port 8080

页面提供三种输入方式：
    1. 自由文本描述（模拟养殖户口语）
    2. 症状点选（结构化输入）
    3. 一键载入示例
结果展示：候选疾病排序、命中症状及文献出处、鉴别要点、安全层提示与免责声明。
"""
import argparse
import html
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
sys.path.insert(0, ROOT)

import diagnose  # noqa: E402
import nlu  # noqa: E402
import safety  # noqa: E402

DX = diagnose.Diagnoser()

EXAMPLES = [
    "7日龄内新生仔猪呕吐，随即水样腹泻，脱水严重",
    "保育猪眼睑和面部水肿，突然死亡，之前有轻度腹泻",
    "育肥猪长期干咳，生长迟缓，被毛粗乱，体温不高",
    "母猪流产产死胎，仔猪呼吸困难，耳部发绀",
    "仔猪腹泻，之前用了氯霉素和呋喃唑酮",
    "猪只采食霉变饲料后呕吐腹泻，部分母猪流产",
]

TIER_LABEL = {"强": "强证据", "中": "中证据", "弱": "弱证据"}
TIER_CLASS = {"强": "t-strong", "中": "t-mid", "弱": "t-weak"}


def esc(s):
    return html.escape(str(s if s is not None else ""))


def render_page(result=None, text="", selected=None, error=None):
    selected = selected or []
    sym_list = sorted(nlu.SYMPTOM_DICT)

    parts = []
    parts.append("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>猪病辅助诊断系统</title>
<style>
 *{box-sizing:border-box}
 body{font-family:"Microsoft YaHei",-apple-system,sans-serif;margin:0;background:#f4f6f8;color:#22303c}
 .wrap{max-width:1080px;margin:0 auto;padding:24px}
 header{background:linear-gradient(135deg,#1f6f3c,#2f9e5f);color:#fff;padding:20px 24px;border-radius:10px}
 header h1{margin:0;font-size:21px}
 header p{margin:6px 0 0;font-size:13px;opacity:.9}
 .grid{display:grid;grid-template-columns:1fr;gap:18px;margin-top:18px}
 .card{background:#fff;border:1px solid #e2e8ee;border-radius:10px;padding:18px}
 .card h2{margin:0 0 12px;font-size:16px;color:#1f6f3c;border-left:4px solid #2f9e5f;padding-left:9px}
 textarea{width:100%;min-height:84px;padding:10px;border:1px solid #cfd8e0;border-radius:7px;font-size:14px;font-family:inherit;resize:vertical}
 .btns{margin-top:12px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
 button{background:#2f9e5f;color:#fff;border:0;border-radius:7px;padding:10px 22px;font-size:14px;cursor:pointer}
 button:hover{background:#26834e}
 button.ghost{background:#eef3f7;color:#22303c;padding:7px 13px;font-size:12.5px}
 button.ghost:hover{background:#dfe8ef}
 .chips{display:flex;flex-wrap:wrap;gap:7px;max-height:220px;overflow:auto;padding:4px 2px}
 label.chip{display:inline-flex;align-items:center;gap:5px;background:#f0f4f8;border:1px solid #dbe4ec;border-radius:15px;padding:4px 11px;font-size:12.5px;cursor:pointer}
 label.chip:hover{background:#e4edf4}
 label.chip input{margin:0}
 .cand{border:1px solid #e2e8ee;border-radius:9px;padding:14px;margin-bottom:13px;background:#fcfdfe}
 .cand.top{border-color:#2f9e5f;background:#f4fbf6;box-shadow:0 1px 4px rgba(47,158,95,.13)}
 .cand h3{margin:0 0 4px;font-size:16px;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
 .rank{background:#2f9e5f;color:#fff;border-radius:5px;padding:1px 8px;font-size:12px}
 .conf{font-size:12.5px;color:#5b6b7a;font-weight:400}
 .bar{height:7px;background:#e4eaef;border-radius:4px;overflow:hidden;margin:9px 0 3px}
 .bar>i{display:block;height:100%;background:linear-gradient(90deg,#2f9e5f,#5cc98a)}
 table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:9px}
 th,td{border:1px solid #e6ecf1;padding:5px 8px;text-align:left;vertical-align:top}
 th{background:#f3f7fa;font-weight:600}
 .t-strong{color:#1f6f3c;font-weight:600}
 .t-mid{color:#9a6a12}
 .t-weak{color:#8a94a0}
 .ev{color:#6b7885;font-size:11.5px}
 .meta{font-size:12.5px;color:#5b6b7a;margin:5px 0}
 .warn{background:#fff8e6;border-left:4px solid #e0a800;padding:10px 13px;border-radius:6px;margin:9px 0;font-size:13px}
 .block{background:#fdecec;border-left:4px solid #d33;padding:10px 13px;border-radius:6px;margin:9px 0;font-size:13px}
 .disc{background:#eef3f7;border-radius:7px;padding:11px 13px;font-size:12px;color:#5b6b7a;margin-top:14px}
 .note{background:#eef6ff;border-left:4px solid #2b7de9;padding:10px 13px;border-radius:6px;margin:9px 0;font-size:13px}
 ul.tight{margin:6px 0;padding-left:20px}
 ul.tight li{margin:3px 0;font-size:13px}
 .kv{font-size:13px;margin:4px 0}
 .kv b{color:#1f6f3c}
</style></head><body><div class="wrap">
<header>
  <h1>猪病辅助诊断系统</h1>
  <p>基于文献知识库的症状加权匹配推理 ｜ 结果仅供学习研究，不能替代执业兽医诊断</p>
</header>
""")

    # ---- 输入区 ----
    parts.append('<div class="grid"><div class="card"><h2>① 描述症状</h2>')
    parts.append('<form method="post" action="/diagnose">')
    parts.append(f'<textarea name="text" placeholder="用日常说法描述，例如：仔猪拉稀，黄白色的，两天了，不吃食">{esc(text)}</textarea>')

    parts.append('<div class="meta">也可以直接点选症状（可多选，与上面文字叠加）：</div>')
    parts.append('<div class="chips">')
    for s in sym_list:
        checked = " checked" if s in selected else ""
        parts.append(f'<label class="chip"><input type="checkbox" name="sym" value="{esc(s)}"{checked}>{esc(s)}</label>')
    parts.append("</div>")

    parts.append('<div class="btns"><button type="submit">开始诊断</button>')
    for ex in EXAMPLES:
        parts.append(f'<button class="ghost" type="submit" name="example" value="{esc(ex)}">示例：{esc(ex[:16])}…</button>')
    parts.append("</div></form></div>")

    # ---- 结果区 ----
    if error:
        parts.append(f'<div class="card"><div class="block">{esc(error)}</div></div>')

    if result:
        p = result.get("parsed", {})
        parts.append('<div class="card"><h2>② 症状解析结果</h2>')
        parts.append(f'<div class="kv"><b>原始输入</b>：{esc(p.get("raw",""))}</div>')
        syms = p.get("symptoms", [])
        parts.append(f'<div class="kv"><b>识别出的标准症状</b>（{len(syms)} 个）：'
                     f'{esc("、".join(syms)) if syms else "（未识别到）"}</div>')
        if p.get("ages"):
            parts.append(f'<div class="kv"><b>日龄线索</b>：{esc("、".join(p["ages"]))}</div>')
        if p.get("duration"):
            parts.append(f'<div class="kv"><b>病程</b>：{esc(p["duration"])}</div>')
        if p.get("llm_note"):
            parts.append(f'<div class="meta">大模型辅助未启用：{esc(p["llm_note"])}</div>')
        parts.append("</div>")

        parts.append('<div class="card"><h2>③ 诊断推理结果</h2>')
        cands = result.get("candidates", [])
        if not cands:
            parts.append('<div class="note">未匹配到候选疾病，请补充更多症状描述。</div>')
        for i, c in enumerate(cands, 1):
            cls = "cand top" if i == 1 else "cand"
            parts.append(f'<div class="{cls}">')
            parts.append(f'<h3><span class="rank">{"首选" if i==1 else "候选"+str(i)}</span>'
                         f'{esc(c["disease"])}'
                         f'<span class="conf">置信度 {c["confidence"]:.0%}　'
                         f'症状解释率 {c["explain"]:.0%}　证据分 {c["evidence"]}</span></h3>')
            parts.append(f'<div class="bar"><i style="width:{max(4, int(c["confidence"]*100))}%"></i></div>')
            if c.get("aliases"):
                parts.append(f'<div class="meta">别名：{esc("、".join(c["aliases"]))}</div>')
            parts.append('<table><tr><th style="width:150px">命中症状</th><th style="width:78px">证据强度</th>'
                         '<th style="width:76px">文献支持</th><th>原文出处</th></tr>')
            for h in c["matched"]:
                ev = "—"
                if h.get("evidence"):
                    no, sent = h["evidence"][0]
                    src = DX.sources.get(str(no), {})
                    ev = esc(f"[{no}] {src.get('source','')}{src.get('year','')}：{sent}")
                parts.append(f'<tr><td>{esc(h["symptom"])}</td>'
                             f'<td class="{TIER_CLASS.get(h["tier"],"")}">{TIER_LABEL.get(h["tier"],h["tier"])}</td>'
                             f'<td>{h.get("n_docs",0)} 篇</td>'
                             f'<td class="ev">{ev}</td></tr>')
            parts.append("</table>")
            if c.get("unreported"):
                parts.append(f'<div class="meta">该病常见但本次未提及的症状：'
                             f'{esc("、".join(c["unreported"]))}</div>')
            if not c.get("title_docs"):
                parts.append('<div class="warn">知识库中缺少本病专论文献，其症状依据较弱，请谨慎采信。</div>')
            parts.append("</div>")
        if result.get("note"):
            parts.append(f'<div class="note">{esc(result["note"])}</div>')
        parts.append("</div>")

        # 鉴别要点
        if result.get("differential"):
            parts.append('<div class="card"><h2>④ 鉴别诊断要点</h2><ul class="tight">')
            for d in result["differential"]:
                a = esc("、".join(d["supports_top1"]) or "—")
                b = esc("、".join(d["supports_other"]) or "—")
                parts.append(f'<li><b>{esc(d["pair"])}</b>：首选病支持症状 {a}；'
                             f'另一候选支持症状 {b}</li>')
            parts.append("</ul></div>")

        # 安全层
        s = result.get("safety", {})
        parts.append('<div class="card"><h2>⑤ 安全层校验</h2>')
        for b in s.get("blocked", []):
            parts.append(f'<div class="block">✗ 已阻断：<b>{esc(b["drug"])}</b>'
                         f'（{esc(b["disease"])}）—— {esc(b["reason"])}，适用范围：{esc(b["scope"])}</div>')
        if s.get("drug_advice"):
            parts.append('<div class="meta">文献中出现的药物线索（<b>不是处方</b>）：</div><ul class="tight">')
            for d in s["drug_advice"]:
                parts.append(f'<li>{esc(d["drug"])}　<span class="ev">（{esc(d["disease"])}，{esc(d["source"])}）</span></li>')
            parts.append("</ul>")
        for w in s.get("warnings", []):
            parts.append(f'<div class="warn">{esc(w)}</div>')
        parts.append(f'<div class="disc"><b>免责声明</b>：{esc(s.get("disclaimer",""))}</div>')
        parts.append("</div>")

    kb_meta = DX.kb.get("meta", {})
    parts.append(f'<div class="disc">知识库：{esc(kb_meta.get("built_from",""))}，'
                 f'共 {esc(kb_meta.get("disease_count",""))} 种猪病。'
                 f'{esc(kb_meta.get("note",""))}</div>')
    parts.append("</div></body></html>")
    return "".join(parts)


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, code=200):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(render_page())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        form = urllib.parse.parse_qs(raw, keep_blank_values=True)

        text = (form.get("text", [""])[0] or "").strip()
        if form.get("example"):
            text = form["example"][0]
        picked = form.get("sym", [])

        if not text and not picked:
            self._send(render_page(error="请输入症状描述或点选症状后再提交。"))
            return

        # 文字描述与点选症状合并
        parsed = nlu.normalize(text)
        syms = sorted(set(parsed["symptoms"]) | set(picked))
        res = DX.evaluate(syms, parsed["ages"], topk=3)
        res["parsed"] = parsed
        if picked:
            res["parsed"]["picked"] = picked
        res["differential"] = DX.differential(res)
        res["safety"] = safety.check(res, raw_text=text)
        self._send(render_page(result=res, text=text, selected=picked))

    def log_message(self, fmt, *a):
        pass  # 静音访问日志，保持控制台干净


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"猪病辅助诊断系统已启动： http://{args.host}:{args.port}")
    print(f"知识库：{len(DX.diseases)} 种疾病　按 Ctrl+C 停止")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
