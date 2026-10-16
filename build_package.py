# -*- coding: utf-8 -*-
"""把各项目成果整合为可提交的成果包。

结构遵循校赛通知的材料要求（作品名称 / 作品方案 / 答辩PPT / 代码及其他材料），
并额外提供「实验数据」与「参考文献」便于评审核对。

排除项（不进提交包）：
    pylibs/           1.1 GB 第三方依赖，用 requirements.txt 说明即可
    data/pigdetect/   1.4 GB 公开数据集，注明来源与许可即可
    __pycache__、hf 缓存等临时产物
"""
import io
import os
import shutil
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

AIC = r"E:\harness\aic"
VISION = os.path.join(AIC, "vision")
PIGDX = os.path.join(AIC, "pigdisease")
RELATE = os.path.join(AIC, "relateanything")
PKG = os.path.join(AIC, "成果包")

DIRS = [
    "01_作品方案",
    "02_答辩PPT",
    "02_答辩PPT/配图",
    "03_源代码/视觉识别_核心模块",
    "03_源代码/视觉识别_网络演示",
    "03_源代码/视觉识别_标注工具",
    "03_源代码/疾病辅助诊断",
    "03_源代码/模型与数据配置",
    "04_实验数据/检测器训练",
    "04_实验数据/行为与标定评测",
    "04_实验数据/疾病诊断评测",
    "05_参考文献",
    "06_训练好的模型",
]

# (源, 目标目录)  —— 只复制源码/文档，不复制依赖与数据集
FILES = [
    # ---- PPT 配图（真实模型输出，供 PPT 使用与评审核验）----
    (os.path.join(AIC, "ppt_assets", "det_compare.png"),
     "02_答辩PPT/配图"),
    # ---- 疫苗识别核心模块 ----
    (os.path.join(VISION, "README.md"), "03_源代码/视觉识别_核心模块"),
    *[(os.path.join(VISION, f), "03_源代码/视觉识别_核心模块") for f in [
        "bootstrap.py", "detector.py", "scene.py", "behavior.py", "health.py",
        "report.py", "visualize.py", "pipeline.py", "cli.py", "regions.py",
        "requirements.txt"]],
    # ---- 网络演示 ----
    (os.path.join(VISION, "web", "app.py"), "03_源代码/视觉识别_网络演示"),
    # ---- 标注工具与评测脚本 ----
    *[(os.path.join(VISION, f), "03_源代码/视觉识别_标注工具") for f in [
        "annotate_regions.py", "make_scenes.py", "make_sequences.py",
        "evaluate_behavior.py", "evaluate_temporal.py", "compare_regions.py",
        "sweep_fight_threshold.py", "smoketest_annotator.py",
        "train_pig_detector.py", "export_onnx.py", "extract_subset.py"]],
    # ---- 疾病诊断 ----
    (os.path.join(PIGDX, "README.md"), "03_源代码/疾病辅助诊断"),
    *[(os.path.join(PIGDX, f), "03_源代码/疾病辅助诊断") for f in [
        "kb_builder.py", "nlu.py", "diagnose.py", "safety.py", "evaluate.py",
        "tune_tiers.py", "cli.py"]],
    *[(os.path.join(PIGDX, "data", f), "03_源代码/疾病辅助诊断") for f in [
        "banned_drugs.json", "overrides.json"]],
    (os.path.join(PIGDX, "web", "app.py"), "03_源代码/疾病辅助诊断"),
    # ---- 模型与数据配置 ----
    (os.path.join(VISION, "data", "pigdetect", "pigdetect.yaml"),
     "03_源代码/模型与数据配置"),
    (os.path.join(VISION, "models", "labels.json"), "03_源代码/模型与数据配置"),
    # ---- 实验数据 ----
    (os.path.join(VISION, "runs", "pig_yolov8n", "results.csv"),
     "04_实验数据/检测器训练"),
    (os.path.join(VISION, "runs", "pig_yolov8n", "results.png"),
     "04_实验数据/检测器训练"),
    (os.path.join(VISION, "runs", "pig_yolov8n", "args.yaml"),
     "04_实验数据/检测器训练"),
    (os.path.join(VISION, "runs", "pig_yolov8n", "confusion_matrix.png"),
     "04_实验数据/检测器训练"),
    (os.path.join(VISION, "runs", "pig_yolov8n", "BoxPR_curve.png"),
     "04_实验数据/检测器训练"),
    *[(os.path.join(VISION, "results", f), "04_实验数据/行为与标定评测") for f in [
        "eval_behavior_synthetic.json", "eval_temporal_synthetic.json",
        "region_calibration_effect.json", "fight_threshold_sweep.json",
        "real_image_report.json"]],
    (os.path.join(PIGDX, "results", "eval_results.json"),
     "04_实验数据/疾病诊断评测"),
    (os.path.join(PIGDX, "results", "tier_sweep.json"),
     "04_实验数据/疾病诊断评测"),
    # ---- 模型 ----
    (os.path.join(VISION, "models", "pig-detector-yolov8n.pt"), "06_训练好的模型"),
    (os.path.join(VISION, "models", "pig-detector-yolov8n.onnx"), "06_训练好的模型"),
]


