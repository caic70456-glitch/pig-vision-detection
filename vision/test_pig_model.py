# -*- coding: utf-8 -*-
"""在 PigBench 真实猪舍图片上测试 yolov8n-pig 模型。

对比：模型预测框 vs YOLO 格式真值标签（labels/*.txt）
输出：带标注的可视化图 + 单图统计
"""
import argparse
import os
import sys

sys.path.insert(0, r"E:\harness\aic\vision")
import bootstrap  # noqa: F401,E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

MODEL = r"E:\harness\aic\vision\models\yolov8n-pig.pt"
ROOT = r"E:\harness\aic\vision\data\pigdetect\extract\test"
OUT = r"E:\harness\aic\vision\data\pigdetect\vis"


def read_yolo_labels(path, w, h):
    """读 YOLO 格式真值：cls cx cy bw bh（归一化）-> 像素 xyxy"""
    boxes = []
    if not os.path.isfile(path):
        return boxes
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            p = line.split()
            if len(p) < 5:
                continue
            _, cx, cy, bw, bh = p[:5]
            cx, cy, bw, bh = float(cx) * w, float(cy) * h, float(bw) * w, float(bh) * h
            boxes.append((cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2))
    return boxes


def font(sz=16):
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                pass
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6, help="测试几张图")
    ap.add_argument("--conf", type=float, default=0.25)
    args = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(MODEL)
    print("模型加载成功:", os.path.basename(MODEL))
    print("模型类别:", model.names)

    img_dir = os.path.join(ROOT, "images")
    lab_dir = os.path.join(ROOT, "labels")
    os.makedirs(OUT, exist_ok=True)

    imgs = sorted(f for f in os.listdir(img_dir) if f.lower().endswith(".jpg"))[:args.n]
    print(f"\n{'图片':<34}{'真值框':>7}{'预测框':>7}{'平均置信':>9}   推理耗时")
    print("-" * 88)

    for name in imgs:
        ip = os.path.join(img_dir, name)
        lp = os.path.join(lab_dir, name.rsplit(".", 1)[0] + ".txt")
        im = Image.open(ip).convert("RGB")
        w, h = im.size
        gt = read_yolo_labels(lp, w, h)

        res = model.predict(ip, conf=args.conf, verbose=False)[0]
        pred = [tuple(map(float, b)) for b in res.boxes.xyxy] if res.boxes is not None else []
        confs = [float(c) for c in res.boxes.conf] if res.boxes is not None else []
        speed = res.speed.get("inference", 0) if hasattr(res, "speed") else 0

        print(f"{name[:32]:<34}{len(gt):>7}{len(pred):>7}"
              f"{(sum(confs)/len(confs) if confs else 0):>9.3f}   {speed:.0f} ms")

        # 可视化：绿=真值，红=预测
        d = ImageDraw.Draw(im)
        for (x1, y1, x2, y2) in gt:
            d.rectangle([x1, y1, x2, y2], outline=(0, 200, 0), width=3)
        for (x1, y1, x2, y2), c in zip(pred, confs):
            d.rectangle([x1, y1, x2, y2], outline=(230, 30, 30), width=3)
            d.text((x1 + 3, max(0, y1 - 18)), f"{c:.2f}", fill=(230, 30, 30), font=font(14))
        d.text((8, 8), f"绿=真值 {len(gt)}　红=预测 {len(pred)}", fill=(20, 20, 20), font=font(18))
        im.save(os.path.join(OUT, "cmp_" + name))
        # 同时存一个纯预测图（供系统的可视化流程使用）
        res.save(filename=os.path.join(OUT, "pred_" + name))

    print("-" * 88)
    print(f"可视化输出目录: {OUT}")
    print("绿框=人工真值，红框=模型预测；两者高度吻合说明模型可用。")


if __name__ == "__main__":
    main()
