# -*- coding: utf-8 -*-
"""标定工具的自动化冒烟测试：不靠人工点击，模拟画框、撤销、保存、载入。"""
import io
import json
import os
import sys
import tkinter as tk

sys.path.insert(0, r"E:\harness\aic\vision")
import bootstrap  # noqa: F401,E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import annotate_regions as A  # noqa: E402
import regions as R  # noqa: E402

IMG = r"E:\harness\aic\vision\data\pigdetect\extract\test\images\danuma_1262.jpg"
OUT = r"E:\harness\aic\vision\data\pigdetect\extract\test\_smoketest_regions.json"

root = tk.Tk()
app = A.Annotator(root, IMG, None, OUT)
root.update()
print(f"[1] 初始化 OK   图像 {app.iw}x{app.ih}  缩放 {app.scale:.3f}")
print(f"    画布偏移 ({app.ox},{app.oy})  绘制尺寸 {app.dw}x{app.dh}")

# 模拟画两个框：先在 feeder 上，再切到 drinker 画一个
app._set_type("feeder")
p1 = app.to_disp(150, 10)
p2 = app.to_disp(520, 60)
app.on_press(type("E", (), {"x": p1[0], "y": p1[1]})())
app.on_drag(type("E", (), {"x": p2[0], "y": p2[1]})())
app.on_release(type("E", (), {"x": p2[0], "y": p2[1]})())
root.update()
print(f"[2] 画食槽后: {len(app.boxes['feeder'])} 个框  dirty={app.dirty}")

app._set_type("drinker")
p3 = app.to_disp(430, 230)
p4 = app.to_disp(640, 350)
app.on_press(type("E", (), {"x": p3[0], "y": p3[1]})())
app.on_drag(type("E", (), {"x": p4[0], "y": p4[1]})())
app.on_release(type("E", (), {"x": p4[0], "y": p4[1]})())
root.update()
print(f"[3] 画饮水器后: 食槽 {len(app.boxes['feeder'])}  饮水器 {len(app.boxes['drinker'])}")

# 撤销
app.undo()
root.update()
print(f"[4] 撤销后: 饮水器 {len(app.boxes['drinker'])} 个框")

# 重新画回，然后保存
app.on_press(type("E", (), {"x": p3[0], "y": p3[1]})())
app.on_drag(type("E", (), {"x": p4[0], "y": p4[1]})())
app.on_release(type("E", (), {"x": p4[0], "y": p4[1]})())
cfg = app._build_config()
R.save_config(cfg, OUT)
print(f"[5] 保存 OK -> {OUT}  ({os.path.getsize(OUT)} 字节)")

# 校验
problems = R.validate(cfg)
print(f"[6] 校验: {'通过' if not problems else problems}")

# 载入回来
app2_boxes = {}
cfg2 = R.load_config(OUT)
from PIL import Image  # noqa: E402
W, H = Image.open(IMG).size
regs = R.to_pixel_regions(cfg2, (W, H))
print(f"[7] 载入并转像素区域: {len(regs)} 个 -> "
      + "; ".join(f"{r.name}({r.label_cn}) x1={r.box[0]:.0f} y1={r.box[1]:.0f}" for r in regs))

# 用该配置跑一次流水线，确认端到端可用
import pipeline  # noqa: E402
rep = pipeline.analyze_image(IMG, regions=cfg2)
print(f"[8] 端到端: 后端 {rep['detector']['backend']}  "
      f"区域已标定={rep['detector'].get('regions_calibrated')}  "
      f"目标 {rep['scene']['animal_count']}  "
      f"采食 {rep['behavior']['distribution_pct'].get('eating',0):.1f}%")

root.destroy()
os.remove(OUT)
print("\n冒烟测试全部通过，已清理临时文件。")
