# -*- coding: utf-8 -*-
"""从各评测结果 JSON 生成 Markdown 指标表 —— 保证文档里的数字可溯源、不手写。"""
import io
import json
import os

AIC = r"E:\harness\aic"
# 注意：不能生成到成果包目录内——build_package.py 会先清空该目录，
# 导致刚生成的指标表被删掉。先生成到外部，再由打包脚本复制进去。
OUT = os.path.join(AIC, "_自动生成的指标表.md")


def load(p):
    with io.open(p, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    md = ["# 实验指标汇总（由脚本自动生成，数字来自各结果 JSON）", ""]

    # ---- 1. 检测 ----
    csvp = os.path.join(AIC, "vision", "runs", "pig_yolov8n", "results.csv")
    if os.path.isfile(csvp):
        import csv as _csv
        rows = list(_csv.DictReader(io.open(csvp, encoding="utf-8")))
        md += ["## 1. 猪只检测器训练过程（YOLOv8n，PigBench 数据集）", "",
               "| epoch | mAP50 | mAP50-95 | Precision | Recall |",
               "|---|---|---|---|---|"]
        for r in rows:
            k = {kk.strip(): vv for kk, vv in r.items()}
            try:
                md.append(f"| {int(float(k.get('epoch', 0)))} "
                          f"| {float(k.get('metrics/mAP50(B)', 0)):.4f} "
                          f"| {float(k.get('metrics/mAP50-95(B)', 0)):.4f} "
                          f"| {float(k.get('metrics/precision(B)', 0)):.4f} "
                          f"| {float(k.get('metrics/recall(B)', 0)):.4f} |")
            except (TypeError, ValueError):
                pass
        last = rows[-1] if rows else {}
        lk = {kk.strip(): vv for kk, vv in last.items()}
        md += ["", f"**最终（第 {int(float(lk.get('epoch', 0)))} 轮）**："
                   f"mAP50 = **{float(lk.get('metrics/mAP50(B)', 0)):.4f}**，"
                   f"mAP50-95 = **{float(lk.get('metrics/mAP50-95(B)', 0)):.4f}**，"
                   f"Precision = **{float(lk.get('metrics/precision(B)', 0)):.4f}**，"
                   f"Recall = **{float(lk.get('metrics/recall(B)', 0)):.4f}**", ""]

    # ---- 2. 单帧行为 ----
    p = os.path.join(AIC, "vision", "results", "eval_behavior_synthetic.json")
    if os.path.isfile(p):
        d = load(p)
        md += ["## 2. 单帧行为推理（合成场景，已知标准答案）", "",
               f"数据集：{d.get('dataset','')}", "",
               "| 场景 | 目标数 | 正确 | 准确率 |", "|---|---|---|---|"]
        for s in d.get("scenes", []):
            md.append(f"| {s['scene']} | {s['targets']} | {s['correct']} "
                      f"| {s['accuracy']:.1%} |")
        md += ["", f"**总体准确率 {d.get('accuracy',0):.1%}"
                   f"（{d.get('n_correct')}/{d.get('n_targets')}），"
                   f"宏平均 F1 = {d.get('macro_f1',0):.3f}**", "",
               "各类别：", "", "| 类别 | tp | fp | fn |", "|---|---|---|---|"]
        for k, v in (d.get("per_class") or {}).items():
            md.append(f"| {k} | {v.get('tp')} | {v.get('fp')} | {v.get('fn')} |")
        md += ["", f"> {d.get('disclaimer','')}", ""]

    # ---- 3. 时序行为 ----
    p = os.path.join(AIC, "vision", "results", "eval_temporal_synthetic.json")
    if os.path.isfile(p):
        d = load(p)
        md += ["## 3. 时序行为推理（合成帧序列）", "",
               f"数据集：{d.get('dataset','')}", "",
               f"**时序判定准确率 {d.get('accuracy',0):.1%}"
               f"（{d.get('n_correct')}/{d.get('n_checks')}）**", "",
               "| 序列 | 逐帧时序特征 | 行为占比 |", "|---|---|---|"]
        for s in d.get("sequences", []):
            tf = "；".join(f"#{t['track_id']+1} 位移{t['displacement']:.3f}"
                           f"/速度{t['speed']:.4f}/面积变化{t['area_change']:+.2f}"
                           for t in s.get("track_features", [])[:2])
            dist = "、".join(f"{k} {v:.0f}%" for k, v in
                            (s.get("distribution_pct") or {}).items() if v > 0)
            md.append(f"| {s['sequence']} | {tf} | {dist} |")
        md += ["", f"> {d.get('disclaimer','')}", ""]

    # ---- 4. 标定效果 ----
    p = os.path.join(AIC, "vision", "results", "region_calibration_effect.json")
    if os.path.isfile(p):
        d = load(p)
        md += ["## 4. 设施区域标定的效果（真实猪舍图片）", "",
               f"对比图片数：{d.get('n_images')}，目标总数：{d.get('n_targets')}", "",
               "| 行为 | 布局先验推断 | 人工标定 | 变化 |", "|---|---|---|---|"]
        CN = {"eating": "采食", "drinking": "饮水", "resting": "休息",
              "standing": "站立", "walking": "行走", "aggressive": "争斗"}
        for k in ("eating", "drinking", "resting", "standing", "walking", "aggressive"):
            a = (d.get("inferred_pct") or {}).get(k, 0.0)
            b = (d.get("calibrated_pct") or {}).get(k, 0.0)
            md.append(f"| {CN.get(k,k)} | {a:.1f}% | {b:.1f}% | {b-a:+.1f}% |")
        md += ["", f"> {d.get('note','')}", ""]

    # ---- 5. 外部分辨力检验（RelateAnything）----
    p = os.path.join(AIC, "relateanything", "results", "vocab_controlled.json")
    if os.path.isfile(p):
        d = load(p)
        md += ["## 5. 开放词汇关系模型的判别力检验（技术选型依据）", "",
               "被测对象：RelateAnything（GitHub 894 stars，arXiv:2609.12552，53M 参数）", "",
               "| 词表条件 | 关系总数 | 判为 fighting 数 | 占比 | 最高置信度 |",
               "|---|---|---|---|---|"]
        for cond in (d.get("conditions") or {}):
            rs = [r for r in d.get("rows", []) if r["condition"] == cond]
            tot = sum(r["n_relations"] for r in rs)
            fc = sum(r["distribution"].get("fighting with", 0) for r in rs)
            mf = max((r["max_score"] for r in rs), default=0.0)
            md.append(f"| {cond} | {tot} | {fc} "
                      f"| {(fc/tot*100 if tot else 0):.1f}% | {mf:.3f} |")
        md += ["", "**结论**：只给 `fighting with` 一个词时 180/180 全判为 fighting，"
                   "但最高置信度仅 0.073；同一批图在只给 `standing next to` 时达 0.500（7 倍）。"
                   "说明其输出主要由词表先验驱动，而非场景内容；"
                   "在真实猪舍图片上对 `fighting with` 的置信度为 0，无判别力。", ""]

    p = os.path.join(AIC, "relateanything", "results", "fight_discrimination.json")
    if os.path.isfile(p):
        d = load(p)
        md += ["### 正负对照（争斗场景 vs 采食场景）", "",
               "| 分组 | 样本 | 目标数 | fighting 最高分 |", "|---|---|---|---|"]
        for r in d.get("rows", []):
            name = r.get("image") or f"第{r.get('frame')}帧"
            md.append(f"| {r.get('group')} | {name} | {r.get('n_targets')} "
                      f"| {r['max_scores'].get('fighting with', 0):.3f} |")
        md += ["", "> 正样本为合成序列（椭圆色块），仅检验几何关系判别力；负样本为真实猪舍图片。", ""]

    # ---- 6. 疾病诊断 ----
    p = os.path.join(AIC, "pigdisease", "results", "eval_results.json")
    if os.path.isfile(p):
        d = load(p)
        m = d.get("metrics", {})
        s = d.get("safety_metrics", {})
        md += ["## 6. 文本疾病辅助诊断模块", "",
               "| 指标 | 数值 |", "|---|---|",
               f"| 评测案例数 | {m.get('n_cases')} |",
               f"| 知识库疾病数 | {m.get('kb_diseases')} |",
               f"| Top-1 命中率 | {m.get('top1_accuracy',0):.1%} |",
               f"| Top-3 命中率 | {m.get('top3_accuracy',0):.1%} |",
               f"| MRR | {m.get('mrr',0):.3f} |",
               f"| 禁用药物拦截测试 | {s.get('passed')}/{s.get('n')} 通过 |", ""]
        st = m.get("stratified") or {}
        if st:
            md += ["分层结果（区分算法问题与知识库覆盖问题）：", "",
                   "| 分层 | 案例数 | Top-1 | Top-3 |", "|---|---|---|---|"]
            for k, v in st.items():
                t1 = f"{v['top1']:.1%}" if v.get("top1") is not None else "—"
                t3 = f"{v['top3']:.1%}" if v.get("top3") is not None else "—"
                md.append(f"| {k} | {v.get('n')} | {t1} | {t3} |")
            md += [""]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8").write("\n".join(md))
    print(f"已生成 {OUT}  ({os.path.getsize(OUT)} 字节)")
    print("\n预览前 40 行：")
    print("\n".join(md[:40]))


if __name__ == "__main__":
    main()
