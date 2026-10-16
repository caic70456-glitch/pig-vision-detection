# -*- coding: utf-8 -*-
"""ONNX 模型 INT8 动态量化 + 精度/速度对比。

ONNX Runtime 动态量化：直接权重从 FP32 转 INT8，无需校准数据集。
适合边缘端部署（树莓派 / Jetson Nano）—— 体积减半，CPU 推理加速 2-4x。
"""
import json, os, sys, time, glob
from pathlib import Path

import numpy as np
import onnxruntime as ort

MODEL_FP32 = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "models", "pig-detector-yolov8n.onnx")
MODEL_INT8 = os.path.join(os.path.dirname(MODEL_FP32),
                          "pig-detector-yolov8n-int8.onnx")
DATASET_ROOT = r"E:/harness/aic/vision/data/pigdetect/extract"
TEST_IMAGES = os.path.join(DATASET_ROOT, "test", "images")
IMGSZ = 640

sys.stdout.reconfigure(encoding="utf-8")


def quantize_dynamic(fp32_path, int8_path):
    """ONNX Runtime 动态量化：权重 FP32 → INT8。"""
    from onnxruntime.quantization import quantize_dynamic, QuantType
    print("📦 正在对 %s 做动态量化..." % os.path.basename(fp32_path))
    quantize_dynamic(fp32_path, int8_path,
                     weight_type=QuantType.QUInt8)
    print("✅ 量化完成: %s (%.1f KB)" % (
        os.path.basename(int8_path), os.path.getsize(int8_path) / 1024))


def preprocess(img_path):
    from PIL import Image
    img = Image.open(img_path).convert("RGB")
    h, w = img.height, img.width
    r = min(IMGSZ / h, IMGSZ / w)
    nh, nw = int(h * r), int(w * r)
    dw, dh = (IMGSZ - nw) / 2, (IMGSZ - nh) / 2
    dw, dh = dw % 32, dh % 32
    resized = img.resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGB", (IMGSZ, IMGSZ), (114, 114, 114))
    canvas.paste(resized, (int(dw), int(dh)))
    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    arr = np.transpose(arr, (2, 0, 1))[None, ...]
    return arr, (w, h), (r, dw, dh)


def postprocess(raw, img_w, img_h, r, dw, dh, conf_thres=0.25, iou_thres=0.45):
    if raw.ndim == 3:
        raw = raw[0]
    if raw.ndim == 2 and raw.shape[0] < raw.shape[1]:
        raw = raw.T

    boxes, scores = [], []
    for row in raw:
        cx, cy, bw, bh, obj = row[:5]
        if obj < conf_thres:
            continue
        x1 = (cx - bw / 2 - dw) / r
        y1 = (cy - bh / 2 - dh) / r
        x2 = (cx + bw / 2 - dw) / r
        y2 = (cy + bh / 2 - dh) / r
        x1, x2 = max(0, min(img_w, x1)), max(0, min(img_w, x2))
        y1, y2 = max(0, min(img_h, y1)), max(0, min(img_h, y2))
        if x2 > x1 and y2 > y1:
            boxes.append([x1, y1, x2, y2])
            scores.append(float(obj))

    if not boxes:
        return np.zeros((0, 4)), np.zeros(0)

    boxes = np.array(boxes)
    scores = np.array(scores)
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]; keep.append(i)
        if order.size == 1: break
        xx1 = np.maximum(boxes[i, 0], boxes[order[1:], 0])
        yy1 = np.maximum(boxes[i, 1], boxes[order[1:], 1])
        xx2 = np.minimum(boxes[i, 2], boxes[order[1:], 2])
        yy2 = np.minimum(boxes[i, 3], boxes[order[1:], 3])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        area_i = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        area_j = (boxes[order[1:], 2] - boxes[order[1:], 0]) * \
                 (boxes[order[1:], 3] - boxes[order[1:], 1])
        iou = inter / (area_i + area_j - inter + 1e-8)
        order = order[1:][iou < iou_thres]
    return boxes[keep], scores[keep]