def main():
    # 不用 rmtree 整目录清空：成果包里的 PDF 可能正被阅读器打开，
    # 删除会因文件占用而失败。改为逐文件清理，被占用的跳过并提示。
    if os.path.isdir(PKG):
        print(f"清理已有成果包：{PKG}")
        locked = []
        for root, dirs, files in os.walk(PKG, topdown=False):
            for f in files:
                p = os.path.join(root, f)
                try:
                    os.remove(p)
                except PermissionError:
                    locked.append(os.path.relpath(p, PKG))
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))
                except OSError:
                    pass
        if locked:
            print("  以下文件被占用，未能清理（请关闭阅读器后重跑）：")
            for x in locked:
                print(f"    {x}")
    for d in DIRS:
        os.makedirs(os.path.join(PKG, d), exist_ok=True)

    ok, miss, locked2 = 0, [], []
    for src, dst_dir in FILES:
        if not os.path.isfile(src):
            miss.append(os.path.basename(src))
            continue
        target_dir = os.path.join(PKG, dst_dir)
        os.makedirs(target_dir, exist_ok=True)      # 清单里有嵌套子目录，按需创建
        # PPT 配图改用中文文件名，便于评委直接看懂
        name = os.path.basename(src)
        if dst_dir.endswith("配图") and name == "det_compare.png":
            name = "检测对比_通用检测器vs自训检测器.png"
        try:
            shutil.copy2(src, os.path.join(target_dir, name))
            ok += 1
        except PermissionError:
            locked2.append(name)

    # 参考文献：原始清单与抽取文本
    for src, name in [
        (r"C:\Users\ASUS\Downloads\CNKI-20261003192821228.txt", "CNKI文献清单_50篇.txt"),
        (os.path.join(AIC, "refs.json"), "文献元数据_refs.json"),
        (os.path.join(AIC, "kb", "疾病知识库候选.md"), "疾病知识库候选表.md"),
        (os.path.join(AIC, "pdf_text.txt"), "官方竞赛通知全文.txt"),
        (os.path.join(AIC, "official_text.txt"), "官方竞赛规则与大纲全文.txt"),
        (os.path.join(AIC, "待补下载清单.md"), "待补文献清单.md"),
    ]:
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(PKG, "05_参考文献", name))
            ok += 1

    # 顶层提交说明（文件名即为校赛要求的首读入口）
    _readme = os.path.join(AIC, "package_readme.md")
    if os.path.isfile(_readme):
        import shutil as _sh
        _sh.copy2(_readme, os.path.join(PKG, "读我先看_提交说明与文件清单.md"))
        ok += 1

    print(f"\n已复制 {ok} 个文件")
    if miss:
        print(f"未找到 {len(miss)} 个（已跳过）：{miss}")

    # 统计
    total = 0
    print("\n各目录：")
    for d in sorted(DIRS):
        p = os.path.join(PKG, d)
        fs = [f for f in os.listdir(p) if os.path.isfile(os.path.join(p, f))]
        sz = sum(os.path.getsize(os.path.join(p, f)) for f in fs)
        total += sz
        if fs:
            print(f"  {d:<42} {len(fs):>3} 个文件  {sz/1024:>8.1f} KB")
    print(f"\n合计约 {total/1024/1024:.1f} MB")


if __name__ == "__main__":
    main()
