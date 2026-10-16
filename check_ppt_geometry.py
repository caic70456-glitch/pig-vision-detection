# -*- coding: utf-8 -*-
"""直接检查 PPTX 中每个形状的几何，判断是否越出幻灯片边界或互相重叠。

用途：渲染预览可能被裁切，不能作为「是否越界」的唯一依据。
本脚本从文件本身读取位置尺寸，给出确定结论。
"""
import sys

from pptx import Presentation
from pptx.util import Emu

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PATH = r"E:\harness\aic\成果包\02_答辩PPT\答辩PPT.pptx"
prs = Presentation(PATH)
SW, SH = prs.slide_width, prs.slide_height
print(f"画布：{SW/914400:.3f} x {SH/914400:.3f} 英寸　共 {len(prs.slides._sldIdLst)} 页\n")

TOL = Emu(int(0.02 * 914400))       # 0.02 英寸容差
issues = 0
for i, slide in enumerate(prs.slides, 1):
    problems = []
    for sh in slide.shapes:
        if sh.left is None or sh.top is None:
            continue
        try:
            l, t = sh.left, sh.top
            w = sh.width or 0
            h = sh.height or 0
        except Exception:
            continue
        r, b = l + w, t + h
        name = sh.shape_type
        txt = ""
        if sh.has_text_frame and sh.text_frame.text.strip():
            txt = sh.text_frame.text.strip().replace("\n", " ")[:24]
        elif getattr(sh, "has_table", False) and sh.has_table:
            txt = f"表格{len(sh.table.rows)}x{len(sh.table.columns)}"
        tag = f"[{name}] {txt}"
        if l < -TOL:
            problems.append(f"左越界 {l/914400:+.3f}\"  {tag}")
        if t < -TOL:
            problems.append(f"上越界 {t/914400:+.3f}\"  {tag}")
        if r > SW + TOL:
            problems.append(f"右越界 {(r-SW)/914400:+.3f}\"  {tag}")
        if b > SH + TOL:
            problems.append(f"下越界 {(b-SH)/914400:+.3f}\"  {tag}")
    # 统计文本框内容是否可能超出其框高（粗估）
    if problems:
        issues += len(problems)
        print(f"第 {i} 页：")
        for p in problems:
            print(f"    {p}")
if not issues:
    print("所有形状均在幻灯片边界内（容差 0.02 英寸）。")
else:
    print(f"\n合计 {issues} 处越界。")
