# -*- coding: utf-8 -*-
"""边缘端推理：摄像头/图片目录/视频 → ONNX 猪只检测 → 行为规则 → SQLite 写入。

用法：
  python edge_infer.py --source images --path data/pigdetect/extract/test/images
  python edge_infer.py --source video  --path pen.mp4
  python edge_infer.py --source camera --device 0

  # 全部参数（默认值就是开箱即用配置）
  python edge_infer.py \
      --source camera \
      --device 0 \
      --model models/pig-detector-yolov8n-int8.onnx \
      --imgsz 640 \
      --conf 0.25 \
      --node-id CAM-PEN-A01 \
      --db pigfarm.db \
      --window-sec 300 \
      --no-display          # Jetson 无显示时加这个
"""
import argparse, glob, json, os, sys, sqlite3, time
from datetime import datetime

import cv2
import numpy as np
import onnxruntime as ort

# 共享工具（绕开 pylibs，只用系统 site-packages）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from onnx_utils import (
    DetectionBox, preprocess_cv2, preprocess_img,
    postprocess, infer_behavior_static, ensure_db, BASELINE_NOTE
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INT8 = os.path.join(SCRIPT_DIR, "models", "pig-detector-yolov8n-int8.onnx")
DEFAULT_FP32 = os.path.join(SCRIPT_DIR, "models", "pig-detector-yolov8n.onnx")

ort.set_default_logger_severity(3)  # 静音日志
sys.stdout.reconfigure(encoding="utf-8")


def load_model(model_path, use_trt=False, providers=None):
    """加载 ONNX 模型。use_trt=True 时走 TensorRT 后端（Jetson 上可用）。"""
    if providers is None:
        if use_trt:
            providers = ["TensorrtExecutionProvider", "CPUExecutionProvider"]
        else:
            providers = ["CPUExecutionProvider"]
    sess = ort.InferenceSession(model_path, providers=providers)
    return sess, sess.get_inputs()[0].name


