# -*- coding: utf-8 -*-
"""ONNX 猪只检测器共享工具库。

提供：letterbox/preprocess/postprocess/NMS/load_yolo_label/compute_iou
      —— benchmark_onnx.py、quantize_int8.py、edge_infer.py 共用。

设计原则：零第三方依赖（除 numpy/PIL），绕开项目内的 pylibs（cp312 编译，
在 Python 3.14 下会崩），只用系统 site-packages 的 numpy/cv2/onnxruntime。
"""
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image


# ============================================================
# Letterbox + 预处理（把任意图片缩放到模型输入尺寸，保持长宽比）
# ============================================================
def letterbox(img_w, img_h, new_shape=640):
    """计算 letterbox 变换参数。

    返回 (r, dw, dh) —— r 是缩放比，dw/dh 是居中填充量（已对 32 对齐）。
    画布坐标 → 原图坐标的反变换：(cx - dw)/r, (cy - dh)/r
    """
    r = min(new_shape / img_h, new_shape / img_w)
    dw = (new_shape - img_w * r) / 2
    dh = (new_shape - img_h * r) / 2
    dw, dh = dw % 32, dh % 32  # 32 对齐
    return r, dw, dh


def preprocess_img(img: Image.Image, imgsz=640):
    """PIL Image → (1,3,H,W) float32 数组 + letterbox 参数 + 原图尺寸。

    返回：arr, (img_w, img_h), (r, dw, dh)
    """
    w, h = img.width, img.height
    r, dw, dh = letterbox(w, h, imgsz)
    nh, nw = int(h * r), int(w * r)
    resized = img.resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGB", (imgsz, imgsz), (114, 114, 114))
    canvas.paste(resized, (int(dw), int(dh)))
    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    arr = np.transpose(arr, (2, 0, 1))[None, ...]
    return arr, (w, h), (r, dw, dh)


def preprocess_cv2(frame_bgr: np.ndarray, imgsz=640):
    """OpenCV BGR 帧 → 与 preprocess_img 相同的输出。"""
    img_rgb = Image.fromarray(frame_bgr[:, :, ::-1])  # BGR → RGB
    return preprocess_img(img_rgb, imgsz)


# ============================================================
# YOLOv8 ONNX 输出解码 + NMS
# ============================================================
def postprocess(raw, img_w, img_h, r, dw, dh,
                conf_thres=0.25, iou_thres=0.45):
    """YOLOv8 ONNX 输出 → 检测框（像素坐标，原图尺度）+ 置信度。

    raw: ONNX 输出数组，shape 可能是 (1, 5, N) 或 (5, N) 或 (N, 5)
         其中 N = 8400 等锚点数量，5 = [cx, cy, bw, bh, obj_score]
    返回：(boxes Nx4, scores N) —— boxes 格式 [x1, y1, x2, y2]
    """
    # 归一化到 (N, 5)
    if raw.ndim == 3:
        raw = raw[0]
    if raw.ndim == 2 and raw.shape[0] < raw.shape[1]:
        raw = raw.T

    boxes, scores = [], []
    for row in raw:
        cx, cy, bw, bh, obj = row[:5]
        if obj < conf_thres:
            continue
        # 反 letterbox：画布 → 原图
        x1 = (cx - bw / 2 - dw) / r
        y1 = (cy - bh / 2 - dh) / r
        x2 = (cx + bw / 2 - dw) / r
        y2 = (cy + bh / 2 - dh) / r
        # 裁剪到原图边界
        x1, x2 = max(0, min(img_w, x1)), max(0, min(img_w, x2))
        y1, y2 = max(0, min(img_h, y1)), max(0, min(img_h, y2))
        if x2 > x1 and y2 > y1:
            boxes.append([float(x1), float(y1), float(x2), float(y2)])
            scores.append(float(obj))

    if not boxes:
        return np.zeros((0, 4), dtype=np.float32), np.zeros(0, dtype=np.float32)

    boxes = np.array(boxes, dtype=np.float32)
    scores = np.array(scores, dtype=np.float32)
    keep = _nms(boxes, scores, iou_thres)
    return boxes[keep], scores[keep]


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_thres: float):
    """贪心 NMS。boxes: (N,4) [x1,y1,x2,y2], scores: (N,)"""
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(boxes[i, 0], boxes[order[1:], 0])
        yy1 = np.maximum(boxes[i, 1], boxes[order[1:], 1])
        xx2 = np.minimum(boxes[i, 2], boxes[order[1:], 2])
        yy2 = np.minimum(boxes[i, 3], boxes[order[1:], 3])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        area_i = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        area_j = ((boxes[order[1:], 2] - boxes[order[1:], 0]) *
                  (boxes[order[1:], 3] - boxes[order[1:], 1]))
        iou = inter / (area_i + area_j - inter + 1e-8)
        order = order[1:][iou < iou_thres]
    return keep


