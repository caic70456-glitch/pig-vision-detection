# -*- coding: utf-8 -*-
"""在 PigDetect（PigBench）数据上微调 YOLOv8n，得到真正的单类猪只检测器。

背景：HuggingFace 上 marcosvmf/yolov8-piglife-sam3 仓库声称提供猪只检测权重，
      但实测三个 .pt 文件都是 COCO 预训练模型（head.nc=80、data=coco.yaml），
      其中 yolov8n-pig.pt 与官方 yolov8n.pt 的 SHA256 完全一致。
      因此本机自行训练：以 COCO 预训练权重的骨干为起点，在 500 张带真值猪框的
      数据集上微调，得到单类（pig）检测器。

用法：
    python train_pig_detector.py --epochs 15
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

BASE = r"E:\harness\aic\vision"
DATA = os.path.join(BASE, "data", "pigdetect", "pigdetect.yaml")
# 用官方 COCO yolov8n 作预训练起点（已下载到本地，避免在线拉取）
PRETRAINED = os.path.join(BASE, "models", "yolov8n-coco.pt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--model", default=PRETRAINED)
    ap.add_argument("--name", default="pig_yolov8n")
    args = ap.parse_args()

    from ultralytics import YOLO

    os.environ.setdefault("YOLO_CONFIG_DIR", os.path.join(BASE, "Ultralytics"))
    print(f"数据配置   : {DATA}")
    print(f"预训练权重 : {args.model}")
    print(f"训练轮数   : {args.epochs}  图像尺寸: {args.imgsz}  批大小: {args.batch}")
    print("注意：本机 CPU-only，训练会较慢。\n")

    model = YOLO(args.model)
    model.train(
        data=DATA,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device="cpu",
        workers=2,
        project=os.path.join(BASE, "runs"),
        name=args.name,
        exist_ok=True,
        pretrained=True,
        optimizer="SGD",
        lr0=0.005,
        patience=8,
        # CPU 上关闭耗时增强，保证能在可接受时间内跑完
        mosaic=0.5,
        mixup=0.0,
        copy_paste=0.0,
        erasing=0.0,
        cache=False,
        plots=True,
        val=True,
        verbose=True,
    )

    best = os.path.join(BASE, "runs", args.name, "weights", "best.pt")
    print(f"\n训练完成，最佳权重: {best}")
    if os.path.isfile(best):
        m = YOLO(best)
        print("验证集评估结果：")
        r = m.val(data=DATA, imgsz=args.imgsz, device="cpu", verbose=False)
        print(f"  mAP50    = {r.box.map50:.4f}")
        print(f"  mAP50-95 = {r.box.map:.4f}")
        print(f"  Precision= {r.box.mp:.4f}")
        print(f"  Recall   = {r.box.mr:.4f}")


if __name__ == "__main__":
    main()
