# -*- coding: utf-8 -*-
"""把现有材料整合成"队友交接包"并打成 zip。

组成：
  01_校赛成果包          —— 直接复制现有 成果包/（作品方案/PPT/源码/实验数据/文献/模型）
  02_赛题一新增材料       —— 技术方案_赛题一、INT8 模型、评测 JSON、边缘脚本、部署说明、PPT素材
  读我先看_交接说明.md     —— 给两位队友的导航
  分工与进度.md           —— 按专业重排的分工表

沿用 make_zip.py 的容错约定：逐个文件写入，遇到被占用（PermissionError）先报告，
不产出不完整压缩包。
"""
import os
import shutil
import sys
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SRC = r"E:\harness\aic"
OUT_ROOT = r"e:\trea work"
PKG_NAME = "AI农业-猪只视觉检测-队友交接包"
PKG = os.path.join(OUT_ROOT, PKG_NAME)
ZIP = os.path.join(OUT_ROOT, PKG_NAME + ".zip")


# ---------------------------------------------------------------- 说明文档
README = """# 队友交接说明（先看这一份）

- **赛题**：AI+农业算法主题赛 · 赛题一：农业视觉目标检测与识别挑战赛
- **作品**：基于视觉行为感知的猪只行为检测与疫病辅助诊断系统
- **队长**：陈麒光（动物科学 动科+智能251）
- **队友**：杨轹文（智能装备·卓越工程师）、武岳（食品科学与工程）
- **生成时间**：2026-10-14

---

## 一、这个压缩包里有什么

```
AI农业-猪只视觉检测-队友交接包/
├── 读我先看_交接说明.md        本文件
├── 分工与进度.md               按专业重排的分工与截止时间
├── 01_校赛成果包/              现有校赛成品（可直接复用的底座）
│   ├── 01_作品方案/           作品方案 docx + pdf
│   ├── 02_答辩PPT/            答辩PPT pptx + pdf + 大纲 + 配图
│   ├── 03_源代码/             视觉识别核心模块 / 网络演示 / 标注工具 / 疾病辅助诊断
│   ├── 04_实验数据/           检测器训练日志与曲线 / 行为与标定评测 / 疾病诊断评测
│   ├── 05_参考文献/           CNKI清单、题录、官方通知与规则全文
│   └── 06_训练好的模型/       pig-detector-yolov8n.pt / .onnx
└── 02_赛题一新增材料/          本次为赛题一新做的成果
    ├── 技术方案_赛题一.md       ★ 主蓝本（按赛题一四评分维度组织）
    ├── AIC2026_AI+农业_技术方案_初稿.docx
    ├── 疾病诊断AI_技术方案.md
    ├── 模型与评测/
    │   ├── pig-detector-yolov8n-int8.onnx   ★ INT8 量化模型（3.2MB，边缘部署用这个）
    │   ├── benchmark_result.json            精度评测原始数据（Precision/Recall/多尺度）
    │   ├── quant_compare.json               FP32 vs INT8 对比原始数据
    │   ├── behavior_demo.json / .md          行为分布演示数据
    │   └── labels.json
    ├── 脚本/
    │   ├── benchmark_onnx.py    ONNX 精度/速度评测
    │   ├── quantize_int8.py     INT8 量化 + 对比
    │   ├── edge_infer.py        ★ 边缘端推理主脚本（摄像头/视频/图片 三模式）
    │   ├── onnx_utils.py        共享工具库（letterbox/NMS/行为规则）
    │   └── demo_behavior.py     行为分布演示
    ├── 边缘部署/
    │   ├── 边缘部署说明_README.md  硬件方案（零成本）+ 架构图 + 部署命令
    │   ├── init_db.sql           SQLite 6 张核心表
    │   ├── db.py                 数据库封装
    │   └── pigfarm.db            示例数据库
    └── PPT素材/
        ├── behavior_seq.png     行为序列可视化
        └── det_compare.png      通用检测器 vs 自训检测器对比图
```

---

## 二、你该先看哪些

### 杨轹文（智能装备 → 硬件 + 边缘部署 + 机电联动）
1. `02_赛题一新增材料/边缘部署/边缘部署说明_README.md` ← 硬件方案（零成本）与部署步骤
2. `02_赛题一新增材料/脚本/edge_infer.py`、`onnx_utils.py` ← 你要跑的主脚本
3. `02_赛题一新增材料/模型与评测/pig-detector-yolov8n-int8.onnx` ← 部署用模型
4. `02_赛题一新增材料/边缘部署/init_db.sql`、`db.py` ← 数据落库
5. `01_校赛成果包/03_源代码/视觉识别_核心模块/` ← detector/behavior/health/regions 参考

### 武岳（食品科学 → PPT + 答辩 + 食品安全叙事）
1. `02_赛题一新增材料/技术方案_赛题一.md` ← **做 PPT 的主蓝本**
2. `01_校赛成果包/02_答辩PPT/` ← 可直接复用的 PPT 与大纲
3. `01_校赛成果包/01_作品方案/` ← 可直接复用的作品方案
4. `02_赛题一新增材料/模型与评测/*.json` ← PPT 里要引用的实测数据
5. `02_赛题一新增材料/PPT素材/` ← 现成配图

---

## 三、数据真实性（答辩可能被追问）

所有指标均来自实测，PPT 里的数字请从对应文件读取、不要手写：

| 数据 | 数值 | 对应文件 |
|---|---|---|
| 检测 Precision / Recall | 0.9448 / 0.8896 | 模型与评测/benchmark_result.json |
| mAP50 / mAP50-95 | 0.9396 / 0.6725 | 01_校赛成果包/04_实验数据/检测器训练/results.csv |
| 多尺度 Recall（大/中/小） | 0.9077 / 0.8922 / 0.1923 | 模型与评测/benchmark_result.json |
| INT8 体积 / 精度变化 | 3277 KB / Precision −1.37% | 模型与评测/quant_compare.json |
| INT8 FPS（CPU） | 4.4（FP32 为 3.3） | 模型与评测/quant_compare.json |
| 行为分布（采食/休息/争斗） | 12.6% / 18.4% / 8.0% | 模型与评测/behavior_demo.json |

> 注意区分数据性质：检测指标来自**真实公开数据集**；行为分布来自测试图**假设食槽区域**的演示；
> 疾病诊断指标来自**自建评测集**。未验证内容已在技术方案中如实标注。

---

## 四、运行环境

- Python 3.14（本机）/ 3.12（校赛成果包代码）
- 依赖：`onnxruntime`、`opencv-python`、`pillow`、`numpy`
- 边缘端 = 杨轹文的笔记本电脑（ONNX INT8 CPU，实测 4.4 FPS）；传感器/执行机构用 ESP32/STM32。**零成本，无需购买 Jetson。**

常用命令：

```bash
python benchmark_onnx.py                 # 复现检测精度/速度评测
python quantize_int8.py                  # 复现 INT8 量化与对比
python edge_infer.py --source images --path <图片目录> --no-display
python edge_infer.py --source camera --device 0            # 真实摄像头
python demo_behavior.py                  # 复现行为分布演示
```
"""