def load_yolo_label(path, iw, ih):
    if not os.path.isfile(path):
        return np.zeros((0, 4))
    boxes = []
    with open(path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 5: continue
            _, cx, cy, bw, bh = map(float, parts[:5])
            boxes.append([(cx-bw/2)*iw, (cy-bh/2)*ih,
                          (cx+bw/2)*iw, (cy+bh/2)*ih])
    return np.array(boxes) if boxes else np.zeros((0, 4))


def compute_iou(pred_boxes, gt_boxes):
    if len(pred_boxes) == 0 or len(gt_boxes) == 0:
        return 0.0
    iou_mat = np.zeros((len(pred_boxes), len(gt_boxes)))
    for i, pb in enumerate(pred_boxes):
        for j, gb in enumerate(gt_boxes):
            xx1 = max(pb[0], gb[0]); yy1 = max(pb[1], gb[1])
            xx2 = min(pb[2], gb[2]); yy2 = min(pb[3], gb[3])
            inter = max(0, xx2 - xx1) * max(0, yy2 - yy1)
            area_p = (pb[2]-pb[0])*(pb[3]-pb[1])
            area_g = (gb[2]-gb[0])*(gb[3]-gb[1])
            union = area_p + area_g - inter
            iou_mat[i, j] = inter / union if union > 0 else 0
    return iou_mat


def evaluate(session, test_images, device="CPU"):
    """跑完整评测，返回 Precision/Recall/平均延迟。"""
    input_name = session.get_inputs()[0].name
    latencies = []
    total_gt = total_tp = total_fp = 0

    # 预热
    warmup = np.zeros((1, 3, IMGSZ, IMGSZ), dtype=np.float32)
    for _ in range(3):
        session.run(None, {input_name: warmup})

    for img_path in test_images:
        arr, (iw, ih), (r, dw, dh) = preprocess(img_path)
        t0 = time.perf_counter()
        out = session.run(None, {input_name: arr})[0]
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000)

        pred_boxes, pred_scores = postprocess(out, iw, ih, r, dw, dh, 0.25, 0.45)
        label_path = os.path.join(TEST_IMAGES.replace("images", "labels"),
                                  os.path.splitext(os.path.basename(img_path))[0] + ".txt")
        gt_boxes = load_yolo_label(label_path, iw, ih)

        total_gt += len(gt_boxes)
        if len(gt_boxes) == 0:
            total_fp += len(pred_boxes)
            continue

        iou_mat = compute_iou(pred_boxes, gt_boxes)
        matched_gt = set()
        for pi in range(len(pred_boxes)):
            best_gi, best_iou = -1, 0
            for gi in range(len(gt_boxes)):
                if gi not in matched_gt and iou_mat[pi, gi] > 0.5 and iou_mat[pi, gi] > best_iou:
                    best_gi, best_iou = gi, iou_mat[pi, gi]
            if best_gi != -1:
                matched_gt.add(best_gi); total_tp += 1
            else:
                total_fp += 1

    prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0
    rec = total_tp / total_gt if total_gt else 0
    lat = np.array(latencies)
    return {"precision": prec, "recall": rec,
            "lat_ms_mean": float(lat.mean()),
            "lat_ms_p50": float(np.median(lat)),
            "fps": float(1000.0 / lat.mean()),
            "n_images": len(test_images)}