def draw_overlay(frame, boxes, scores, behavior_result, latency_ms, node_id):
    """把检测框 + 行为占比 + 延迟 画在帧上，用于实时展示。"""
    vis = frame.copy()
    # 检测框（绿色框 + 置信度）
    for b, s in zip(boxes, scores):
        x1, y1, x2, y2 = map(int, b)
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(vis, f"{s:.2f}", (x1, max(y1 - 6, 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

    # 右侧面板：延迟 + 行为占比
    dist = behavior_result.get("distribution_pct", {})
    total = behavior_result.get("total", 0)
    panel_w = 200
    vis = cv2.copyMakeBorder(vis, 0, 0, 0, panel_w,
                             cv2.BORDER_CONSTANT, value=(30, 30, 30))
    x0 = vis.shape[1] - panel_w + 10
    y = 25
    cv2.putText(vis, f"{node_id}", (x0, y), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (255, 255, 255), 1); y += 20
    cv2.putText(vis, f"Latency: {latency_ms:.1f} ms", (x0, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 200, 100), 1); y += 20
    cv2.putText(vis, f"Pigs: {total}", (x0, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 255, 100), 1); y += 25
    cv2.putText(vis, "--- Behavior ---", (x0, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1); y += 20
    name_map = {"eating": "EAT", "drinking": "DRINK", "resting": "REST",
                "standing": "STAND", "walking": "WALK", "aggressive": "FIGHT"}
    for bname in ["eating", "drinking", "aggressive", "resting", "standing"]:
        pct = dist.get(bname, 0)
        color = (0, 255, 255) if bname in ("aggressive",) else (200, 200, 200)
        bar_len = int(min(150, pct * 1.5))
        cv2.rectangle(vis, (x0, y - 14), (x0 + bar_len, y), color, -1)
        cv2.putText(vis, f"{name_map.get(bname, bname):<6} {pct:5.1f}%",
                    (x0, y - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        y += 22
    cv2.putText(vis, "ESC to quit", (x0, vis.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (150, 150, 150), 1)
    return vis


def batch_write_detections(conn, node_id, frames_data):
    """批量写 detections 表（高频帧，commit 一次）。"""
    rows = []
    for f in frames_data:
        rows.append((node_id, f["ts"], f["seq"],
                     f["img_w"], f["img_h"], f["pig_count"],
                     json.dumps(f["boxes_json"], ensure_ascii=False),
                     f.get("model_ver"), f.get("latency_ms")))
    conn.executemany(
        """INSERT INTO detections
           (node_id, frame_timestamp, frame_seq, image_width, image_height,
            pig_count, boxes_json, model_ver, inference_ms)
           VALUES (?,?,?,?,?,?,?,?,?)""", rows)


def write_behavior_dist(conn, node_id, window_start, window_end,
                        pcts, total_animals, total_frames, pen_id=None):
    """按时间窗口聚合的行为分布 → behavior_distributions 表。"""
    window_sec = int((datetime.fromisoformat(window_end) -
                      datetime.fromisoformat(window_start)).total_seconds())
    conn.execute(
        """INSERT INTO behavior_distributions
           (node_id, pen_id, window_start, window_end, window_sec,
            pct_eating, pct_drinking, pct_resting,
            pct_standing, pct_walking, pct_aggressive,
            total_animals, total_frames, avg_detections_per_frame)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (node_id, pen_id, window_start, window_end, window_sec,
         pcts.get("eating", 0), pcts.get("drinking", 0), pcts.get("resting", 0),
         pcts.get("standing", 0), pcts.get("walking", 0), pcts.get("aggressive", 0),
         total_animals, total_frames,
         total_animals / total_frames if total_frames else 0))


def run(args):
    print(f"{'='*60}")
    print(f"🐷 边缘端推理：{args.source} 模式")
    print(f"{'='*60}")

    # 1. 加载模型
    model_path = args.model or DEFAULT_INT8
    if not os.path.isfile(model_path):
        print(f"❌ 模型不存在: {model_path}")
        print(f"   尝试 FP32 默认路径: {DEFAULT_FP32}")
        model_path = DEFAULT_FP32
    sess, in_name = load_model(model_path, use_trt=args.use_trt)
    print(f"✅ 模型: {model_path} ({os.path.getsize(model_path)/1024:.1f} KB)")

    # 2. 初始化数据库
    ensure_db(args.db)
    conn = sqlite3.connect(args.db)
    print(f"✅ 数据库: {args.db}")

    # 3. 准备输入源
    frames_iter = _make_source_iter(args)
    if frames_iter is None:
        print("❌ 无法打开输入源")
        return

    # 4. 主循环
    print(f"\n🚀 开始推理（按 ESC 退出）...")
    print(f"   输入: {args.source}  窗口: {args.window_sec}s  阈值: conf={args.conf}")
    print(f"   {BASELINE_NOTE}\n")

    frame_seq = 0
    batch_buf = []                    # detections 批量缓冲（10帧一写）
    behavior_window = []              # 行为分布窗口（window_sec 聚合一次）
    window_start = datetime.now().isoformat(timespec="seconds")
    last_commit = time.time()
    total_frames_all = 0
    total_pigs_all = 0
    total_latency_ms = 0.0

    try:
        for frame_bgr in frames_iter:
            total_frames_all += 1
            frame_seq += 1
            h, w = frame_bgr.shape[:2]
            ts = datetime.now().isoformat(timespec="seconds")

            # ONNX 推理
            arr, (iw, ih), (r, dw, dh) = preprocess_cv2(frame_bgr, args.imgsz)
            t0 = time.perf_counter()
            out = sess.run(None, {in_name: arr})[0]
            latency_ms = (time.perf_counter() - t0) * 1000
            total_latency_ms += latency_ms

            # 解码 + NMS
            boxes, scores = postprocess(out, iw, ih, r, dw, dh,
                                        conf_thres=args.conf, iou_thres=0.45)
            det_boxes = [DetectionBox(float(b[0]), float(b[1]),
                                       float(b[2]), float(b[3]), float(s))
                         for b, s in zip(boxes, scores)]

            # 行为规则
            behavior = infer_behavior_static(det_boxes)

            # 缓冲（10帧批量写一次）
            boxes_json = [{"x1": float(b.x1), "y1": float(b.y1),
                           "x2": float(b.x2), "y2": float(b.y2),
                           "score": b.score, "label": "pig"}
                          for b in det_boxes]
            batch_buf.append({
                "ts": ts, "seq": frame_seq,
                "img_w": iw, "img_h": ih,
                "pig_count": len(det_boxes),
                "boxes_json": boxes_json,
                "model_ver": os.path.basename(model_path),
                "latency_ms": round(latency_ms, 1),
            })
            behavior_window.append({
                "timestamp": ts,
                "pig_count": len(det_boxes),
                "dist_pct": behavior.get("distribution_pct", {}),
            })
            total_pigs_all += len(det_boxes)

            # 每 10 帧批量写 detections
            if len(batch_buf) >= 10:
                batch_write_detections(conn, args.node_id, batch_buf)
                batch_buf = []

            # 每 window_sec 聚合写 behavior_distributions
            elapsed = (datetime.now() - datetime.fromisoformat(window_start)).total_seconds()
            if elapsed >= args.window_sec and behavior_window:
                # 聚合各行为占比（帧平均）
                n = len(behavior_window)
                agg = {"eating": 0.0, "drinking": 0.0, "resting": 0.0,
                       "standing": 0.0, "walking": 0.0, "aggressive": 0.0}
                for bw in behavior_window:
                    for k in agg:
                        agg[k] += bw["dist_pct"].get(k, 0)
                agg = {k: v / n for k, v in agg.items()}
                avg_pigs = sum(bw["pig_count"] for bw in behavior_window) / n
                window_end = datetime.now().isoformat(timespec="seconds")
                write_behavior_dist(conn, args.node_id, window_start, window_end,
                                    agg, avg_pigs, n, pen_id=args.pen_id)
                window_start = window_end
                behavior_window = []
                print(f"  📊 行为聚合写入: {n}帧, 平均{avg_pigs:.1f}头, "
                      f"EAT={agg['eating']:.1f}% REST={agg['resting']:.1f}% "
                      f"FIGHT={agg['aggressive']:.1f}%")

            # 画面显示
            if not args.no_display:
                vis = draw_overlay(frame_bgr, boxes, scores, behavior,
                                   latency_ms, args.node_id)
                cv2.imshow(f"Edge Inference ({args.source})", vis)
                key = cv2.waitKey(1) & 0xFF
                if key == 27 or key == ord('q'):  # ESC 或 q
                    break

    except KeyboardInterrupt:
        pass

    # 尾刷：剩余批量 + 剩余窗口
    if batch_buf:
        batch_write_detections(conn, args.node_id, batch_buf)
    if behavior_window:
        n = len(behavior_window)
        agg = {"eating": 0.0, "drinking": 0.0, "resting": 0.0,
               "standing": 0.0, "walking": 0.0, "aggressive": 0.0}
        for bw in behavior_window:
            for k in agg:
                agg[k] += bw["dist_pct"].get(k, 0)
        agg = {k: v / n for k, v in agg.items()}
        avg_pigs = sum(bw["pig_count"] for bw in behavior_window) / n
        window_end = datetime.now().isoformat(timespec="seconds")
        write_behavior_dist(conn, args.node_id, window_start, window_end,
                            agg, avg_pigs, n, pen_id=args.pen_id)
    conn.commit()
    conn.close()
    cv2.destroyAllWindows()

    # 汇总
    print(f"\n{'='*60}")
    print(f"🏁 完成")
    print(f"{'='*60}")
    print(f"  总帧数:       {total_frames_all}")
    print(f"  总检测头数:   {total_pigs_all}")
    avg_lat = total_latency_ms / max(total_frames_all, 1)
    print(f"  平均延迟:     {avg_lat:.1f} ms/张")
    print(f"  平均 FPS:     {1000.0/avg_lat:.1f}")
    print(f"  数据库:       {args.db}")
    if total_frames_all > 0:
        conn2 = sqlite3.connect(args.db)
        cnt_det = conn2.execute("SELECT COUNT(*) FROM detections WHERE node_id=?",
                                (args.node_id,)).fetchone()[0]
        cnt_bd = conn2.execute("SELECT COUNT(*) FROM behavior_distributions WHERE node_id=?",
                               (args.node_id,)).fetchone()[0]
        conn2.close()
        print(f"  detections 表:        {cnt_det} 行")
        print(f"  behavior_distributions: {cnt_bd} 行")


def _make_source_iter(args):
    """根据 --source 返回帧迭代器（yield BGR numpy array）。"""
    if args.source == "images":
        exts = ("*.jpg", "*.jpeg", "*.png", "*.bmp")
        files = []
        for e in exts:
            files += glob.glob(os.path.join(args.path, e))
        files = sorted(files)
        if not files:
            print(f"❌ 图片目录无文件: {args.path}")
            return None
        print(f"📁 图片模式: {len(files)} 张 → {args.path}")
        def gen():
            for fp in files:
                img = cv2.imread(fp)
                if img is not None:
                    yield img
        return gen()

    elif args.source == "video":
        cap = cv2.VideoCapture(args.path)
        if not cap.isOpened():
            print(f"❌ 视频无法打开: {args.path}")
            return None
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        print(f"🎬 视频模式: {n}帧, {fps:.1f} FPS → {args.path}")
        def gen():
            while True:
                ret, f = cap.read()
                if not ret: break
                yield f
            cap.release()
        return gen()

    elif args.source == "camera":
        cap = cv2.VideoCapture(args.device)
        if not cap.isOpened():
            print(f"❌ 摄像头无法打开 (device={args.device})")
            return None
        w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        print(f"📷 摄像头模式: device={args.device}, {int(w)}x{int(h)}")
        def gen():
            while True:
                ret, f = cap.read()
                if not ret: break
                yield f
            cap.release()
        return gen()

    print(f"❌ 未知 source: {args.source}（应为 camera / video / images）")
    return None


def main():
    p = argparse.ArgumentParser(description="边缘端 ONNX 推理 + 行为规则 + SQLite 入库")
    p.add_argument("--source", default="images",
                   choices=["camera", "video", "images"],
                   help="输入源类型（默认 images）")
    p.add_argument("--device", type=int, default=0,
                   help="摄像头编号（camera 模式，默认 0）")
    p.add_argument("--path", default=None,
                   help="视频文件路径 或 图片目录路径（video / images 模式）")
    p.add_argument("--model", default=DEFAULT_INT8,
                   help=f"ONNX 模型路径（默认 INT8: {DEFAULT_INT8}）")
    p.add_argument("--imgsz", type=int, default=640,
                   help="模型输入尺寸（默认 640）")
    p.add_argument("--conf", type=float, default=0.25,
                   help="置信度阈值（默认 0.25）")
    p.add_argument("--node-id", default="CAM-DEFAULT",
                   help="摄像头/节点 ID（写入数据库用）")
    p.add_argument("--pen-id", default=None,
                   help="关联栏舍 ID（可选）")
    p.add_argument("--db", default=os.path.join(SCRIPT_DIR, "edge_pigfarm.db"),
                   help="SQLite 数据库路径")
    p.add_argument("--window-sec", type=int, default=300,
                   help="行为聚合窗口秒数（默认 300 = 5分钟）")
    p.add_argument("--use-trt", action="store_true",
                   help="启用 TensorRT 后端（Jetson 上可用）")
    p.add_argument("--no-display", action="store_true",
                   help="无显示环境（Jetson 无屏幕时加）")
    args = p.parse_args()

    # 默认图片路径：用 PigBench 测试集（images 模式且没指定 --path 时）
    if args.source == "images" and args.path is None:
        args.path = r"E:/harness/aic/vision/data/pigdetect/extract/test/images"
    if args.source == "video" and args.path is None:
        p.error("--source video 必须指定 --path 视频文件")

    run(args)


if __name__ == "__main__":
    main()
