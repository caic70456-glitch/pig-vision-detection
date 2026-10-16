# -*- coding: utf-8 -*-
"""生成"导师版"精简包。

与"队友交接包"的区别：
  - 去掉团队分工、截止日期、答辩叙事、扩展模块等**内部策略内容**
  - 保留技术主线 + 可复现的**原始证据**（训练日志 / 评测 JSON / 训练曲线 / 模型）
  - 新增一页"项目简介 + 数据需求"，便于向导师说明来意

输出：e:\trea work 下的「AI农业-猪只视觉检测-导师版」目录与同名 zip
"""
import os
import re
import shutil
import sys
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SRC = r"E:\harness\aic"
OUT_ROOT = r"e:\trea work"
PKG_NAME = "AI农业-猪只视觉检测-导师版"
PKG = os.path.join(OUT_ROOT, PKG_NAME)
ZIP = os.path.join(OUT_ROOT, PKG_NAME + ".zip")
TECH = os.path.join(SRC, "技术方案_赛题一.md")

INTRO = """# 项目简介与数据需求

**项目名称**：基于视觉行为感知的猪只行为检测与疫病辅助诊断系统
**赛题**：第八届全球校园人工智能算法精英大赛 · AI农业算法主题赛 · 赛题一（农业视觉目标检测与识别挑战赛）
**参赛单位**：动物科学技术学院
**负责人**：陈麒光

---

## 一、一句话简介

利用深度学习目标检测 + 轻量化边缘部署，实现猪只行为识别与疫病辅助诊断，面向农业边缘计算场景。

## 二、已完成的工作（均为实测，可复现）

| 工作 | 结果 |
|---|---|
| 自训 YOLOv8n 猪只检测器（PigBench 数据集） | Precision 0.9448 / Recall 0.8896 / mAP50 0.9396 |
| INT8 动态量化 | 模型 11.7MB → **3.2MB**（−72.6%），精度仅 −1.4%，CPU 推理 4.4 FPS |
| 边缘端推理 + 行为规则 + SQLite 落库 | 端到端已跑通（80 张测试图 → 检测 1,658 头猪） |
| 训练与评测过程 | 完整训练日志（15 轮）、评测 JSON、训练曲线，均随包提供 |

> 所有指标均由本人在公开数据集 PigBench 上实测，评测脚本与原始日志见 `03_原始证据/`。

## 三、想向老师请教并请求的素材

1. **监控视频（最需要）**：实验猪场固定机位、连续 3–10 分钟、俯拍或斜上方
   —— 用于验证时序行为（行走/采食/饮水），公开数据集只有静态图
2. **多场景图片**：不同栏舍、不同光照（白天/夜间红外）、不同猪只密度
   —— 用于验证模型在真实场景的**泛化能力**
3. **食槽、饮水器的位置或典型角度说明** —— 用于行为区域标定
4. **（如有）病猪或异常行为片段** —— 用于疫病辅助诊断链路验证

## 四、素材用途说明

- 素材仅用于本比赛的模型验证与展示，会注明来源
- 精度指标仍基于公开数据集 PigBench，**不与真实素材混用**，保证指标可复现
- 若方便安排到实验猪场现场拍摄，效果最好（可配合摄像头做端到端演示）

## 五、随包内容

- `02_技术方案_赛题一（精简版）.md`：技术路线与实测指标
- `03_原始证据/`：训练日志、评测结果、训练曲线、量化模型
"""

# 需要从技术方案中删除的内部章节（按标题关键字匹配）
DROP_KEYWORDS = ["目录", "团队与专业背景", "扩展模块", "答辩材料", "团队分工"]


def condense_tech_doc(text):
    """按标题关键字删除内部章节，保留技术主线。"""
    lines = text.splitlines(keepends=True)
    out = []
    skip_level = None
    for line in lines:
        m = re.match(r"^(#{2,3})\s+(.*?)\s*$", line)
        if m:
            level = len(m.group(1))
            title = m.group(2)
            if skip_level is not None and level > skip_level:
                continue  # 仍在被跳过的章节内部
            skip_level = None
            if any(k in title for k in DROP_KEYWORDS):
                skip_level = level
                continue
            out.append(line)
            continue
        if skip_level is not None:
            continue
        out.append(line)
    body = "".join(out)
    # 合并可能出现的连续空行
    body = re.sub(r"\n{3,}", "\n\n", body)
    # 中和少量"答辩/加分点"等表述（仅导师版；队友包保留原样）
    body = re.sub(r"答辩时[“\"]低成本落地[”\"]反而是加分点",
                  "低成本落地本身即体现工程优化能力", body)
    body = body.replace("答辩前", "赛前")
    header = (
        "# 基于视觉行为感知的猪只行为检测与疫病辅助诊断系统\n\n"
        "> 赛题一：农业视觉目标检测与识别挑战赛 · 第八届全球校园人工智能算法精英大赛\n"
        "> （**导师汇报精简版**：已略去团队分工、扩展模块等内部章节）\n\n"
        "---\n\n"
    )
    # 去掉原文件开头重复的标题行，保留正文
    body = re.sub(r"^#\s+基于视觉行为感知的猪只行为检测与疫病辅助诊断系统\s*\n", "", body, count=1)
    return header + body.lstrip()


def copy_file(src, dst):
    if not os.path.isfile(src):
        print(f"  [跳过·缺失] {src}")
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return True


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    if os.path.isdir(PKG):
        shutil.rmtree(PKG)
    if os.path.isfile(ZIP):
        os.remove(ZIP)
    os.makedirs(PKG)

    print("[1/3] 写入项目简介与数据需求...")
    write_text(os.path.join(PKG, "01_项目简介与数据需求.md"), INTRO)

    print("[2/3] 生成技术方案（精简版）...")
    with open(TECH, "r", encoding="utf-8") as f:
        tech = f.read()
    write_text(os.path.join(PKG, "02_技术方案_赛题一（精简版）.md"), condense_tech_doc(tech))

    print("[3/3] 收集原始证据...")
    runs = os.path.join(SRC, "vision", "runs", "pig_yolov8n")
    models = os.path.join(SRC, "vision", "models")
    ev = os.path.join(PKG, "03_原始证据")
    for f in ["results.csv", "args.yaml"]:
        copy_file(os.path.join(runs, f), os.path.join(ev, f))
    for f in ["benchmark_result.json", "quant_compare.json", "behavior_demo.json"]:
        copy_file(os.path.join(models, f), os.path.join(ev, f))
    for f in ["results.png", "BoxPR_curve.png", "BoxF1_curve.png", "confusion_matrix.png"]:
        copy_file(os.path.join(runs, f), os.path.join(ev, "训练曲线", f))
    for f in ["val_batch0_pred.jpg", "val_batch0_labels.jpg"]:
        copy_file(os.path.join(runs, f), os.path.join(ev, "检测样例", f))
    copy_file(os.path.join(models, "pig-detector-yolov8n-int8.onnx"),
              os.path.join(ev, "模型", "pig-detector-yolov8n-int8.onnx"))

    print("打包 zip...")
    cnt = 0
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, _d, files in os.walk(PKG):
            for f in sorted(files):
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, PKG))
                cnt += 1

    size = os.path.getsize(ZIP) / 1024 / 1024
    print(f"\n完成：\n  目录：{PKG}\n  压缩包：{ZIP}\n  {cnt} 个文件，{size:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