DIVISION = """# 分工与进度（按专业重排）

| 成员 | 专业 | 角色定位 | 专业增值点 | 核心交付 | 截止 |
|---|---|---|---|---|---|
| 陈麒光 | 动物科学+AI | 视觉 AI 技术核心 | 动物行为学领域知识 | 模型/评测/方案/边缘脚本 | 已完成 |
| 杨轹文 | 智能装备（卓越工程师） | 硬件 + 边缘工程落地 | **机电联动闭环控制** | 硬件集成/传感器/部署 | 10/27 |
| 武岳 | 食品科学与工程 | 答辩 + 食品安全叙事 | **食品安全价值链** | PPT/视频/答辩 | 10/28 |

---

## 陈麒光（视觉 AI 技术核心）

| 任务 | 状态 |
|---|---|
| YOLOv8n PigBench 自训（mAP50=0.940） | 完成 |
| ONNX FP32 导出 + INT8 动态量化（3.2MB） | 完成 |
| FP32/INT8 精度速度评测（benchmark/quant JSON） | 完成 |
| 技术方案_赛题一（本文档蓝本） | 完成 |
| 给武岳补 PPT 素材（曲线/可视化截图） | 待办 10/18 |
| RK3566 NPU（RKNN）转换脚本（可选升级，预算允许再做） | 待办 10/30 |

## 杨轹文（智能装备 → 硬件 + 机电）

| 任务 | 用到的专业课 | 截止 |
|---|---|---|
| 摄像头 + ESP32/STM32 单片机采购 | 测控系统 | 10/22 |
| 笔记本环境搭建（Python + ONNX Runtime + OpenCV） | 嵌入式/测控 | 10/22 |
| 多传感器接入（温湿度/氨气） | **传感器与检测技术** | 10/26 |
| 部署模型 + edge_infer 端到端跑通 | 嵌入式系统 | 10/27 |
| 机电联动控制（异常→报警/通风） | **自动控制/机电传动** | 10/30 |
| 现场摄像头标定（食槽/饮水器区域） | 测控标定 | 10/30 |
| 硬件实物照片 + 运行视频 | 工程实践 | 11/1 |

## 武岳（食品科学 → 答辩 + 食品安全）

| 任务 | 用到的专业课 | 截止 |
|---|---|---|
| 阅读技术方案_赛题一，理解四评分维度 | — | 10/18 |
| PPT 主稿（20-25 页） | 表达能力 | 10/25 |
| 食品安全价值链专题页（从农场到餐桌） | **食品安全/HACCP** | 10/28 |
| 猪肉品质等级标签体系草案 | **肉品科学/感官评价** | 10/28 |
| 录 Demo 视频（30-60 秒） | — | 10/28 |
| 答辩演讲稿 + 模拟答辩 | — | 11/3 |

---

## 依赖关系

```
陈麒光（技术方案终稿 + 素材 10/18）
   ├──▶ 武岳（PPT 主稿 10/25 → 食品安全页 10/28）
   └──▶ 杨轹文（硬件到手 10/22 → 端到端 10/27 → 机电联动 10/30）
                    └──▶ 武岳（用杨的实机画面录 Demo 视频 10/28）
三人一起：提交材料打包 11/1
```
"""


