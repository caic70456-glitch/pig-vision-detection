# -*- coding: utf-8 -*-
"""网页演示界面（纯标准库 + PIL，无需 Flask）。

启动：
    python web/app.py --port 8000

三条演示路径：
    1. 合成场景分析（内置 6 个已知答案场景）——验证流程，出可视化图
    2. 上传真实照片 —— 走 COCO 检测器（会明确提示不认识「猪」）
    3. 帧序列分析 —— 选择内置合成序列，展示时序行为判定
"""
import argparse
import base64
import io
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

import detector  # noqa: E402
import pipeline  # noqa: E402
import visualize  # noqa: E402
from behavior import BEHAVIOR_CN, classify_scene  # noqa: E402
from health import assess  # noqa: E402
from report import build_report  # noqa: E402
from scene import compute_scene, compute_tracks  # noqa: E402

CACHE = os.path.join(BASE, "cache")
os.makedirs(CACHE, exist_ok=True)
SYN = os.path.join(ROOT, "synthetic")
SYNF = os.path.join(ROOT, "synthetic_frames")

_BACKEND = None


def get_backend():
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = detector.build_backend(kind="auto")
    return _BACKEND


def esc(s):
    import html
    return html.escape(str(s if s is not None else ""))


def load_scenes():
    p = os.path.join(SYN, "scenes.json")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def load_sequences():
    p = os.path.join(SYNF, "sequences.json")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def img_tag(path):
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return f'<img class="vis" src="data:image/png;base64,{b64}">'


def analyze_scene(scene_meta, image_size):
    dets = [detector.Detection(tuple(d["box"]), d["label"], d["score"])
            for d in scene_meta["detections"]]
    rep = pipeline.analyze_detections(dets, image_size, backend_name="合成场景（已知答案）",
                                     approximate=True)
    result = detector.DetectionResult(detections=dets, backend="合成场景",
                                     approximate=True, image_size=tuple(image_size))
    scene = compute_scene(result)
    behavior = classify_scene(scene)
    out = os.path.join(CACHE, "annotated_" + scene_meta["name"] + ".png")
    visualize.annotate(scene_meta["image"], result, scene, behavior, out,
                       title=f"{scene_meta['name']} · {scene_meta['desc']}")
    return rep, out


def analyze_sequence(seq_meta, image_size):
    scenes = []
    for dets_raw in seq_meta["frames"]:
        dets = [detector.Detection(tuple(d["box"]), d["label"], d["score"]) for d in dets_raw]
        r = detector.DetectionResult(detections=dets, backend="合成序列",
                                     approximate=True, image_size=tuple(image_size))
        scenes.append(compute_scene(r))
    tracks = compute_tracks(scenes)
    agg, total = {}, 0
    for sf in scenes:
        br = classify_scene(sf, tracks=tracks, track_scenes=len(scenes))
        for k, v in br.distribution.items():
            agg[k] = agg.get(k, 0) + v
        total += sum(br.distribution.values())
    pct = {k: v * 100.0 / total for k, v in agg.items()} if total else {}
    first = classify_scene(scenes[0], tracks=tracks, track_scenes=len(scenes))
    last = classify_scene(scenes[-1], tracks=tracks, track_scenes=len(scenes))

    # 可视化最后两帧
    imgs = []
    for idx in (len(seq_meta["frames"]) - 2, len(seq_meta["frames"]) - 1):
        fp = os.path.join(seq_meta["dir"], f"{idx:03d}.png")
        if not os.path.isfile(fp):
            continue
        dets = [detector.Detection(tuple(d["box"]), d["label"], d["score"])
                for d in seq_meta["frames"][idx]]
        r = detector.DetectionResult(detections=dets, backend="合成序列",
                                     approximate=True, image_size=tuple(image_size))
        sf = compute_scene(r)
        br = classify_scene(sf, tracks=tracks, track_scenes=len(seq_meta["frames"]))
        out = os.path.join(CACHE, f"seq_{seq_meta['name']}_{idx:03d}.png")
        visualize.annotate(fp, r, sf, br, out,
                           title=f"{seq_meta['name']} · 第 {idx+1}/{len(seq_meta['frames'])} 帧")
        imgs.append(out)
    return pct, tracks, first, last, imgs


