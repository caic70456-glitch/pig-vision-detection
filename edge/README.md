# 边缘端部署方案 —— 摄像头 + 单片机 + ONNX 推理

> **本方案采用零成本路线**：以**笔记本电脑**作为边缘端推理平台，传感器采集与执行机构控制交给低成本**单片机（ESP32/STM32）**。无需购买 Jetson 等高价开发板。

---

## 一、硬件方案

**核心思路**：赛题一评分的是「模型轻量化部署能力」，而非硬件档次。3.2MB 的 INT8 模型本身就是轻量化能力的证明。

### 主方案（推荐 · 零成本）

| 组件 | 型号 | 成本 | 说明 |
|---|---|---|---|
| **计算平台** | **杨轹文的笔记本电脑**（Windows/Linux） | **¥0** | 运行 ONNX Runtime INT8 推理，即"边缘端" |
| 摄像头 | USB 摄像头 或 笔记本自带摄像头 | ¥0 – 60 | 采集猪舍画面 |
| 传感器采集 | **ESP32 / STM32 单片机** | ¥20 – 60 | 温湿度、氨气等 |
| 执行机构 | 继电器模块 + 报警灯/蜂鸣器/风机 | ¥30 – 80 | 机电联动 |
| 供电/线材 | USB 供电 + 杜邦线 | ¥20 | — |
| **合计** | | **≈ ¥100 以内** | |

### 可选升级（预算允许时，非必需）

| 方案 | 硬件 | 成本 | 推理后端 | 预期 FPS | 适用场景 |
|---|---|---|---|---|---|
| **主方案** | **笔记本电脑 + USB 摄像头** | **¥0–60** | ONNX Runtime INT8 | **~4.4（实测）** | 演示/验证 |
| 可选B | 树莓派 5 + CSI 摄像头 | ¥500–800 | ONNX Runtime INT8 | ~5–10 | 独立嵌入式节点 |
| 可选C | RK3566 开发板（NPU） | ¥180 | RKNN INT8 | ~10–25 | 低成本 NPU |
| 采集端 | ESP32 + 摄像头模块 | ¥100 | **不跑 YOLO** | — | 传感器采集 + 执行机构 |

> **不选 Jetson 的理由**：Jetson Nano ¥1,200+ 且已停产；赛题评分不指定硬件，笔记本 + 单片机的组合更符合"农业低成本边缘计算"主题，答辩时"低成本落地"反而是加分点。

---

## 二、系统架构（边缘端 → 云端）

```
┌─────────────────────────────────────────────────────────────────┐
│                  边缘端（笔记本电脑 + 单片机）                    │
│  ┌────────┐    ┌──────────┐    ┌────────────┐    ┌────────────┐  │
│  │ USB/   │───▶│ ONNX INT8│───▶│ 行为规则    │───▶│ SQLite     │  │
│  │ 摄像头 │    │ 猪只检测 │    │ 六类行为    │    │ pigfarm.db │  │
│  └────────┘    └──────────┘    └────────────┘    └─────┬──────┘  │
│      (30fps)     (INT8 3MB)    (无训练，规则)    │              │
│                                                       │         │
│  ┌──────────┐    ┌────────────┐                       │         │
│  │ ESP32/ST │───▶│ 环境传感器  │                       │         │
│  │ 单片机   │    │ 接入       │                       │         │
│  └──────────┘    └────────────┘                       │         │
└────────────────────────────────────────────────────────┼─────────┘
                                                         │
                                                        WiFi/4G
                                                         │
┌────────────────────────────────────────────────────────▼─────────┐
│                    云端（可选，用于大屏/AI模型训练）                │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                     │
│  │ PostgreSQL│   │ Flask API│   │ 可视化大屏│                     │
│  └──────────┘    └──────────┘    └──────────┘                     │
└───────────────────────────────────────────────────────────────────┘
```

---

## 三、边缘端代码结构

```
edge/
├── edge_infer.py          # 核心循环：摄像头 → ONNX推理 → 行为规则 → 写DB
├── camera_stream.py       # 视频采集封装（OpenCV）
├── sensor_reader.py       # 温湿度/氨气传感器读取（单片机 ESP32/STM32）
├── actuator_control.py    # 机电联动控制（继电器 → 报警/通风）
├── db.py                  # 复用 db/ 目录的数据库封装
├── requirements.txt       # onnxruntime / opencv-python / pillow / numpy
└── README.md              # 本文件
```

---

## 四、笔记本端部署步骤（零成本，已验证）

```bash
# 1. 安装依赖（Windows/Linux 通用）
pip install onnxruntime opencv-python pillow numpy

# 2. 拷贝模型与脚本
#    模型：pig-detector-yolov8n-int8.onnx（3.2MB）
#    脚本：edge_infer.py, onnx_utils.py

# 3. 直接运行
python edge_infer.py --source camera --device 0        # USB 摄像头
python edge_infer.py --source video --path demo.mp4    # 视频文件
python edge_infer.py --source images --path ./test_images --no-display
```

**单片机侧（杨轹文）**：用 Arduino / PlatformIO 烧录 ESP32/STM32 固件，读取温湿度/氨气传感器，控制继电器驱动报警灯/风机；通过串口或 WiFi 把数据发给笔记本端的 `sensor_reader.py`。

---