def copy_file(src, dst):
    if not os.path.isfile(src):
        print(f"  [跳过·缺失] {src}")
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return True


def copy_tree(src, dst, skip_prefix=("~$",)):
    if not os.path.isdir(src):
        print(f"  [跳过·缺失] {src}")
        return 0
    n = 0
    for root, _d, files in os.walk(src):
        rel = os.path.relpath(root, src)
        for f in files:
            if f.startswith(skip_prefix):
                continue
            s = os.path.join(root, f)
            d = os.path.join(dst, rel, f) if rel != "." else os.path.join(dst, f)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)
            n += 1
    return n


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    # 0. 清理旧包
    if os.path.isdir(PKG):
        shutil.rmtree(PKG)
    if os.path.isfile(ZIP):
        os.remove(ZIP)
    os.makedirs(PKG)

    print("构建交接包目录...")
    write_text(os.path.join(PKG, "读我先看_交接说明.md"), README)
    write_text(os.path.join(PKG, "分工与进度.md"), DIVISION)

    # 1. 校赛成果包
    print("[1/2] 复制现有成果包...")
    n = copy_tree(os.path.join(SRC, "成果包"), os.path.join(PKG, "01_校赛成果包"))
    print(f"  {n} 个文件")

    # 2. 赛题一新增材料
    print("[2/2] 收集赛题一新增材料...")
    d2 = os.path.join(PKG, "02_赛题一新增材料")
    copy_file(os.path.join(SRC, "技术方案_赛题一.md"),
              os.path.join(d2, "技术方案_赛题一.md"))
    copy_file(os.path.join(SRC, "AIC2026_AI+农业_技术方案_初稿.docx"),
              os.path.join(d2, "AIC2026_AI+农业_技术方案_初稿.docx"))
    copy_file(os.path.join(SRC, "疾病诊断AI_技术方案.md"),
              os.path.join(d2, "疾病诊断AI_技术方案.md"))

    m = os.path.join(SRC, "vision", "models")
    for f in ["pig-detector-yolov8n-int8.onnx", "benchmark_result.json",
              "quant_compare.json", "behavior_demo.json", "behavior_demo.md",
              "labels.json"]:
        copy_file(os.path.join(m, f), os.path.join(d2, "模型与评测", f))

    v = os.path.join(SRC, "vision")
    for f in ["benchmark_onnx.py", "quantize_int8.py", "edge_infer.py",
              "onnx_utils.py", "demo_behavior.py"]:
        copy_file(os.path.join(v, f), os.path.join(d2, "脚本", f))

    copy_file(os.path.join(SRC, "edge", "README.md"),
              os.path.join(d2, "边缘部署", "边缘部署说明_README.md"))
    for f in ["init_db.sql", "db.py", "pigfarm.db"]:
        copy_file(os.path.join(SRC, "db", f), os.path.join(d2, "边缘部署", f))

    pa = os.path.join(SRC, "ppt_assets")
    if os.path.isdir(pa):
        for f in os.listdir(pa):
            copy_file(os.path.join(pa, f), os.path.join(d2, "PPT素材", f))

    # 3. 打包（容错）
    print("打包 zip...")
    locked = []
    cnt = 0
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, _d, files in os.walk(PKG):
            for f in sorted(files):
                p = os.path.join(root, f)
                arc = os.path.relpath(p, PKG)
                try:
                    z.write(p, arc)
                    cnt += 1
                except (PermissionError, OSError) as e:
                    locked.append((arc, str(e)))

    if locked:
        print("以下文件被占用，未能写入：")
        for arc, err in locked:
            print(f"  {arc}: {err}")
        try:
            os.remove(ZIP)
        except Exception:
            pass
        print("已删除不完整压缩包，请关闭占用文件的程序后重试。")
        return 1

    size = os.path.getsize(ZIP) / 1024 / 1024
    print("\n完成：")
    print(f"  目录：{PKG}")
    print(f"  压缩包：{ZIP}")
    print(f"  {cnt} 个文件，{size:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