def render_page(msg=None, scenes_html=None, upload_html=None, seq_html=None, backend_info=None):
    parts = ["""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>猪场视觉行为识别与巡检报告</title><style>
*{box-sizing:border-box} body{font-family:"Microsoft YaHei",sans-serif;margin:0;background:#f4f6f8;color:#22303c}
.wrap{max-width:1180px;margin:0 auto;padding:22px}
header{background:linear-gradient(135deg,#1f6f3c,#2f9e5f);color:#fff;padding:18px 22px;border-radius:10px}
header h1{margin:0;font-size:20px} header p{margin:6px 0 0;font-size:13px;opacity:.92}
.card{background:#fff;border:1px solid #e2e8ee;border-radius:10px;padding:16px;margin-top:16px}
.card h2{margin:0 0 12px;font-size:16px;color:#1f6f3c;border-left:4px solid #2f9e5f;padding-left:9px}
.vis{max-width:100%;border-radius:8px;border:1px solid #dfe6ec;margin-top:8px}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}
th,td{border:1px solid #e6ecf1;padding:6px 9px;text-align:left;vertical-align:top}
th{background:#f3f7fa}
.box{background:#f7fafc;border-radius:7px;padding:11px 13px;font-size:13px;white-space:pre-wrap;line-height:1.65;margin-top:8px}
.warn{background:#fff8e6;border-left:4px solid #e0a800;padding:10px 13px;border-radius:6px;margin:9px 0;font-size:13px}
.info{background:#eef6ff;border-left:4px solid #2b7de9;padding:10px 13px;border-radius:6px;margin:9px 0;font-size:13px}
.disc{background:#eef3f7;border-radius:7px;padding:11px 13px;font-size:12px;color:#5b6b7a;margin-top:12px}
button{background:#2f9e5f;color:#fff;border:0;border-radius:7px;padding:9px 18px;font-size:14px;cursor:pointer}
button:hover{background:#26834e}
button.sm{padding:5px 11px;font-size:12.5px;background:#eef3f7;color:#22303c}
button.sm:hover{background:#dfe8ef}
.pill{display:inline-block;background:#eef3f7;border-radius:12px;padding:2px 10px;font-size:12px;margin-right:6px}
</style></head><body><div class="wrap">
<header><h1>猪场视觉行为识别与巡检报告</h1>
<p>检测与行为解耦 · 行为规则可解释 · 视觉输入到语言报告 ｜ 研究演示系统，不能替代现场巡查与兽医诊断</p></header>
"""]

    # 后端能力
    parts.append('<div class="card"><h2>① 检测后端能力</h2>')
    if backend_info:
        can = backend_info.get("can_detect_pig")
        parts.append(f'<div class="info">当前后端：<b>{esc(backend_info.get("name"))}</b>　'
                     f'识别「猪」类别能力：<b>{"有" if can else "无"}</b></div>')
        if not can:
            parts.append('<div class="warn">COCO 数据集没有 pig 类别，因此当前后端只能给出'
                         '「疑似猪只的动物」粗类别，可能把猪计为 cow/sheep/horse 或漏检。'
                         '要获得真正的猪只检测，请把猪只检测模型（.onnx）放入 '
                         f'<code>{esc(detector.MODELS_DIR)}</code> 目录并在同目录提供 labels.json。</div>')
        parts.append(f'<div class="box">{esc(json.dumps(backend_info, ensure_ascii=False, indent=1))}</div>')
    parts.append("</div>")

    if msg:
        parts.append(f'<div class="card"><div class="warn">{esc(msg)}</div></div>')

    # 合成场景
    parts.append('<div class="card"><h2>② 合成场景分析（已知标准答案，用于验证流程）</h2>')
    parts.append('<div class="info">合成图像只验证流水线逻辑正确性，'
                 '不代表真实栏舍识别精度。真实精度需在真实猪舍图像上评测。</div>')
    parts.append('<form method="get" action="/"><input type="hidden" name="act" value="scenes">'
                 '<button type="submit">运行全部合成场景</button></form>')
    parts.append(scenes_html or "")
    parts.append("</div>")

    # 帧序列
    parts.append('<div class="card"><h2>③ 时序行为判定（站立 / 行走 / 卧倒 / 争斗）</h2>')
    parts.append('<div class="info">单帧无法区分「站立」与「行走」；'
                 '本项用连续帧的位移与面积变化做时序判定。</div>')
    parts.append('<form method="get" action="/"><input type="hidden" name="act" value="sequences">'
                 '<button type="submit">运行全部合成序列</button></form>')
    parts.append(seq_html or "")
    parts.append("</div>")

    # 上传真实图片
    parts.append('<div class="card"><h2>④ 上传真实照片</h2>')
    parts.append('<form method="post" action="/upload" enctype="multipart/form-data">'
                 '<input type="file" name="image" accept="image/*" required> '
                 '<button type="submit">分析</button></form>')
    parts.append('<div class="info">上传的照片会走当前检测后端。若后端不认识「猪」，'
                 '结果只说明流程可用，不代表识别正确。</div>')
    parts.append(upload_html or "")
    parts.append("</div>")

    parts.append('<div class="disc">研究演示系统。检测结果与行为判定均可能出错；'
                 '报告内容不构成疾病诊断或用药依据，异常情况请由执业兽医现场检查。</div>')
    parts.append("</div></body></html>")
    return "".join(parts)