# ============================================================
# 评测工具（benchmark / quantize 用）
# ============================================================
def load_yolo_label(label_path: str, img_w: int, img_h: int):
    """YOLO 格式标注文件 → 像素坐标 (N,4)。"""
    if not os.path.isfile(label_path):
        return np.zeros((0, 4), dtype=np.float32)
    boxes = []
    with open(label_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            _, cx, cy, bw, bh = map(float, parts[:5])
            x1 = (cx - bw / 2) * img_w
            y1 = (cy - bh / 2) * img_h
            x2 = (cx + bw / 2) * img_w
            y2 = (cy + bh / 2) * img_h
            boxes.append([x1, y1, x2, y2])
    return np.array(boxes, dtype=np.float32) if boxes else np.zeros((0, 4), dtype=np.float32)


def compute_iou_matrix(a: np.ndarray, b: np.ndarray):
    """a(N,4) vs b(M,4) → (N,M) IoU 矩阵。"""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)), dtype=np.float32)
    A = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    B = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    Iw = np.maximum(0, np.minimum(a[:, None, 2], b[None, :, 2]) -
                        np.maximum(a[:, None, 0], b[None, :, 0]))
    Ih = np.maximum(0, np.minimum(a[:, None, 3], b[None, :, 3]) -
                        np.maximum(a[:, None, 1], b[None, :, 1]))
    inter = Iw * Ih
    return inter / (A[:, None] + B[None, :] - inter + 1e-8)


def evaluate_accuracy(pred_boxes, gt_boxes, iou_threshold=0.5):
    """单图 Precision/Recall 评估。返回 (tp, fp, fn)。"""
    if len(gt_boxes) == 0 and len(pred_boxes) == 0:
        return 0, 0, 0
    if len(gt_boxes) == 0:
        return 0, len(pred_boxes), 0
    if len(pred_boxes) == 0:
        return 0, 0, len(gt_boxes)

    iou_mat = compute_iou_matrix(pred_boxes, gt_boxes)
    matched_gt = set()
    tp = 0
    fp = 0
    for pi in range(len(pred_boxes)):
        # 贪心：找未匹配 GT 中 IoU 最大且超过阈值的
        best_gi, best_iou = -1, 0.0
        for gi in range(len(gt_boxes)):
            if gi not in matched_gt and iou_mat[pi, gi] > iou_threshold:
                if iou_mat[pi, gi] > best_iou:
                    best_gi, best_iou = gi, float(iou_mat[pi, gi])
        if best_gi != -1:
            matched_gt.add(best_gi)
            tp += 1
        else:
            fp += 1
    fn = len(gt_boxes) - len(matched_gt)
    return tp, fp, fn


