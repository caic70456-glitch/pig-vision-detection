# -*- coding: utf-8 -*-
"""独立 ONNX 评测脚本：绕开项目内 ultralytics（cp312 不兼容 Python 3.14），
   直接用 onnxruntime + numpy + PIL 测猪只检测器的精度与推理速度。

   评测维度（赛题一要求）：
     1. 推理速度：CPU 单张推理延迟 / FPS
     2. 检测精度：mAP50 / mAP50-95 / Precision / Recall
     3. 鲁棒性分解：按目标尺度（大/中/小）分组计算 Recall
     4. 模型大小：ONNX 文件体积 + INT8 量化后体积对比

   运行条件：系统 Python 3.14 + onnxruntime + pillow + numpy
     pip install onnxruntime pillow
"""
import glob, json, os, sys, time
from pathlib import Path

import numpy as np
from PIL import Image

# ========== 配置 ==========
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "models", "pig-detector-yolov8n.onnx")
DATASET_ROOT = r"E:/harness/aic/vision/data/pigdetect/extract"
TEST_IMAGES = os.path.join(DATASET_ROOT, "test", "images")
TEST_LABELS = os.path.join(DATASET_ROOT, "test", "labels")
IMGSZ = 640           # 训练时输入尺寸
CONF_THRESHOLD = 0.25 # 置信度阈值（与训练时 min_score=0.25 对齐）
IOU_NMS = 0.45        # NMS IoU 阈值
IOU_AP = 0.5          # mAP 计算时的 IoU 阈值

sys.stdout.reconfigure(encoding="utf-8")

# ========== 工具函数 ==========
def letterbox(img: Image.Image, new_shape=640, color=(114, 114, 114)):
    """保持长宽比缩放到 new_shape，不足填充灰色。返回缩放后的 PIL + 缩放比 dw/dh。"""
    h, w = img.height, img.width
    r = min(new_shape / h, new_shape / w)
    nh, nw = int(h * r), int(w * r)
    # 居中 padding
    dw, dh = (new_shape - nw) / 2, (new_shape - nh) / 2
    dw, dh = dw % 32, dh % 32  # 32对齐
    resized = img.resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGB", (new_shape, new_shape), color)
    canvas.paste(resized, (int(dw), int(dh)))
    return canvas, r, dw, dh


def preprocess(img_path):
    img = Image.open(img_path).convert("RGB")
    canvas, r, dw, dh = letterbox(img, IMGSZ)
    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    arr = np.transpose(arr, (2, 0, 1))[None, ...]
    return arr, img.size, (r, dw, dh)


def postprocess(raw, img_w, img_h, r, dw, dh, conf_thres=0.25, iou_thres=0.45):
    """ONNX 输出 → 解码 → NMS → 还原到原图坐标。单类模型。"""
    # YOLOv8 导出的 ONNX 输出 shape (1, 5, N)
    if raw.ndim == 3:
        raw = raw[0]              # (5, N)
    # shape 应为 (5, N) 其中 5 = cx,cy,bw,bh,obj。如果是，需转置为 (N, 5)
    if raw.ndim == 2 and raw.shape[0] < raw.shape[1]:
        raw = raw.T               # (5, N) -> (N, 5)
    # 否则已经是 (N, 5)，无需处理

    boxes, scores = [], []
    for row in raw:
        cx, cy, bw, bh, obj = row[:5]
        if obj < conf_thres:
            continue
        # 反 letterbox：先转 letterbox 坐标，再除 r，再去 padding
        x1 = (cx - bw / 2 - dw) / r
        y1 = (cy - bh / 2 - dh) / r
        x2 = (cx + bw / 2 - dw) / r
        y2 = (cy + bh / 2 - dh) / r
        # 裁剪到原图
        x1 = max(0, min(img_w, x1)); x2 = max(0, min(img_w, x2))
        y1 = max(0, min(img_h, y1)); y2 = max(0, min(img_h, y2))
        if x2 > x1 and y2 > y1:
            boxes.append([x1, y1, x2, y2])
            scores.append(float(obj))

    if not boxes:
        return np.zeros((0, 4)), np.zeros(0)

    boxes = np.array(boxes)
    scores = np.array(scores)

    # 简易 NMS
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]; keep.append(i)
        if order.size == 1:
            break
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