def render_scenes():
    data = load_scenes()
    if not data:
        return '<div class="warn">未找到合成场景，请先运行 <code>python make_scenes.py</code></div>'
    html = []
    for s in data["scenes"]:
        rep, img = analyze_scene(s, data["image_size"])
        sc = rep["scene"]
        exp = {int(k): BEHAVIOR_CN.get(v, v) for k, v in s["expected"].items()}
        got = {v["index"]: v["behavior_cn"] for v in rep["behavior"]["verdicts"]}
        html.append(f'<h3 style="font-size:14px;margin:14px 0 4px">{esc(s["name"])}　'
                    f'<span class="pill">{esc(s["desc"])}</span></h3>')
        html.append(img_tag(img))
        rows = []
        for k in exp:
            ok = exp[k] == got.get(k)
            rows.append(f'<tr><td>#{k+1}</td><td>{esc(exp[k])}</td>'
                        f'<td>{esc(got.get(k, "—"))}</td>'
                        f'<td>{"✓" if ok else "✗"}</td></tr>')
        html.append('<table><tr><th>目标</th><th>预期行为</th><th>系统判定</th><th>结果</th></tr>'
                    + "".join(rows) + "</table>")
        html.append(f'<div class="box">{esc(rep.get("narrative",""))}</div>')
    return "".join(html)


def render_sequences():
    data = load_sequences()
    if not data:
        return '<div class="warn">未找到合成序列，请先运行 <code>python make_sequences.py</code></div>'
    html = []
    for s in data["sequences"]:
        pct, tracks, first, last, imgs = analyze_sequence(s, data["image_size"])
        dist = "、".join(f"{BEHAVIOR_CN.get(k,k)} {v:.0f}%" for k, v in
                        sorted(pct.items(), key=lambda x: -x[1]) if v > 0)
        html.append(f'<h3 style="font-size:14px;margin:14px 0 4px">{esc(s["name"])}　'
                    f'<span class="pill">{esc(s["desc"])}</span></h3>')
        for im in imgs:
            html.append(img_tag(im))
        tr = "；".join(f"#{t.track_id+1} 位移 {t.displacement:.3f}、速度 {t.speed:.4f}、"
                       f"面积变化 {t.area_change:+.2f}" for t in tracks)
        html.append(f'<div class="box">时序特征：{esc(tr)}\n行为占比：{esc(dist)}</div>')
    return "".join(html)


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, code=200):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        act = (q.get("act") or [""])[0]
        info = get_backend().describe()
        if act == "scenes":
            self._send(render_page(scenes_html=render_scenes(), backend_info=info))
        elif act == "sequences":
            self._send(render_page(seq_html=render_sequences(), backend_info=info))
        else:
            self._send(render_page(backend_info=info))

    def do_POST(self):
        ctype = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        info = get_backend().describe()
        if "multipart/form-data" not in ctype or "boundary=" not in ctype:
            self._send(render_page(msg="上传格式不正确", backend_info=info))
            return
        boundary = ctype.split("boundary=", 1)[1].strip().strip('"').encode()
        # 极简 multipart 解析：取出第一个文件部分
        parts = raw.split(b"--" + boundary)
        file_bytes = None
        for p in parts:
            if b"filename=" in p and b"\r\n\r\n" in p:
                head, body = p.split(b"\r\n\r\n", 1)
                if b"filename=" in head:
                    file_bytes = body.rstrip(b"\r\n").rstrip(b"--")
                    break
        if not file_bytes:
            self._send(render_page(msg="未收到图片文件", backend_info=info))
            return
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        except Exception as e:
            self._send(render_page(msg=f"图片解析失败：{e}", backend_info=info))
            return

        tmp = os.path.join(CACHE, "upload.png")
        img.save(tmp)
        backend = get_backend()
        result = backend.detect(img)
        scene = compute_scene(result)
        behavior = classify_scene(scene)
        meta = {"backend": result.backend,
                "can_detect_pig": getattr(backend, "can_detect_pig", False),
                "approximate": result.approximate,
                "approx_note": "", "warnings": result.warnings}
        rep = build_report(scene, behavior, assess(behavior), result_meta=meta)
        out = os.path.join(CACHE, "upload_annotated.png")
        visualize.annotate(tmp, result, scene, behavior, out,
                           title=f"上传图片 · 检出 {scene.animal_count} 个目标")
        body = ['<h3 style="font-size:14px">分析结果</h3>', img_tag(out)]
        body.append(f'<div class="box">目标数：{scene.animal_count}　人员数：{scene.person_count}\n'
                    f'行为构成：{esc(json.dumps({BEHAVIOR_CN.get(k,k): round(v,1) for k,v in rep["behavior"]["distribution_pct"].items()}, ensure_ascii=False))}</div>')
        if scene.animal_count == 0:
            body.append('<div class="warn">未检出任何目标。可能是因为当前检测器不认识猪，'
                        '或图片中无 COCO 覆盖的动物类别。</div>')
        body.append(f'<div class="box">{esc(rep.get("narrative",""))}</div>')
        self._send(render_page(upload_html="".join(body), backend_info=info))

    def log_message(self, fmt, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    print("预热检测后端……")
    info = get_backend().describe()
    print("后端:", info.get("name"), "| 识别猪类别:", info.get("can_detect_pig"))
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"猪场视觉分析系统已启动： http://{args.host}:{args.port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
