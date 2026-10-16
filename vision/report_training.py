# -*- coding: utf-8 -*-
"""读取训练结果，用最佳权重在测试集上评估，并在真实图片上可视化验证。"""
import csv
import io
import os
import sys

sys.path.insert(0, r"E:\harness\aic\vision")
import bootstrap  # noqa: F401,E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = r"E:\harness\aic\vision"
RUN = os.path.join(BASE, "runs", "pig_yolov8n")
BEST = os.path.join(RUN, "weights", "best.pt")
YAML = os.path.join(BASE, "data", "pigdetect", "pigdetect.yaml")

# 1) 读训练曲线
csvp = os.path.join(RUN, "results.csv")
if os.path.isfile(csvp):
    rows = list(csv.DictReader(io.open(csvp, encoding="utf-8")))
    print(f"{'epoch':>6}{'mAP50':>9}{'mAP50-95':>10}{'P':>8}{'R':>8}")
    print("-" * 45)
    for r in rows:
        k = {kk.strip(): vv for kk, vv in r.items()}
        try:
            print(f"{int(float(k.get('epoch', 0))):>6}"
                  f"{float(k.get('metrics/mAP50(B)', 0)):>9.4f}"
                  f"{float(k.get('metrics/mAP50-95(B)', 0)):>10.4f}"
                  f"{float(k.get('metrics/precision(B)', 0)):>8.4f}"
                  f"{float(k.get('metrics/recall(B)', 0)):>8.4f}")
        except (TypeError, ValueError):
            pass
    print()

# 2) 用 best.pt 正式评估
from ultralytics import YOLO  # noqa: E402

print("=" * 60)
print(f"最佳权重: {BEST}")
print(f"大小: {os.path.getsize(BEST)/1e6:.2f} MB")
m = YOLO(BEST)
print("\n模型类别:", m.names)
r = m.val(data=YAML, imgsz=640, device="cpu", verbose=False, plots=True)
print("\n【测试集最终指标】")
print(f"  mAP50     = {r.box.map50:.4f}")
print(f"  mAP50-95  = {r.box.map:.4f}")
print(f"  Precision = {r.box.mp:.4f}")
print(f"  Recall    = {r.box.mr:.4f}")

# 3) 真实图片可视化验证
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

IMG = os.path.join(BASE, "data", "pigdetect", "extract", "test", "images")
OUT = os.path.join(BASE, "data", "pigdetect", "vis_trained")
os.makedirs(OUT, exist_ok=True)
imgs = sorted(f for f in os.listdir(IMG) if f.endswith(".jpg"))[:6]
print(f"\n真实图片检测验证（{len(imgs)} 张）：")


def font(sz=18):
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                pass
    return ImageFont.load_default()


for n in imgs:
    p = os.path.join(IMG, n)
    res = m.predict(p, conf=0.25, imgsz=640, device="cpu", verbose=False)[0]
    nb = len(res.boxes) if res.boxes is not None else 0
    avgc = float(res.boxes.conf.mean()) if nb else 0.0
    print(f"  {n[:38]:<40} 检出 {nb:>2} 头   平均置信 {avgc:.3f}")
    im = Image.open(p).convert("RGB")
    d = ImageDraw.Draw(im)
    if res.boxes is not None:
        for b, c in zip(res.boxes.xyxy.cpu().numpy(), res.boxes.conf.cpu().numpy()):
            x1, y1, x2, y2 = [float(v) for v in b]
            d.rectangle([x1, y1, x2, y2], outline=(230, 30, 30), width=3)
            d.text((x1 + 3, max(0, y1 - 20)), f"pig {c:.2f}", fill=(230, 30, 30), font=font(15))
    d.text((8, 8), f"自训猪检测器 · 检出 {nb} 头", fill=(20, 20, 20), font=font(20))
    im.save(os.path.join(OUT, "det_" + n))

print(f"\n可视化输出: {OUT}")