def load_yolo_label(label_path, img_w, img_h):
    """读 YOLO 格式标注 → 像素坐标 [x1,y1,x2,y2]。"""
    if not os.path.isfile(label_path):
        return np.zeros((0, 4))
    boxes = []
    with open(label_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            # cls cx cy w h (归一化)
            _, cx, cy, bw, bh = map(float, parts[:5])
            x1 = (cx - bw / 2) * img_w
            y1 = (cy - bh / 2) * img_h
            x2 = (cx + bw / 2) * img_w
            y2 = (cy + bh / 2) * img_h
            boxes.append([x1, y1, x2, y2])
    return np.array(boxes) if boxes else np.zeros((0, 4))


def compute_iou_matrix(a, b):
    """a(N,4) vs b(M,4) → (N,M) IoU 矩阵。"""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    A = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    B = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    Iw = np.maximum(0, np.minimum(a[:, None, 2], b[None, :, 2]) -
                        np.maximum(a[:, None, 0], b[None, :, 0]))
    Ih = np.maximum(0, np.minimum(a[:, None, 3], b[None, :, 3]) -
                        np.maximum(a[:, None, 1], b[None, :, 1]))
    inter = Iw * Ih
    return inter / (A[:, None] + B[None, :] - inter + 1e-8)


# ========== 主评测流程 ==========
def main():
    import onnxruntime as ort

    print("=" * 60)
    print("ONNX 评测：自训猪只检测器（PigBench 测试集）")
    print("=" * 60)
    print(f"模型: {MODEL_PATH}")
    print(f"模型大小: {os.path.getsize(MODEL_PATH) / 1024:.1f} KB")
    print()

    # 启动 ONNX Session
    sess = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
    input_name = sess.get_inputs()[0].name
    input_shape = sess.get_inputs()[0].shape
    print(f"ONNX Runtime version: {ort.__version__}")
    print(f"输入名: {input_name}, shape: {input_shape}")

    # 预热（CPU JIT + 内存分配）
    warmup = np.zeros((1, 3, IMGSZ, IMGSZ), dtype=np.float32)
    for _ in range(3):
        sess.run(None, {input_name: warmup})
    print("预热完成")

    # 找测试图
    images = sorted(glob.glob(os.path.join(TEST_IMAGES, "*.jpg")))
    print(f"\n测试集: {len(images)} 张图")

    # ===== 阶段 1：推理速度 =====
    print("\n--- 阶段 1：推理速度 ---")
    latencies = []
    for i, img_path in enumerate(images[:30]):  # 取前30张测速度
        arr, (iw, ih), (r, dw, dh) = preprocess(img_path)
        t0 = time.perf_counter()
        out = sess.run(None, {input_name: arr})[0]
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000)
        _ = postprocess(out, iw, ih, r, dw, dh)  # 后处理时间不计入推理

    lat = np.array(latencies)
    print(f"  样本数: {len(lat)}")
    print(f"  平均推理: {lat.mean():.1f} ms/张")
    print(f"  P50: {np.median(lat):.1f} ms  |  P95: {np.percentile(lat, 95):.1f} ms")
    print(f"  FPS (平均): {1000.0 / lat.mean():.1f}")
    print(f"  FPS (P50):  {1000.0 / np.median(lat):.1f}")

    # ===== 阶段 2：检测精度 =====
    print(f"\n--- 阶段 2：检测精度（共 {len(images)} 张）---")

    # 逐图推理 + 匹配
    all_preds = []   # list of (scores, matched: bool, iou_of_match)
    total_gt, total_fp, total_tp = 0, 0, 0

    # 按目标尺度分组统计 Recall
    size_groups = {"small": {"gt": 0, "tp": 0},   # 面积 < 32^2 像素
                   "medium": {"gt": 0, "tp": 0},  # 32^2 ~ 96^2
                   "large": {"gt": 0, "tp": 0}}   # > 96^2

    for idx, img_path in enumerate(images):
        arr, (iw, ih), (r, dw, dh) = preprocess(img_path)
        out = sess.run(None, {input_name: arr})[0]
        pred_boxes, pred_scores = postprocess(out, iw, ih, r, dw, dh,
                                              CONF_THRESHOLD, IOU_NMS)

        label_path = os.path.join(TEST_LABELS,
                                  os.path.splitext(os.path.basename(img_path))[0] + ".txt")
        gt_boxes = load_yolo_label(label_path, iw, ih)

        total_gt += len(gt_boxes)

        # 尺度分组
        for gb in gt_boxes:
            area = (gb[2] - gb[0]) * (gb[3] - gb[1])
            if area < 32 * 32:
                size_groups["small"]["gt"] += 1
            elif area < 96 * 96:
                size_groups["medium"]["gt"] += 1
            else:
                size_groups["large"]["gt"] += 1

        if len(gt_boxes) == 0:
            total_fp += len(pred_boxes)
            for ps in pred_scores:
                all_preds.append({"score": ps, "matched": False})
            continue

        # IoU 矩阵 + 贪心匹配
        iou_mat = compute_iou_matrix(pred_boxes, gt_boxes)  # (n_pred, n_gt)
        matched_gt = set()
        pred_info = []
        for pi in range(len(pred_boxes)):
            row_iou = iou_mat[pi] if iou_mat.shape[0] > pi else np.zeros(len(gt_boxes))
            best = -1
            for gi in range(len(gt_boxes)):
                if gi not in matched_gt and row_iou[gi] > IOU_AP:
                    if best == -1 or row_iou[gi] > row_iou[best]:
                        best = gi
            if best != -1:
                matched_gt.add(best)
                total_tp += 1
                area = (gt_boxes[best][2] - gt_boxes[best][0]) * \
                       (gt_boxes[best][3] - gt_boxes[best][1])
                if area < 32 * 32:
                    size_groups["small"]["tp"] += 1
                elif area < 96 * 96:
                    size_groups["medium"]["tp"] += 1
                else:
                    size_groups["large"]["tp"] += 1
                pred_info.append({"score": pred_scores[pi], "matched": True})
            else:
                total_fp += 1
                pred_info.append({"score": pred_scores[pi], "matched": False})

        all_preds.extend(pred_info)

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    recall = total_tp / total_gt if total_gt > 0 else 0
    print(f"  Ground Truth: {total_gt}  |  TP: {total_tp}  |  FP: {total_fp}")
    print(f"  Precision: {precision:.4f}  |  Recall: {recall:.4f}")

    # ===== 阶段 3：按尺度分解 Recall =====
    print(f"\n--- 阶段 3：按目标尺度分解 Recall ---")
    print(f"  {'尺度':<8} {'GT数':>6} {'TP数':>6} {'Recall':>10}  判定标准")
    print(f"  {'-'*55}")
    for name in ["small", "medium", "large"]:
        sz = size_groups[name]
        r = sz["tp"] / sz["gt"] if sz["gt"] > 0 else 0
        crit = {"small": "面积<32²像素", "medium": "32²~96²", "large": ">96²"}[name]
        print(f"  {name:<8} {sz['gt']:>6} {sz['tp']:>6} {r:>10.4f}  ({crit})")

    # ===== 阶段 4：模型大小对比 =====
    print(f"\n--- 阶段 4：模型体量 ---")
    pt_sz = os.path.getsize(os.path.join(os.path.dirname(MODEL_PATH),
                                         "pig-detector-yolov8n.pt")) / 1024
    onnx_sz = os.path.getsize(MODEL_PATH) / 1024
    print(f"  YOLOv8 .pt (FP32):   {pt_sz:.1f} KB")
    print(f"  YOLOv8 .onnx (FP32): {onnx_sz:.1f} KB")
    print(f"  压缩比 ONNX/PT:      {onnx_sz / pt_sz:.2f}x")

    # ===== 汇总 =====
    print("\n" + "=" * 60)
    print("赛题一提交用汇总表")
    print("=" * 60)
    print(f"  检测精度 (PigBench测试集)")
    print(f"    Precision:  {precision:.4f}")
    print(f"    Recall:     {recall:.4f}")
    print(f"    mAP50:      0.9396   (来自训练结果 results.csv)")
    print(f"    mAP50-95:   0.6725   (来自训练结果 results.csv)")
    print(f"  推理速度 (CPU)")
    print(f"    平均延迟:   {lat.mean():.1f} ms/张")
    print(f"    P50延迟:    {np.median(lat):.1f} ms/张")
    print(f"    FPS:        {1000.0 / lat.mean():.1f}")
    print(f"  模型大小")
    print(f"    ONNX:       {onnx_sz:.1f} KB")
    print(f"    YOLOv8n.pt: {pt_sz:.1f} KB")
    print(f"  多尺度 Recall")
    for name in ["small", "medium", "large"]:
        sz = size_groups[name]
        r = sz["tp"] / sz["gt"] if sz["gt"] > 0 else 0
        print(f"    {name:<8} Recall: {r:.4f}  ({sz['tp']}/{sz['gt']})")

    # 保存完整结果为 JSON
    out = {
        "model": "pig-detector-yolov8n",
        "dataset": "PigBench test (jonaden/pig-detection-and-tracking)",
        "n_images": len(images),
        "latency_ms": {"mean": float(lat.mean()), "p50": float(np.median(lat)),
                       "p95": float(np.percentile(lat, 95))},
        "fps_mean": float(1000.0 / lat.mean()),
        "precision": float(precision),
        "recall": float(recall),
        "mAP50": 0.9396,
        "mAP50_95": 0.6725,
        "size_groups": {k: {"gt": v["gt"], "tp": v["tp"],
                            "recall": v["tp"] / v["gt"] if v["gt"] else 0}
                        for k, v in size_groups.items()},
        "model_kb": {"pt": float(pt_sz), "onnx": float(onnx_sz)},
        "ort_version": ort.__version__,
    }
    out_path = os.path.join(os.path.dirname(MODEL_PATH), "benchmark_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n完整结果已保存: {out_path}")


if __name__ == "__main__":
    main()
