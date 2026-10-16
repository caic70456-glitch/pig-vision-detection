# -*- coding: utf-8 -*-
"""猪场视觉检测时序数据库 —— SQLite 封装层

设计要点：
  - SQLite 零配置，Jetson/树莓派上直接能跑
  - API 风格与 ORM 一致，但保持轻量（不引入 SQLAlchemy 依赖）
  - 所有对外返回 dict，便于 JSON 序列化给前端/边缘端

  数据流：
    ONNX推理 → insert_detection() 每帧写入
               ↓ (后台聚合任务)
             upsert_behavior_window() 按5分钟聚合
               ↓ (后台关联任务)
             与 environment_sensors JOIN → 行为+环境联合特征
               ↓
             可用于训练疫病风险预测模型（赛题二）或可视化大屏
"""
import json, os, sqlite3, time
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.environ.get("AIC_DB_PATH",
                         os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "pigfarm.db"))
INIT_SQL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "init_db.sql")


def init(db_path=None, force=False):
    """初始化数据库：建表 + 示例数据。force=True 时删除旧库重建。"""
    path = db_path or DB_PATH
    if force and os.path.isfile(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    with open(INIT_SQL, encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    return path


@contextmanager
def connect(db_path=None):
    path = db_path or DB_PATH
    if not os.path.isfile(path):
        init(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ========== 节点与栏舍 ==========
def register_node(node_id, location, pen_id=None,
                  resolution_w=1920, resolution_h=1080,
                  firmware_ver=None):
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO nodes
               (node_id, node_type, location, pen_id,
                resolution_w, resolution_h, install_date, firmware_ver, last_heartbeat)
               VALUES (?, 'camera', ?, ?, ?, ?, ?, ?, ?)""",
            (node_id, location, pen_id, resolution_w, resolution_h,
             now[:10], firmware_ver, now))


def register_pen(pen_id, pen_name, pig_count=None, pig_breed=None,
                 pig_age_days=None, pen_area_m2=None, stock_date=None, notes=None):
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO pens
               (pen_id, pen_name, pig_count, pig_breed, pig_age_days,
                pen_area_m2, stock_date, notes)
               VALUES (?,?,?,?,?,?,?,?)""",
            (pen_id, pen_name, pig_count, pig_breed, pig_age_days,
             pen_area_m2, stock_date, notes))


# ========== 检测结果 ==========
def insert_detection(node_id, frame_timestamp, frame_seq, image_size,
                     boxes, model_ver=None, inference_ms=None):
    """把一帧的检测结果写入 detections 表。

    boxes: list of dict [{x1,y1,x2,y2,score,label}]
    """
    w, h = image_size
    with connect() as conn:
        conn.execute(
            """INSERT INTO detections
               (node_id, frame_timestamp, frame_seq,
                image_width, image_height, pig_count,
                boxes_json, model_ver, inference_ms)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (node_id, frame_timestamp, frame_seq,
             w, h, len(boxes),
             json.dumps(boxes, ensure_ascii=False), model_ver, inference_ms))


def bulk_insert_detections(node_id, frames_list):
    """批量写入多帧检测结果（边缘端高频率上传场景）。

    frames_list: list of dicts，每个 dict 含
      frame_timestamp, frame_seq, image_size, boxes, model_ver, inference_ms
    """
    with connect() as conn:
        conn.executemany(
            """INSERT INTO detections
               (node_id, frame_timestamp, frame_seq,
                image_width, image_height, pig_count,
                boxes_json, model_ver, inference_ms)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            [(node_id, f["frame_timestamp"], f["frame_seq"],
              f["image_size"][0], f["image_size"][1], len(f["boxes"]),
              json.dumps(f["boxes"], ensure_ascii=False),
              f.get("model_ver"), f.get("inference_ms"))
             for f in frames_list])


# ========== 行为分布聚合 ==========
def upsert_behavior_window(node_id, window_start, window_end,
                           pcts, total_animals, total_frames,
                           pen_id=None):
    """按时间窗口聚合行为占比，写入 behavior_distributions 表。

    pcts: dict {eating: 10.0, drinking: 4.0, resting: 65.0, ...}
    """
    window_sec = int((datetime.fromisoformat(window_end) -
                      datetime.fromisoformat(window_start)).total_seconds())
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO behavior_distributions
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


def query_behavior(node_id=None, pen_id=None,
                   start=None, end=None, limit=100):
    """查询行为分布序列（返回 dict 列表，适合前端画图）。"""
    sql = "SELECT * FROM behavior_distributions WHERE 1=1"
    params = []
    if node_id:
        sql += " AND node_id = ?"; params.append(node_id)
    if pen_id:
        sql += " AND pen_id = ?"; params.append(pen_id)
    if start:
        sql += " AND window_start >= ?"; params.append(start)
    if end:
        sql += " AND window_end <= ?"; params.append(end)
    sql += " ORDER BY window_start DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


# ========== 环境传感器 ==========
def insert_environment(node_id, timestamp,
                       temperature_c=None, humidity_pct=None,
                       nh3_ppm=None, co2_ppm=None, light_lux=None,
                       noise_db=None, sensor_id=None):
    with connect() as conn:
        conn.execute(
            """INSERT INTO environment_sensors
               (node_id, timestamp, temperature_c, humidity_pct,
                nh3_ppm, co2_ppm, light_lux, noise_db, sensor_id)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (node_id, timestamp, temperature_c, humidity_pct,
             nh3_ppm, co2_ppm, light_lux, noise_db, sensor_id))


# ========== 疫病风险标签 ==========
def insert_disease_label(pen_id, timestamp, risk_level,
                         disease_type=None, severity=None,
                         reporter=None, notes=None, source="manual",
                         linked_window=None):
    with connect() as conn:
        conn.execute(
            """INSERT INTO disease_risk_labels
               (pen_id, timestamp, risk_level, disease_type, severity,
                reporter, notes, source, linked_window)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (pen_id, timestamp, risk_level, disease_type, severity,
             reporter, notes, source, linked_window))


# ========== 系统配置 ==========
def get_config(key, default=None):
    with connect() as conn:
        row = conn.execute(
            "SELECT cfg_value FROM system_config WHERE cfg_key = ?", (key,)).fetchone()
    return row["cfg_value"] if row else default


def set_config(key, value):
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute(
            """INSERT INTO system_config (cfg_key, cfg_value, updated_at)
               VALUES (?,?,?)
               ON CONFLICT(cfg_key) DO UPDATE SET cfg_value=excluded.cfg_value,
                                                   updated_at=excluded.updated_at""",
            (key, str(value), now))


# ========== 演示：把 ONNX benchmark 结果写入数据库 ==========
def demo_insert():
    """把 benchmkark_onnx.py 输出的 benchmark_result.json 写入数据库。"""
    init(force=True)
    register_node("CAM-A01", "猪舍1栋A区摄像头", pen_id="PEN-01",
                  resolution_w=640, resolution_h=360, firmware_ver="pigdet-yolov8n-v1")

    # 模拟 80 帧检测结果（对应 80 张测试图）
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "vision", "models", "benchmark_result.json"),
              encoding="utf-8") as f:
        bench = json.load(f)

    frames = []
    for i in range(80):
        # 模拟：单帧检测结果（实际应来自 pipeline 推理）
        boxes = []
        for _ in range(20):  # 假设平均20头
            import random
            x1, y1 = random.randint(0, 500), random.randint(0, 250)
            x2, y2 = x1 + random.randint(30, 120), y1 + random.randint(25, 100)
            boxes.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2,
                          "score": round(random.uniform(0.5, 0.95), 3),
                          "label": "pig"})
        frames.append({
            "frame_timestamp": f"2026-10-14T09:{i:02d}:00.000",
            "frame_seq": i + 1,
            "image_size": (640, 360),
            "boxes": boxes,
            "model_ver": "pig-detector-yolov8n",
            "inference_ms": round(random.uniform(220, 280), 1),
        })
    bulk_insert_detections("CAM-A01", frames)
    print(f"✅ 批量写入 {len(frames)} 帧检测结果")

    # 聚合行为分布（5分钟窗口）
    upsert_behavior_window(
        "CAM-A01", "2026-10-14T09:00:00", "2026-10-14T09:05:00",
        pcts={"eating": 12.5, "drinking": 5.2, "resting": 62.0,
              "standing": 8.3, "walking": 10.0, "aggressive": 2.0},
        total_animals=24, total_frames=80, pen_id="PEN-01")
    print("✅ 写入行为分布")

    # 环境传感器
    insert_environment("CAM-A01", "2026-10-14T09:02:00",
                       temperature_c=26.5, humidity_pct=68.2,
                       nh3_ppm=8.5, co2_ppm=1250, light_lux=320,
                       sensor_id="SENS-A01")
    print("✅ 写入环境传感器数据")

    # 风险标签（正常）
    insert_disease_label("PEN-01", "2026-10-14T09:05:00", risk_level="normal",
                         reporter="系统自动", source="model_predicted")
    print("✅ 写入风险标签")

    # 查询验证
    behaviors = query_behavior(pen_id="PEN-01", limit=10)
    print(f"\n📋 查询验证：")
    print(f"   behavior_distributions: {len(behaviors)} 条")

    with connect() as conn:
        cnt = conn.execute("SELECT COUNT(*) as c FROM detections").fetchone()["c"]
        env = conn.execute("SELECT * FROM environment_sensors").fetchone()
        print(f"   detections: {cnt} 帧")
        print(f"   env_sensor: {dict(env)}")

    print(f"\n💾 数据库位置: {DB_PATH}")


if __name__ == "__main__":
    init(force=True)
    demo_insert()
