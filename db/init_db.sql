-- ============================================================================
-- 猪场视觉检测时序数据库 —— SQLite 轻量版
-- 用途：边缘摄像头检测结果入库 / 行为分布统计 / 环境参数关联 / 疫病风险标签
-- 设计原则：可直接在树莓派/Jetson 上跑（SQLite 零配置），同时可迁移到 MySQL 生产库
--
-- 技术方案里要写的故事线：
--   摄像头(边缘端) → ONNX 推理 → 检测结果(每帧) → 聚合行为分布(每分钟)
--   → 与环境参数(温度/湿度/氨气)关联 → 写入数据库 → 异常预警
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- 1. 摄像头 / 栏舍节点表（注册硬件）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nodes (
    node_id         TEXT PRIMARY KEY,          -- 摄像头唯一ID，如 CAM-A01
    node_type       TEXT NOT NULL,             -- 'camera' / 'edge_compute'
    location        TEXT NOT NULL,             -- 位置描述，如 "猪舍1栋A区3号栏"
    pen_id          TEXT,                      -- 关联栏舍ID
    resolution_w    INTEGER DEFAULT 1920,
    resolution_h    INTEGER DEFAULT 1080,
    install_date    TEXT,                      -- YYYY-MM-DD
    status          TEXT DEFAULT 'active',     -- active / offline / maintenance
    firmware_ver    TEXT,
    last_heartbeat  TEXT                       -- ISO时间戳
);

CREATE TABLE IF NOT EXISTS pens (
    pen_id          TEXT PRIMARY KEY,
    pen_name        TEXT NOT NULL,
    pig_count       INTEGER,                   -- 当前存栏数
    pig_breed       TEXT,
    pig_age_days    INTEGER,
    pen_area_m2     REAL,
    stock_date      TEXT,
    notes           TEXT
);

-- ----------------------------------------------------------------------------
-- 2. 检测原始结果表（每帧检测框）
--    边缘端 ONNX 推理完成后直接 INSERT。高频写入。
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS detections (
    det_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id         TEXT NOT NULL REFERENCES nodes(node_id),
    frame_timestamp TEXT NOT NULL,             -- ISO时间戳，如 2026-10-14T08:30:00.123
    frame_seq       INTEGER,                   -- 帧序号（同node_id内单调递增）
    image_width     INTEGER,
    image_height    INTEGER,
    pig_count       INTEGER,                   -- 本帧检出猪数
    -- 检测框列表：JSON 字符串。每元素 {x1,y1,x2,y2,score,label}
    boxes_json      TEXT NOT NULL,
    model_ver       TEXT,                      -- 如 'pig-detector-yolov8n'
    inference_ms    INTEGER,                   -- 本次推理耗时
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_det_node_time ON detections(node_id, frame_timestamp);
-- 注：跨表 JOIN 条件（detections.node_id → nodes.pen_id）不在此建索引，运行时 SQLite 会自动优化

-- ----------------------------------------------------------------------------
-- 3. 行为分布时序表（按时间窗口聚合后的统计）
--    由后端后台任务从 detections 聚合，窗口大小通常 60秒 / 5分钟 / 1小时
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS behavior_distributions (
    dist_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id         TEXT NOT NULL REFERENCES nodes(node_id),
    pen_id          TEXT REFERENCES pens(pen_id),
    window_start    TEXT NOT NULL,             -- 窗口起始 ISO时间
    window_end      TEXT NOT NULL,             -- 窗口结束 ISO时间
    window_sec      INTEGER NOT NULL,          -- 窗口大小（秒）
    -- 各行为占比（0-100%，合计≈100）
    pct_eating      REAL DEFAULT 0,
    pct_drinking    REAL DEFAULT 0,
    pct_resting     REAL DEFAULT 0,
    pct_standing    REAL DEFAULT 0,
    pct_walking     REAL DEFAULT 0,
    pct_aggressive  REAL DEFAULT 0,
    -- 辅助统计
    total_animals   REAL DEFAULT 0,            -- 时间窗内平均观测猪数
    total_frames    INTEGER DEFAULT 0,         -- 聚合的帧数
    avg_detections_per_frame REAL DEFAULT 0,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bd_node_time
    ON behavior_distributions(node_id, window_start);
CREATE INDEX IF NOT EXISTS idx_bd_pen_time
    ON behavior_distributions(pen_id, window_start);

-- ----------------------------------------------------------------------------
-- 4. 环境传感器表（外部/边缘端接入）
--    与 behavior_distributions 通过 node_id + 时间窗口关联
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS environment_sensors (
    env_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id         TEXT NOT NULL REFERENCES nodes(node_id),
    timestamp       TEXT NOT NULL,
    temperature_c   REAL,                      -- 舍温 °C
    humidity_pct    REAL,                      -- 相对湿度 %
    nh3_ppm         REAL,                      -- 氨气浓度 ppm
    co2_ppm         REAL,                      -- CO₂ ppm
    light_lux       REAL,                      -- 光照强度 lux
    noise_db        REAL,                      -- 环境噪声 dB
    sensor_id       TEXT,                      -- 对应物理传感器编号
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_env_node_time
    ON environment_sensors(node_id, timestamp);

-- ----------------------------------------------------------------------------
-- 5. 疫病风险标签表（用于训练预测模型 + 现场记录对照）
--    生产中由兽医巡查 / 养殖系统录入，与 behaviors 通过 pen_id+时间关联
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS disease_risk_labels (
    label_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    pen_id          TEXT NOT NULL REFERENCES pens(pen_id),
    timestamp       TEXT NOT NULL,
    risk_level      TEXT NOT NULL,             -- normal / watch / alert / confirmed
    disease_type    TEXT,                      -- 如 'PED' 'ASF' '支原体肺炎'
    severity        INTEGER,                   -- 1-5
    reporter        TEXT,                      -- 录入人（兽医/养殖员）
    notes           TEXT,
    source          TEXT DEFAULT 'manual',     -- manual / model_predicted / system_alert
    -- 关联的行为/环境窗口起始时间（用于模型输入对齐）
    linked_window   TEXT
);
CREATE INDEX IF NOT EXISTS idx_drl_pen_time
    ON disease_risk_labels(pen_id, timestamp);

-- ----------------------------------------------------------------------------
-- 6. 系统配置表
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_config (
    cfg_key    TEXT PRIMARY KEY,
    cfg_value  TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO system_config (cfg_key, cfg_value) VALUES
    ('behavior_window_sec', '300'),          -- 行为聚合窗口 5分钟
    ('inference_conf_threshold', '0.25'),
    ('inference_iou_nms', '0.45'),
    ('health_baseline_eating', '10.0'),      -- 默认基线（未标定，须如实标注）
    ('health_baseline_drinking', '4.0'),
    ('health_baseline_resting', '65.0'),
    ('health_baseline_standing', '8.0'),
    ('health_baseline_walking', '12.0'),
    ('health_baseline_aggressive', '1.0');

-- ============================================================================
-- 初始化示例数据（演示用）
-- ============================================================================
INSERT OR IGNORE INTO pens VALUES
    ('PEN-01', '猪舍1栋A区1栏', 24, '大白猪', 120, 12.0, '2026-07-15', '正常');
INSERT OR IGNORE INTO nodes VALUES
    ('CAM-A01', 'camera', '猪舍1栋A区摄像头', 'PEN-01', 1920, 1080,
     '2026-08-01', 'active', 'v1.2.0', '2026-10-14T09:00:00');
