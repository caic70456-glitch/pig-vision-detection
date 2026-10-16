# -*- coding: utf-8 -*-
"""命令行入口：图像 / 帧序列 / 视频 分析。

用法：
    python cli.py --backend mock --scene-images          # 用合成场景跑流程自检
    python cli.py path/to/photo.jpg                      # 单张图像
    python cli.py path/to/frames_dir --frames            # 帧序列（启用时序行为）
    python cli.py path/to/video.mp4                      # 视频（自动抽帧）
    python cli.py --info                                 # 查看当前检测后端能力
"""
import argparse
import glob
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import detector  # noqa: E402
import pipeline  # noqa: E402


def render(rep: dict) -> str:
    out = []
    out.append("=" * 78)
    det = rep.get("detector", {})
    out.append(f"检测后端：{det.get('backend')}"
               f"　识别猪只能力：{'有' if det.get('can_detect_pig') else '无（近似检测）'}")
    if det.get("image"):
        out.append(f"输入图像：{det['image']}")
    if rep.get("frames_analyzed"):
        out.append(f"分析帧数：{rep['frames_analyzed']}")
    out.append("=" * 78)

    sc = rep.get("scene", {})
    out.append(f"目标个体数：{sc.get('animal_count')}　　人员数：{sc.get('person_count')}")
    cal = det.get("regions_calibrated")
    if cal is True:
        out.append("设施区域：已人工标定（行为判定的空间锚点可靠）")
    elif cal is False:
        out.append("⚠ 设施区域：布局先验推断，未人工标定 —— "
                   "「采食/饮水」可能存在误判。建议运行 "
                   "annotate_regions.py 标定一次")
    out.append(f"行为构成：{json.dumps(rep['behavior'].get('distribution_pct', {}), ensure_ascii=False)}")
    if sc.get("region_counts"):
        out.append(f"设施占用：{json.dumps(sc['region_counts'], ensure_ascii=False)}")
    out.append(f"拥挤度（平均接触数）：{sc.get('crowding')}　"
               f"体型离散度：{sc.get('area_cv')}")

    print_ = rep.get("behavior", {}).get("verdicts", [])
    if print_:
        out.append("")
        out.append("逐个判定：")
        for v in print_:
            out.append(f"  #{v['index']+1:<2} {v['behavior_cn']:<4} 置信 {v['confidence']:.0%}"
                       f"　依据：{'; '.join(v['rules_fired']) or '—'}")
            if v.get("note"):
                out.append(f"       注：{v['note']}")

    out.append("")
    out.append("—— 巡检报告 ——")
    out.append(rep.get("narrative", ""))
    out.append("")

    for w in rep.get("pipeline_warnings", []) or []:
        out.append(f"⚠ {w}")
    for w in rep.get("behavior", {}).get("warnings", []) or []:
        out.append(f"⚠ {w}")
    out.append(f"\n{rep.get('disclaimer','')}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="猪场视觉行为识别与巡检报告")
    ap.add_argument("path", nargs="?", help="图像 / 帧目录 / 视频路径")
    ap.add_argument("--backend", default="auto", choices=["auto", "torchvision", "onnx", "mock"],
                    help="检测后端；auto 会自动优选")
    ap.add_argument("--onnx", help="ONNX 猪只检测模型路径")
    ap.add_argument("--labels", help="类别名 JSON 路径（列表形式）")
    ap.add_argument("--frames", action="store_true", help="把 path 当作帧目录处理（启用时序）")
    ap.add_argument("--scene-images", action="store_true",
                    help="使用 synthetic/scenes.json 里的合成场景做流程自检（已知答案）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--llm", action="store_true", help="启用大模型生成叙述")
    ap.add_argument("--info", action="store_true", help="显示检测后端能力信息")
    ap.add_argument("--regions", help="设施区域配置 JSON（不指定则自动查找同目录 regions.json）")
    ap.add_argument("--out", help="把 JSON 结果写入文件")
    args = ap.parse_args()

    if args.info:
        print("models/ 目录下的 ONNX 模型：", detector.list_available_models() or "（无）")
        b = detector.build_backend(kind="auto")
        print(json.dumps(b.describe(), ensure_ascii=False, indent=1))
        if not b.describe().get("can_detect_pig"):
            print("\n⚠ 当前后端不认识「猪」类别。要获得真正的猪只检测，请：")
            print(f"   1. 把猪只检测模型（.onnx）放入 {detector.MODELS_DIR}\\")
            print("   2. 在同目录放 labels.json，内容形如 {\"labels\": [\"pig\"]}")
            print("   3. 重新运行本命令，会自动切换到 OnnxBackend")
        return

    # ---- 合成场景自检模式 ----
    if args.scene_images:
        meta_p = os.path.join(BASE, "synthetic", "scenes.json")
        if not os.path.isfile(meta_p):
            print("未找到合成场景，请先运行： python make_scenes.py")
            return
        with open(meta_p, encoding="utf-8") as fh:
            data = json.load(fh)
        for s in data["scenes"]:
            dets = [detector.Detection(tuple(d["box"]), d["label"], d["score"])
                    for d in s["detections"]]
            rep = pipeline.analyze_detections(
                dets, data["image_size"], backend_name="mock(合成场景)",
                approximate=True, use_llm=args.llm)
            rep["detector"]["image"] = os.path.basename(s["image"])
            if args.json:
                print(json.dumps(rep, ensure_ascii=False, indent=1))
            else:
                print(render(rep))
                print(f"\n【该场景预期行为】{json.dumps(s['expected'], ensure_ascii=False)}")
        return

    if not args.path:
        ap.print_help()
        return

    backend = detector.build_backend(kind=args.backend, onnx_model=args.onnx)

    # 设施区域：优先用 --regions 指定的配置，否则由 pipeline 自动查找 regions.json
    region_arg = None
    if args.regions:
        import regions as R
        region_arg = R.load_config(args.regions)
        if region_arg is None:
            print(f"⚠ 无法读取区域配置：{args.regions}")

    if args.frames or os.path.isdir(args.path):
        paths = sorted(sum([glob.glob(os.path.join(args.path, e))
                            for e in ("*.jpg", "*.jpeg", "*.png", "*.bmp")], []))
        if not paths:
            print(f"目录中未找到图像：{args.path}")
            return
        rep = pipeline.analyze_frames(paths, backend=backend, regions=region_arg,
                                      use_llm=args.llm)
    elif os.path.splitext(args.path)[1].lower() in (".mp4", ".avi", ".mov", ".mkv"):
        print("视频输入需要先抽帧（本机未安装 opencv）。请用以下方式之一：")
        print("  1. 安装 opencv： pip install opencv-python")
        print("  2. 用 ffmpeg 抽帧： ffmpeg -i video.mp4 -vf fps=2 frames/%04d.jpg")
        print("  然后运行： python cli.py frames_dir --frames")
        return
    else:
        rep = pipeline.analyze_image(args.path, backend=backend, regions=region_arg,
                                     use_llm=args.llm)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=1)
        print(f"结果已写入 {args.out}")

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print(render(rep))


if __name__ == "__main__":
    main()