# ============================================================
# 行为规则（六类，可解释，轻量内联版，不 import behavior.py/scene.py）
# ============================================================
@dataclass
class DetectionBox:
    x1: float
    y1: float
    x2: float
    y2: float
    score: float

    @property
    def area(self):
        return max(0, self.x2 - self.x1) * max(0, self.y2 - self.y1)

    @property
    def cx(self):
        return (self.x1 + self.x2) / 2

    @property
    def cy(self):
        return (self.y1 + self.y2) / 2

    @property
    def aspect(self):
        w = max(1, self.x2 - self.x1)
        h = max(1, self.y2 - self.y1)
        return w / h

    def iou(self, other: "DetectionBox"):
        ix1 = max(self.x1, other.x1); iy1 = max(self.y1, other.y1)
        ix2 = min(self.x2, other.x2); iy2 = min(self.y2, other.y2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        union = self.area + other.area - inter
        return inter / union if union > 0 else 0.0


# 行为占比阈值（默认基线，须如实标注为"待现场标定"）
DEFAULT_BASELINE = {
    "eating": 10.0, "drinking": 4.0, "resting": 65.0,
    "standing": 8.0, "walking": 12.0, "aggressive": 1.0,
}
BASELINE_NOTE = ("⚠ 默认基线未经现场标定，不可作为临床判断依据。"
                 "部署后应采集本栏至少 3-7 天的数据建立自身基线。")


def infer_behavior_static(boxes: List[DetectionBox],
                          feeder_region=None, drinker_region=None) -> dict:
    """**单帧静态**行为推断（无时序信息，近似版）。

    六类行为优先级：采食 > 饮水 > 争斗 > 休息 > 站立。
    与 vision/behavior.py 规则一致但简化（单帧无时序）。

    feeder_region / drinker_region: (x1, y1, x2, y2) 像素坐标，可选。
    返回：{behavior: count, ..., distribution_pct: {...}, verdict: [...]}
    """
    verdict = []
    dist_count = {"eating": 0, "drinking": 0, "aggressive": 0,
                  "resting": 0, "standing": 0}

    for b in boxes:
        label, conf, note = "standing", 0.4, ""

        # 1. 采食：与食槽区域重叠 ≥ 0.35
        if feeder_region is not None:
            fx1, fy1, fx2, fy2 = feeder_region
            inter_w = max(0, min(b.x2, fx2) - max(b.x1, fx1))
            inter_h = max(0, min(b.y2, fy2) - max(b.y1, fy1))
            feeder_overlap = (inter_w * inter_h) / (b.area + 1e-8)
            if feeder_overlap >= 0.35:
                label = "eating"; conf = min(1.0, 0.55 + feeder_overlap * 0.45)
                note = f"与食槽重叠 {feeder_overlap:.2f} >= 0.35"
                dist_count["eating"] += 1
                verdict.append({"idx": len(verdict), "behavior": label,
                                "confidence": round(conf, 3), "note": note})
                continue

        # 2. 饮水：与饮水器区域重叠 ≥ 0.35
        if drinker_region is not None:
            dx1, dy1, dx2, dy2 = drinker_region
            inter_w = max(0, min(b.x2, dx2) - max(b.x1, dx1))
            inter_h = max(0, min(b.y2, dy2) - max(b.y1, dy1))
            drinker_overlap = (inter_w * inter_h) / (b.area + 1e-8)
            if drinker_overlap >= 0.35:
                label = "drinking"; conf = min(1.0, 0.55 + drinker_overlap * 0.45)
                note = f"与饮水器重叠 {drinker_overlap:.2f} >= 0.35"
                dist_count["drinking"] += 1
                verdict.append({"idx": len(verdict), "behavior": label,
                                "confidence": round(conf, 3), "note": note})
                continue

        # 3. 争斗：相邻框 IoU ≥ 0.35（静态保守阈值）
        for other in boxes:
            if other is b:
                continue
            iou_val = b.iou(other)
            if iou_val >= 0.35:
                label = "aggressive"; conf = min(1.0, 0.5 + iou_val)
                note = f"与相邻个体 IoU={iou_val:.3f} >= 0.35（静态保守阈值）"
                dist_count["aggressive"] += 1
                break

        if label == "standing":
            # 4. 休息 vs 站立：静态下靠宽高比（扁→卧姿）
            if b.aspect >= 1.5:
                label = "resting"; conf = 0.45
                note = f"宽高比 {b.aspect:.2f} >= 1.5，形态偏卧姿"
                dist_count["resting"] += 1
            else:
                dist_count["standing"] += 1

        verdict.append({"idx": len(verdict), "behavior": label,
                        "confidence": round(conf, 3), "note": note})

    total = sum(dist_count.values()) or 1
    dist_pct = {k: round(v * 100.0 / total, 1) for k, v in dist_count.items()}
    return {"distribution_count": dist_count, "distribution_pct": dist_pct,
            "total": total, "verdict": verdict}


# ============================================================
# SQLite 轻量封装（edge 端专用，零依赖 db/ 模块）
# ============================================================
def ensure_db(db_path):
    """确保数据库存在且初始化（只建核心表：detections + behavior_distributions + nodes）。"""
    import sqlite3
    first = not os.path.isfile(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    # 建表（幂等）
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS nodes (
            node_id TEXT PRIMARY KEY, node_type TEXT, location TEXT,
            pen_id TEXT, resolution_w INTEGER, resolution_h INTEGER,
            install_date TEXT, status TEXT DEFAULT 'active', firmware_ver TEXT,
            last_heartbeat TEXT);
        CREATE TABLE IF NOT EXISTS detections (
            det_id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL REFERENCES nodes(node_id),
            frame_timestamp TEXT NOT NULL, frame_seq INTEGER,
            image_width INTEGER, image_height INTEGER, pig_count INTEGER,
            boxes_json TEXT NOT NULL, model_ver TEXT, inference_ms REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS idx_det_node_time
            ON detections(node_id, frame_timestamp);
        CREATE TABLE IF NOT EXISTS behavior_distributions (
            dist_id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL REFERENCES nodes(node_id),
            pen_id TEXT, window_start TEXT, window_end TEXT, window_sec INTEGER,
            pct_eating REAL DEFAULT 0, pct_drinking REAL DEFAULT 0,
            pct_resting REAL DEFAULT 0, pct_standing REAL DEFAULT 0,
            pct_walking REAL DEFAULT 0, pct_aggressive REAL DEFAULT 0,
            total_animals REAL DEFAULT 0, total_frames INTEGER DEFAULT 0,
            avg_detections_per_frame REAL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS idx_bd_node_time
            ON behavior_distributions(node_id, window_start);
    """)
    if first:
        # 注册默认节点
        conn.execute(
            """INSERT OR IGNORE INTO nodes
               (node_id, node_type, location, resolution_w, resolution_h)
               VALUES (?, 'camera', ?, ?, ?)""",
            ("CAM-DEFAULT", "边缘端默认摄像头", 640, 360))
    conn.commit()
    conn.close()
    return db_path
