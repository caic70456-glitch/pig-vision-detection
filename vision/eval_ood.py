# -*- coding: utf-8 -*-
"""跨域泛化（OOD）评估：域内测试集 vs 域外压力测试集。

背景：本检测器训练于 PigBench —— 栏舍固定机位俯拍监控画面。为了量化"换个
拍摄方式还能不能用"，本脚本在同一套预处理/后处理下对比两个集合：

  • 域内  vision/data/pigdetect/extract/test/   栏舍俯拍，有真值 → 出 P/R
  • 域外  vision/ood_hard_set/                  自然光/平视/户外，无真值
                                                → 只比置信度分布与检出数

用法：
    python vision/eval_ood.py
    python vision/eval_ood.py --model vision/models/pig-detector-yolov8n-int8.onnx
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bootstrap  # noqa: F401,E402

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import onnxruntime as ort  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
IN_DOMAIN = os.path.join(_HERE, "data", "pigdetect", "extract", "test")
OOD = os.path.join(_HERE, "ood_hard_set")
IMGSZ = 640


# ---------- 与网页端完全一致的预处理 / 后处理 ----------
def letterbox(img):
    w, h = img.size
    r = min(IMGSZ / h, IMGSZ / w)
    nw, nh = int(round(w * r)), int(round(h * r))
    dw, dh = (IMGSZ - nw) / 2, (IMGSZ - nh) / 2
    canvas = Image.new("RGB", (IMGSZ, IMGSZ), (114, 114, 114))
    canvas.paste(img.resize((nw, nh), Image.BILINEAR), (int(dw), int(dh)))
    arr = np.transpose(np.asarray(canvas, dtype=np.float32) / 255.0, (2, 0, 1))
    return arr[None, ...], (w, h), (r, dw, dh)


def postprocess(raw, iw, ih, r, dw, dh, conf, iou):
    raw = raw[0] if raw.ndim == 3 else raw
    if raw.ndim == 2 and raw.shape[0] < raw.shape[1]:
        raw = raw.T
    boxes, scores = [], []
    for row in raw:
        cx, cy, bw, bh, obj = row[:5]
        if obj < conf:
            continue
        x1 = (cx - bw / 2 - dw) / r; y1 = (cy - bh / 2 - dh) / r
        x2 = (cx + bw / 2 - dw) / r; y2 = (cy + bh / 2 - dh) / r
        x1, x2 = max(0, min(iw, x1)), max(0, min(iw, x2))
        y1, y2 = max(0, min(ih, y1)), max(0, min(ih, y2))
        if x2 > x1 and y2 > y1:
            boxes.append([x1, y1, x2, y2]); scores.append(float(obj))
    if not boxes:
        return np.zeros((0, 4)), np.zeros(0)
    boxes, scores = np.array(boxes), np.array(scores)
    order = scores.argsort()[::-1]; keep = []
    while order.size:
        i = order[0]; keep.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(boxes[i, 0], boxes[order[1:], 0]); yy1 = np.maximum(boxes[i, 1], boxes[order[1:], 1])
        xx2 = np.minimum(boxes[i, 2], boxes[order[1:], 2]); yy2 = np.minimum(boxes[i, 3], boxes[order[1:], 3])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        ai = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        aj = (boxes[order[1:], 2] - boxes[order[1:], 0]) * (boxes[order[1:], 3] - boxes[order[1:], 1])
        order = order[1:][inter / (ai + aj - inter + 1e-8) < iou]
    return boxes[keep], scores[keep]


def load_gt(path, iw, ih):
    if not os.path.isfile(path):
        return np.zeros((0, 4))
    out = []
    for line in open(path, encoding="utf-8"):
        p = line.split()
        if len(p) < 5:
            continue
        _, cx, cy, bw, bh = map(float, p[:5])
        out.append([(cx - bw / 2) * iw, (cy - bh / 2) * ih,
                    (cx + bw / 2) * iw, (cy + bh / 2) * ih])
    return np.array(out) if out else np.zeros((0, 4))


def run(sess, path, conf=0.25, iou=0.45):
    img = Image.open(path).convert("RGB")
    arr, (iw, ih), (r, dw, dh) = letterbox(img)
    raw = sess.run(None, {sess.get_inputs()[0].name: arr})[0]
    return postprocess(raw, iw, ih, r, dw, dh, conf, iou), (iw, ih)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.join(_HERE, "models",
                                                    "pig-detector-yolov8n-int8.onnx"))
    ap.add_argument("--in-domain", type=int, default=30, help="域内参与统计的图片数")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--iou", type=float, default=0.45)
    args = ap.parse_args()

    sess = ort.InferenceSession(args.model, providers=["CPUExecutionProvider"])
    print(f"模型: {os.path.basename(args.model)}  conf={args.conf} NMS={args.iou}")
    print("=" * 68)

    # ---- 域内 ----
    dom = sorted(glob.glob(os.path.join(IN_DOMAIN, "images", "*.jpg")))[:args.in_domain]
    tp = fp = ngt = 0
    dom_confs = []
    for p in dom:
        (pb, ps), (iw, ih) = run(sess, p, args.conf, args.iou)
        dom_confs.append(ps.mean() if len(ps) else 0.0)
        gt = load_gt(os.path.join(IN_DOMAIN, "labels",
                                  os.path.splitext(os.path.basename(p))[0] + ".txt"), iw, ih)
        ngt += len(gt)
        if len(gt) == 0:
            fp += len(pb); continue
        iou_mat = np.zeros((len(pb), len(gt)))
        for i in range(len(pb)):
            for j in range(len(gt)):
                xx1 = max(pb[i][0], gt[j][0]); yy1 = max(pb[i][1], gt[j][1])
                xx2 = min(pb[i][2], gt[j][2]); yy2 = min(pb[i][3], gt[j][3])
                inter = max(0, xx2 - xx1) * max(0, yy2 - yy1)
                ai = (pb[i][2]-pb[i][0])*(pb[i][3]-pb[i][1])
                aj = (gt[j][2]-gt[j][0])*(gt[j][3]-gt[j][1])
                iou_mat[i, j] = inter / (ai + aj - inter + 1e-8)
        used = set()
        for i in range(len(pb)):
            j = int(iou_mat[i].argmax())
            if iou_mat[i, j] > 0.5 and j not in used:
                used.add(j); tp += 1
            else:
                fp += 1
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / ngt if ngt else 0
    dom_n = sum(1 for _ in dom)

    # ---- 域外 ----
    ood = sorted(glob.glob(os.path.join(OOD, "*.jpg")))
    ood_rows = []
    for p in ood:
        (pb, ps), _ = run(sess, p, args.conf, args.iou)
        ood_rows.append((os.path.basename(p), len(pb),
                         float(ps.mean()) if len(ps) else 0.0,
                         float(ps.max()) if len(ps) else 0.0))

    print(f"{'集合':<22}{'图片数':>6}{'平均每图检出':>14}{'逐图平均置信度':>16}")
    print("-" * 68)
    dom_avg_conf = float(np.mean(dom_confs))
    dom_avg_box = None
    print(f"{'域内(栏舍俯拍)':<20}{dom_n:>6}{'—':>14}{dom_avg_conf:>16.3f}")
    if ood_rows:
        print(f"{'域外(自然光/平视)':<19}{len(ood_rows):>6}"
              f"{np.mean([r[1] for r in ood_rows]):>14.2f}"
              f"{np.mean([r[2] for r in ood_rows]):>16.3f}")
    print()
    print(f"域内 P/R（IoU>0.5, conf={args.conf}）: "
          f"Precision {prec:.4f}  Recall {rec:.4f}   真值框 {ngt}")
    print()
    print("域外逐图明细：")
    print(f"  {'文件':<16}{'检出':>6}{'平均置信':>10}{'最高分':>10}")
    for f, c, a, m in ood_rows:
        flag = "  ← 疑似漏检" if c == 0 else ""
        print(f"  {f:<16}{c:>6}{a:>10.3f}{m:>10.3f}{flag}")

    out = {"model": os.path.basename(args.model), "conf": args.conf, "iou": args.iou,
           "in_domain": {"images": dom_n, "precision": prec, "recall": rec,
                         "avg_conf": dom_avg_conf, "gt_boxes": int(ngt)},
           "ood": [{"file": f, "boxes": c, "avg_conf": a, "max_conf": m}
                   for f, c, a, m in ood_rows]}
    p = os.path.join(_HERE, "results", "ood_eval.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n结果已写入: {p}")


if __name__ == "__main__":
    main()