## 五、核心推理循环（edge_infer.py 骨架）

```python
import time, sqlite3, json
import cv2, numpy as np
import onnxruntime as ort

ort.set_default_logger_severity(3)  # 静音日志

MODEL_PATH = "pig-detector-yolov8n-int8.onnx"
DB_PATH    = "pigfarm.db"
CAM_ID     = "CAM-PEN-A01"
FPS_TARGET = 10        # 推理帧率（不用摄像头满帧，降频节省算力）

sess = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
in_name = sess.get_inputs()[0].name

cap = cv2.VideoCapture(0)  # 0 = 默认摄像头
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)

conn = sqlite3.connect(DB_PATH)
frame_seq = 0
last_report = time.time()

while True:
    ret, frame = cap.read()
    if not ret: break

    # Letterbox + 归一化
    canvas, r, dw, dh = letterbox(frame, 640)
    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    arr = np.transpose(arr, (2, 0, 1))[None, ...]

    t0 = time.perf_counter()
    out = sess.run(None, {in_name: arr})[0]
    latency_ms = (time.perf_counter() - t0) * 1000

    # 后处理 + NMS（复用 benchmark_onnx.py 的 postprocess）
    boxes, scores = postprocess(out, frame.shape[1], frame.shape[0], r, dw, dh)

    # 写入数据库（每帧）
    frame_seq += 1
    conn.execute(
        "INSERT INTO detections(node_id, frame_timestamp, frame_seq, "
        "image_width, image_height, pig_count, boxes_json, "
        "model_ver, inference_ms) VALUES(?,?,?,?,?,?,?,?,?)",
        (CAM_ID, time.strftime("%Y-%m-%dT%H:%M:%S.")+str(frame_seq),
         frame_seq, 640, 360, len(boxes),
         json.dumps([{"x1":float(b[0]),"y1":float(b[1]),
                      "x2":float(b[2]),"y2":float(b[3]),
                      "score":float(s),"label":"pig"}
                     for b,s in zip(boxes,scores)], ensure_ascii=False),
         "pigdet-yolov8n-int8", round(latency_ms,1)))

    # 每 5 分钟聚合行为分布（后台定时任务）
    if time.time() - last_report > 300:
        conn.commit()  # 批量提交
        last_report = time.time()
```

---

## 六、关键设计决策

### 6.1 为什么是 ONNX 而不是 TensorFlow Lite / NCNN
- **ONNX 是行业标准**：任何硬件都能跑，模型从 PyTorch/YOLOv8 导出一步到位
- **动态量化零校准数据**：INT8 量化不需要额外数据集，量化后精度几乎无损（本项目实测：Precision 仅降 1.4%，Recall 还涨了 0.4%）
- **3.2MB INT8 模型**：普通笔记本 CPU 即可 4.4 FPS 实时运行；若升级到树莓派/RK3566，无需重新训练

### 6.2 为什么检测在边缘端、行为规则也在边缘端、SQLite 也在边缘端
- **延迟最低**：检测→行为→入库全在本地闭环，不依赖网络
- **断网可用**：猪圈常常网络差，边缘端必须自包含
- **云端可选**：后续要做大模型增强或可视化，把 SQLite 数据推送上去即可

### 6.3 数据库用 SQLite 而不是 MySQL/PostgreSQL
- **零配置**：`sqlite3 pigfarm.db` 直接创建，无需装服务
- **轻量**：单文件，占用 <1MB 起步
- **足够用**：每秒 10 帧 × 每帧 20 头猪，数据库完全扛得住

---

## 七、赛题一相关交付物清单

| 交付物 | 位置 | 赛题一评分维度 |
|---|---|---|
| 自训 YOLOv8n 猪只检测器 | vision/models/pig-detector-yolov8n.pt | 核心模型 |
| FP32 ONNX 导出 (11.7MB) | vision/models/pig-detector-yolov8n.onnx | 标准格式 |
| **INT8 量化 ONNX (3.2MB)** | vision/models/pig-detector-yolov8n-int8.onnx | **轻量化部署** |
| ONNX 评测脚本 | vision/benchmark_onnx.py | **精度/速度对比** |
| FP32 vs INT8 量化评测 | vision/quantize_int8.py | **轻量化优化** |
| 评测结果 JSON | vision/models/benchmark_result.json, quant_compare.json | 实验数据 |
| SQL 数据库 | db/pigfarm.db, init_db.sql, db.py | **工程化落地** |
| 边缘部署架构图 | edge/README.md | **边缘计算场景** |
| YOLOv8 训练指标 | vision/runs/pig_yolov8n/results.csv | mAP/PR 曲线 |
| 验证图集 (3批) | vision/runs/pig_yolov8n/val_batch*_*.jpg | 可视化 |

---

## 八、后续可提升方向（答辩加分项）

1. **升级到 NPU 板卡（可选）**：预算允许时买 RK3566（¥180），ONNX 转 RKNN 后 FPS 从 4.4 → 10–25
2. **多摄像头并行**：用多台笔记本或一台 RK3588 覆盖 2–4 个栏舍
3. **USB Coral TPU 加速**：Coral TPU（¥300 左右）在笔记本/树莓派上跑，理论加速 10x
4. **行为识别从规则升级为时序模型**：现有六类行为是可解释规则，后续可训练 LSTM/TCN 做更准的时序分类
