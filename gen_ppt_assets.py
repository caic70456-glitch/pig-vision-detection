# -*- coding: utf-8 -*-
"""为答辩 PPT 生成两张配图（真实模型输出，非示意）：

    图1  det_compare.png  同一张猪舍照片上，通用检测器与自训检测器的检出结果并排
    图2  behavior_seq.png 合成帧序列中某一帧的行为判定可视化

用途：替换 PPT 中的纯文字说明，让评委直接看到模型差异。
"""
import io
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, r"E:\harness\aic\vision")
import bootstrap  # noqa: F401,E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

VISION = r"E:\harness\aic\vision"
MODELS = os.path.join(VISION, "models")
TEST_IMG = os.path.join(VISION, "data", "pigdetect", "extract", "test", "images")
OUT = r"E:\harness\aic\ppt_assets"
os.makedirs(OUT, exist_ok=True)

IMG = "danuma_1262.jpg"     # 人工标注 23 头
TRUTH = 23

NAVY = (20, 44, 82)
RED = (192, 48, 43)
GREEN = (46, 125, 79)
WHITE = (255, 255, 255)


def font(size):
    for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc"):
        p = os.path.join(r"C:\Windows\Fonts", name)
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def detect(model_path, img_path):
    from ultralytics import YOLO
    m = YOLO(model_path)
    r = m.predict(img_path, conf=0.25, verbose=False)[0]
    boxes = []
    for b in r.boxes:
        xyxy = [float(v) for v in b.xyxy[0].tolist()]
        boxes.append((xyxy, float(b.conf[0]), int(b.cls[0])))
    names = r.names
    return boxes, names


def draw_panel(img, boxes, names, title, subtitle, color, only_pig=True):
    """在图片上画框并加标题条。only_pig=True 时只保留类别名为 pig 的框。"""
    W, H = img.size
    canvas = Image.new("RGB", (W, H + 92), WHITE)
    canvas.paste(img, (0, 92))
    d = ImageDraw.Draw(canvas)
    # 标题条
    d.rectangle([0, 0, W, 92], fill=NAVY)
    d.text((18, 14), title, font=font(30), fill=WHITE)
    d.text((18, 54), subtitle, font=font(21), fill=(168, 200, 232))
    shown = 0
    for xyxy, conf, cls in boxes:
        label = str(names.get(cls, cls)) if isinstance(names, dict) else str(names[cls])
        if only_pig and label.lower() != "pig":
            continue
        x1, y1, x2, y2 = xyxy
        d.rectangle([x1, y1 + 92, x2, y2 + 92], outline=color, width=4)
        shown += 1
    return canvas, shown


def fig_detection_compare():
    img_path = os.path.join(TEST_IMG, IMG)
    img = Image.open(img_path).convert("RGB")

    gen_boxes, gen_names = detect(os.path.join(MODELS, "_pretrained_coco_yolov8n.pt"),
                                  img_path)
    pig_boxes, pig_names = detect(os.path.join(MODELS, "pig-detector-yolov8n.pt"),
                                  img_path)

    # 左：通用检测器，画出所有动物类框（体现"把猪判成别的动物"）
    n_gen_pig = sum(1 for b in gen_boxes
                    if str(gen_names.get(b[2], "")).lower() == "pig")
    left, n_left = draw_panel(
        img, gen_boxes, gen_names,
        "通用预训练检测器（COCO 80 类）",
        f"检测到 {len(gen_boxes)} 个目标，其中判为 pig 的 {n_gen_pig} 个",
        RED, only_pig=False)
    # 右：自训检测器
    right, n_right = draw_panel(
        img, pig_boxes, pig_names,
        "自训单类检测器（pig）",
        "检测中……",
        GREEN, only_pig=True)
    # 标题条上的数量在画完后回填，避免在函数返回前引用变量
    d2 = ImageDraw.Draw(right)
    d2.rectangle([0, 46, right.width, 92], fill=NAVY)
    d2.text((18, 54), f"检测到 {n_right} 头猪（人工标注 {TRUTH} 头）",
            font=font(21), fill=(168, 232, 200))

    # 并排
    W = left.width + right.width + 24
    H = max(left.height, right.height)
    canvas = Image.new("RGB", (W, H), WHITE)
    canvas.paste(left, (0, 0))
    canvas.paste(right, (left.width + 24, 0))
    out = os.path.join(OUT, "det_compare.png")
    canvas.save(out)
    print(f"图1 {out}  {canvas.size}  左 {len(gen_boxes)} 框 / 右 {n_right} 框")
    return out


def fig_behavior_seq():
    """合成帧序列的行为判定可视化（左右两帧对照）。"""
    from detector import build_backend
    import behavior
    import scene as sc
    from PIL import Image as I

    seq_dir = os.path.join(VISION, "synthetic_frames", "T5_采食后离开")
    meta_p = os.path.join(VISION, "synthetic_frames", "sequences.json")
    import json
    meta = json.load(io.open(meta_p, encoding="utf-8"))
    frames = None
    for s in meta["sequences"]:
        if s["name"] == "T5_采食后离开":
            frames = s["frames"]

    panels = []
    for fi in (6, 11):
        p = os.path.join(seq_dir, f"{fi:03d}.png")
        if not os.path.isfile(p):
            continue
        im = I.open(p).convert("RGB")
        W, H = im.size
        cv = I.new("RGB", (W, H + 92), WHITE)
        cv.paste(im, (0, 92))
        d = ImageDraw.Draw(cv)
        d.rectangle([0, 0, W, 92], fill=NAVY)
        d.text((18, 14), f"第 {fi+1} 帧", font=font(30), fill=WHITE)
        d.text((18, 54), "时序判定：比较相邻帧位移与框面积变化", font=font(21),
               fill=(168, 200, 232))
        for det in frames[fi]:
            x1, y1, x2, y2 = det["box"]
            d.rectangle([x1, y1 + 92, x2, y2 + 92], outline=GREEN, width=4)
        panels.append(cv)
    if len(panels) < 2:
        print("合成序列帧不足，跳过图2")
        return None
    W = panels[0].width + panels[1].width + 24
    H = max(p.height for p in panels)
    canvas = I.new("RGB", (W, H), WHITE)
    canvas.paste(panels[0], (0, 0))
    canvas.paste(panels[1], (panels[0].width + 24, 0))
    out = os.path.join(OUT, "behavior_seq.png")
    canvas.save(out)
    print(f"图2 {out}  {canvas.size}")
    return out


if __name__ == "__main__":
    fig_detection_compare()
    fig_behavior_seq()