def main():
    print("=" * 60)
    print("ONNX FP32 vs INT8 动态量化 —— 精度 & 速度对比")
    print("=" * 60)

    # 1. 量化（如果没量化过）
    if not os.path.isfile(MODEL_INT8):
        quantize_dynamic(MODEL_FP32, MODEL_INT8)

    fp32_kb = os.path.getsize(MODEL_FP32) / 1024
    int8_kb = os.path.getsize(MODEL_INT8) / 1024

    print(f"\n📏 模型体积")
    print(f"  FP32:  {fp32_kb:.1f} KB")
    print(f"  INT8:  {int8_kb:.1f} KB")
    print(f"  压缩比: {fp32_kb / int8_kb:.2f}x")

    test_images = sorted(glob.glob(os.path.join(TEST_IMAGES, "*.jpg")))
    print(f"\n🔬 测试集: {len(test_images)} 张")

    # 2. FP32 评测
    print(f"\n{'─'*60}")
    print("📊 FP32 基线评测 (ONNX Runtime CPU)")
    sess_fp32 = ort.InferenceSession(MODEL_FP32, providers=["CPUExecutionProvider"])
    fp32 = evaluate(sess_fp32, test_images)
    print(f"  Precision: {fp32['precision']:.4f}")
    print(f"  Recall:    {fp32['recall']:.4f}")
    print(f"  平均延迟:   {fp32['lat_ms_mean']:.1f} ms/张")
    print(f"  P50延迟:    {fp32['lat_ms_p50']:.1f} ms")
    print(f"  FPS:        {fp32['fps']:.1f}")

    # 3. INT8 评测
    print(f"\n{'─'*60}")
    print("📊 INT8 动态量化评测 (ONNX Runtime CPU)")
    sess_int8 = ort.InferenceSession(MODEL_INT8, providers=["CPUExecutionProvider"])
    int8 = evaluate(sess_int8, test_images)
    print(f"  Precision: {int8['precision']:.4f}")
    print(f"  Recall:    {int8['recall']:.4f}")
    print(f"  平均延迟:   {int8['lat_ms_mean']:.1f} ms/张")
    print(f"  P50延迟:    {int8['lat_ms_p50']:.1f} ms")
    print(f"  FPS:        {int8['fps']:.1f}")

    # 4. 对比汇总
    print(f"\n{'='*60}")
    print("赛题一提交用对比表")
    print(f"{'='*60}")
    print(f"{'指标':<20} {'FP32':>12} {'INT8':>12} {'变化':>14}")
    print(f"{'-'*60}")
    delta = lambda a, b, suffix="": (b - a) / a * 100 if a != 0 else 0
    print(f"{'Precision':<20} {fp32['precision']:>12.4f} {int8['precision']:>12.4f}"
          f" {delta(fp32['precision'], int8['precision'], '%'):>+13.2f}%")
    print(f"{'Recall':<20} {fp32['recall']:>12.4f} {int8['recall']:>12.4f}"
          f" {delta(fp32['recall'], int8['recall'], '%'):>+13.2f}%")
    print(f"{'平均延迟(ms)':<20} {fp32['lat_ms_mean']:>12.1f} {int8['lat_ms_mean']:>12.1f}"
          f" {delta(fp32['lat_ms_mean'], int8['lat_ms_mean'], '%'):>+13.2f}%")
    print(f"{'FPS':<20} {fp32['fps']:>12.1f} {int8['fps']:>12.1f}"
          f" {delta(fp32['fps'], int8['fps'], '%'):>+13.2f}%")
    print(f"{'模型大小(KB)':<20} {fp32_kb:>12.1f} {int8_kb:>12.1f}"
          f" {delta(fp32_kb, int8_kb, '%'):>+13.2f}%")

    # 5. 推理后端理论加速比（边缘端硬件参考）
    print(f"\n{'='*60}")
    print("边缘端部署参考（理论值，非实测）")
    print(f"{'='*60}")
    print(f"  硬件              后端                    预期 FPS")
    print(f"  ────────────────────────────────────────────────────────────")
    print(f"  本机 i9-13900H    ONNX FP32 (当前)        {fp32['fps']:.1f}")
    print(f"  本机 i9-13900H    ONNX INT8 (当前)        {int8['fps']:.1f}")
    print(f"  Jetson Nano       TensorRT INT8           ~20-40")
    print(f"  Jetson Orin Nano  TensorRT INT8           ~80-120")
    print(f"  树莓派 5          ONNX INT8               ~5-10")

    out = {"fp32": fp32, "int8": int8,
           "model_kb": {"fp32": fp32_kb, "int8": int8_kb},
           "ort_version": ort.__version__}
    out_path = os.path.join(os.path.dirname(MODEL_FP32), "quant_compare.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n完整对比结果: {out_path}")


if __name__ == "__main__":
    main()
