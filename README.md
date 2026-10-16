# 🐷 基于视觉行为感知的猪只行为检测与疫病辅助诊断系统

**第八届全球校园人工智能算法精英大赛 · AI 农业算法主题赛 · 赛题一：农业视觉目标检测与识别挑战赛**

基于 YOLOv8n 的猪只目标检测 → INT8 轻量化量化 → 浏览器端 / 边缘端部署的完整链路。

## 🔗 在线体验

**https://caic70456-glitch.github.io/pig-vision-detection/**

纯浏览器端推理（onnxruntime-web + WebAssembly），模型仅 **3.2 MB**，图片不上传服务器。
打开后点击「🐷 示例图片」即可一键体验，也可上传自己的猪只照片并调节置信度阈值。

## 📊 性能指标（PigBench 公开测试集实测）

| 类别 | 指标 | 数值 |
|---|---|---|
| 检测精度 | Precision | **0.9448** |
| | Recall | **0.8896** |
| | mAP50 / mAP50-95 | **0.9396 / 0.6725** |
| 轻量化 | 模型体积（FP32 → INT8） | 11.7 MB → **3.2 MB（−72.6%）** |
| | INT8 后 Precision / Recall | 0.9318 / 0.8931（精度损失约 1.4%） |
| 推理效率 | CPU 推理（FP32 / INT8） | 3.3 / **4.4 FPS**（延迟 299.8 → 227.6 ms） |
| Web 实测 | 示例图（Chrome） | 检出 22 头，平均置信度 0.886，887 ms |

> 所有指标均有评测脚本与原始日志支撑，见 `vision/models/*.json` 与 `vision/runs/pig_yolov8n/results.csv`。

## 📁 仓库结构

```
├── docs/                  # 🌐 Web 应用（GitHub Pages 部署目录）
│   ├── index.html         #   onnxruntime-web 推理页面（零依赖构建）
│   ├── model.onnx         #   INT8 量化模型（3.2 MB）
│   └── sample.jpg         #   示例图片
├── vision/
│   ├── models/            # 模型：.pt / FP32 ONNX / INT8 ONNX + 评测 JSON
│   ├── runs/pig_yolov8n/  # 训练日志、PR/F1 曲线、混淆矩阵、best.pt
│   ├── benchmark_onnx.py  # ONNX 精度/速度评测
│   ├── quantize_int8.py   # INT8 动态量化与 FP32 对比
│   └── ...                # 检测器/行为规则/健康评估等模块
├── db/                    # SQLite 时序数据库（建表 SQL + Python 封装）
├── edge/                  # 边缘端部署说明（笔记本 + ESP32/STM32 零成本方案）
├── 技术方案_赛题一.md      # 完整技术方案（按赛题评分维度组织）
├── 成果包/                # 校赛成果：作品方案、答辩 PPT、源码、实验数据、文献
└── pigdisease/, kb/       # 猪病领域知识库（早期模块，供诊断链路扩展）
```

## 🚀 本地运行

### 方式一：Web 应用

```bash
# 任意静态服务器均可，例如 Python：
cd docs
python -m http.server 8000
# 浏览器打开 http://localhost:8000
```

### 方式二：Python 评测 / 边缘推理

```bash
pip install onnxruntime opencv-python pillow numpy

# FP32 vs INT8 精度/速度评测
python vision/benchmark_onnx.py

# INT8 量化
python vision/quantize_int8.py

# 边缘端推理（图片目录 / 视频 / 摄像头）
python vision/edge_infer.py --source path/to/images
```

## 🛠 技术栈

| 环节 | 技术 |
|---|---|
| 训练 | Ultralytics YOLOv8n，PigBench 数据集，15 epochs |
| 轻量化 | ONNX 导出 + 动态 INT8 量化（onnxruntime） |
| Web 部署 | onnxruntime-web 1.19 (WASM)，原生 JS + Canvas，无构建步骤 |
| 边缘部署 | ONNX Runtime（笔记本 CPU）/ ESP32、STM32 负责传感器与执行机构 |
| 数据存储 | SQLite（6 张时序表：设备、栏舍、检测、行为、环境、风险标签） |

## 📝 说明

- 数据集 PigBench 未包含在仓库内（体积约 2.7 GB）；精度指标均基于该公开测试集。
- 检测模型目前为单类别（pig）；行为分类基于可解释规则引擎（采食/饮水/休息/站立/行走/攻击）。
- 已知局限与改进路线见 `技术方案_赛题一.md` 第 9 章（小目标 Recall、现场基线标定等）。

## 👥 团队

动物科学技术学院：陈麒光（视觉/算法）、武岳（食品科学与工程 · PPT 与答辩）、杨轹文（智能装备 · 硬件与边缘部署）
