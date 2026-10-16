# -*- coding: utf-8 -*-
"""设施区域标定工具（GUI）。

用法：
    python annotate_regions.py 猪舍照片.jpg                 # 开始标定
    python annotate_regions.py 照片.jpg --load regions.json # 载入已有配置继续改
    python annotate_regions.py 照片.jpg --out my_regions.json
    python annotate_regions.py --check regions.json         # 只校验已有配置

操作说明（界面内也有提示）：
    1/2/3/4      切换要画的区域类型（食槽 / 饮水器 / 保温区 / 栏舍边界）
    鼠标左键拖拽  画出矩形
    鼠标右键点击  删除该区域内的框
    Ctrl+Z       撤销上一个框
    Ctrl+S       保存                 Ctrl+O 载入
    R            重置全部
    Esc / 关闭窗口 退出（未保存会提示）

标定建议：
    - 食槽 / 饮水器是**必需**的，行为识别里的「采食」「饮水」直接依赖它们
    - 同一类区域可画多个框（例如两侧各有一个食槽）
    - 框要尽量贴合设施实际占地区域，宁小勿大：框太大会把栏中的猪也误判为在采食
"""
import argparse
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bootstrap  # noqa: F401,E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PIL import Image, ImageDraw, ImageTk  # noqa: E402

import regions as R  # noqa: E402

CANVAS_W, CANVAS_H = 1000, 680          # 画布逻辑尺寸上限
PAD = 24


class Annotator:
    def __init__(self, root, image_path, config_path, out_path):
        self.root = root
        self.image_path = image_path
        self.out_path = out_path
        self.config_path = config_path

        self.img = Image.open(image_path).convert("RGB")
        self.iw, self.ih = self.img.size

        self.order = list(R.REGION_TYPES.keys())
        self.current = self.order[0]
        self.boxes = {k: [] for k in self.order}        # 像素坐标
        self.dirty = False
        self.drag_box = None                            # 拖拽中的临时框
        self.start = None

        self._build_ui()
        self._fit_image()
        self._redraw()
        if config_path:
            self._load_from(config_path)

    # ---------------- UI ----------------
    def _build_ui(self):
        self.root.title(f"设施区域标定 — {os.path.basename(self.image_path)}")
        top = tk.Frame(self.root)
        top.pack(side=tk.TOP, fill=tk.X)

        self.info = tk.Label(top, anchor="w", justify=tk.LEFT, font=("Microsoft YaHei", 10))
        self.info.pack(side=tk.LEFT, padx=10, pady=6)

        self.status = tk.Label(self.root, anchor="w", font=("Microsoft YaHei", 10),
                               fg="#1f6f3c")
        self.status.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=4)

        bar = tk.Frame(self.root)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        for i, k in enumerate(self.order, start=1):
            meta = R.REGION_TYPES[k]
            txt = f"{i}. {meta['label_cn']}" + ("*" if meta["required"] else "")
            b = tk.Button(bar, text=txt, width=13,
                          command=lambda kk=k: self._set_type(kk))
            b.pack(side=tk.LEFT, padx=3, pady=5)
        tk.Button(bar, text="撤销 Ctrl+Z", command=self.undo).pack(side=tk.LEFT, padx=3)
        tk.Button(bar, text="重置 R", command=self.reset).pack(side=tk.LEFT, padx=3)
        tk.Button(bar, text="保存 Ctrl+S", command=self.save).pack(side=tk.LEFT, padx=3)
        tk.Button(bar, text="载入 Ctrl+O", command=self.open_file).pack(side=tk.LEFT, padx=3)
        tk.Button(bar, text="校验", command=self.check).pack(side=tk.LEFT, padx=3)

        self.canvas = tk.Canvas(self.root, width=self.disp_w_max(), height=CANVAS_H,
                                bg="#222", highlightthickness=0)
        self.canvas.pack(side=tk.TOP, expand=True, fill=tk.BOTH)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.on_right)
        self.root.bind("<Key>", self.on_key)
        self.root.bind("<Control-s>", lambda e: self.save())
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._update_info()

    def disp_w_max(self):
        return CANVAS_W

    # ---------------- 坐标换算 ----------------
    def _fit_image(self):
        """按比例缩放到画布内，记录缩放比与偏移。"""
        cw = max(320, self.canvas.winfo_reqwidth())
        ch = max(240, self.canvas.winfo_reqheight())
        avail_w = cw - 2 * PAD
        avail_h = ch - 2 * PAD
        self.scale = min(avail_w / self.iw, avail_h / self.ih)
        self.dw, self.dh = int(self.iw * self.scale), int(self.ih * self.scale)
        self.ox = (cw - self.dw) // 2
        self.oy = (ch - self.dh) // 2

    def to_disp(self, x, y):
        return self.ox + x * self.scale, self.oy + y * self.scale

    def to_img(self, x, y):
        return ((x - self.ox) / self.scale, (y - self.oy) / self.scale)

    # ---------------- 绘制 ----------------
    def _redraw(self):
        self.canvas.delete("all")
        disp = self.img.resize((self.dw, self.dh), Image.LANCZOS)
        # 半透明叠加当前区域的框
        base = disp.convert("RGBA")
        ov = Image.new("RGBA", base.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        for k in self.order:
            col = R.REGION_TYPES[k]["color"]
            a = 130 if k == self.current else 70
            for (x1, y1, x2, y2) in self.boxes[k]:
                dx1, dy1 = self.to_disp(x1, y1)
                dx2, dy2 = self.to_disp(x2, y2)
                od.rectangle([dx1 - self.ox, dy1 - self.oy, dx2 - self.ox, dy2 - self.oy],
                             fill=col + (a,), outline=col + (255,), width=3)
        base = Image.alpha_composite(base, ov).convert("RGB")
        # 用 ImageDraw 写字需要字体；改用 Canvas 文字更简单，这里只贴图
        self.tkimg = ImageTk.PhotoImage(base)
        self.canvas.create_image(self.ox, self.oy, anchor="nw", image=self.tkimg)

        # 用 Canvas 画边框与标签（文字更清晰）
        for k in self.order:
            col = "#%02x%02x%02x" % R.REGION_TYPES[k]["color"]
            for i, (x1, y1, x2, y2) in enumerate(self.boxes[k]):
                dx1, dy1 = self.to_disp(x1, y1)
                dx2, dy2 = self.to_disp(x2, y2)
                self.canvas.create_rectangle(dx1, dy1, dx2, dy2, outline=col,
                                             width=3 if k == self.current else 2)
                self.canvas.create_text(dx1 + 4, dy1 + 10, anchor="w",
                                        text=f"{R.REGION_TYPES[k]['label_cn']}{i+1}",
                                        fill=col, font=("Microsoft YaHei", 11, "bold"))
        if self.drag_box:
            dx1, dy1 = self.to_disp(*self.drag_box[:2])
            dx2, dy2 = self.to_disp(*self.drag_box[2:])
            col = "#%02x%02x%02x" % R.REGION_TYPES[self.current]["color"]
            self.canvas.create_rectangle(dx1, dy1, dx2, dy2, outline=col, width=2,
                                         dash=(6, 4))

    def _update_info(self):
        meta = R.REGION_TYPES[self.current]
        cnt = {k: len(self.boxes[k]) for k in self.order}
        s = "　".join(f"{R.REGION_TYPES[k]['label_cn']}:{cnt[k]}" for k in self.order)
        self.info.config(
            text=(f"图像 {self.iw}×{self.ih}　当前类型：{meta['label_cn']}"
                  f"{'（必需）' if meta['required'] else ''}\n"
                  f"已画：{s}　　左键拖拽画框 · 右键删框 · 数字键切换类型"))
        self.status.config(text=f"输出：{self.out_path}" + ("　● 有未保存修改" if self.dirty else ""))

    # ---------------- 事件 ----------------
    def _set_type(self, k):
        self.current = k
        self._redraw()
        self._update_info()

    def on_press(self, e):
        if not (self.ox <= e.x <= self.ox + self.dw and self.oy <= e.y <= self.oy + self.dh):
            return
        self.start = self.to_img(e.x, e.y)
        self.drag_box = (*self.start, *self.start)

    def on_drag(self, e):
        if not getattr(self, "drag_box", None):
            return
        x, y = self.to_img(e.x, e.y)
        x = min(max(x, 0), self.iw)
        y = min(max(y, 0), self.ih)
        self.drag_box = (self.start[0], self.start[1], x, y)
        self._redraw()

    def on_release(self, e):
        if not getattr(self, "drag_box", None):
            return
        x1, y1, x2, y2 = self.drag_box
        self.drag_box = None
        if abs(x2 - x1) < 6 or abs(y2 - y1) < 6:      # 太小的拖动忽略
            self._redraw()
            return
        box = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        self.boxes[self.current].append(box)
        self.dirty = True
        self._redraw()
        self._update_info()

    def on_right(self, e):
        x, y = self.to_img(e.x, e.y)
        for k in self.order:
            for i, (x1, y1, x2, y2) in enumerate(self.boxes[k]):
                if x1 <= x <= x2 and y1 <= y <= y2:
                    del self.boxes[k][i]
                    self.dirty = True
                    self._redraw()
                    self._update_info()
                    return

    def on_key(self, e):
        if e.keysym in ("1", "2", "3", "4"):
            idx = int(e.keysym) - 1
            if idx < len(self.order):
                self._set_type(self.order[idx])
        elif e.keysym.lower() == "r":
            self.reset()
        elif e.keysym == "Escape":
            self.on_close()

    def undo(self):
        for k in reversed(self.order):
            if self.boxes[k]:
                self.boxes[k].pop()
                self.dirty = True
                self._redraw()
                self._update_info()
                return

    def reset(self):
        if messagebox.askyesno("重置", "确定清空所有已画的区域框？"):
            self.boxes = {k: [] for k in self.order}
            self.dirty = True
            self._redraw()
            self._update_info()

    # ---------------- 存取 ----------------
    def _build_config(self):
        cfg = R.empty_config((self.iw, self.ih), os.path.basename(self.image_path))
        for k in self.order:
            cfg["regions"][k]["boxes"] = [
                [round(x1 / self.iw, 6), round(y1 / self.ih, 6),
                 round(x2 / self.iw, 6), round(y2 / self.ih, 6)]
                for (x1, y1, x2, y2) in self.boxes[k]
            ]
        return cfg

    def save(self):
        cfg = self._build_config()
        R.save_config(cfg, self.out_path)
        self.dirty = False
        problems = R.validate(cfg)
        self._update_info()
        if problems:
            messagebox.showwarning("已保存，但有问题",
                                   "已保存到：\n%s\n\n需要注意：\n- %s"
                                   % (self.out_path, "\n- ".join(problems)))
        else:
            messagebox.showinfo("已保存", f"已保存到：\n{self.out_path}\n\n校验通过。")

    def open_file(self):
        p = filedialog.askopenfilename(title="选择区域配置", initialdir=os.path.dirname(self.out_path),
                                       filetypes=[("JSON", "*.json"), ("全部", "*.*")])
        if p:
            self._load_from(p)

    def _load_from(self, path):
        cfg = R.load_config(path)
        if not cfg:
            return
        regs = cfg.get("regions") or {}
        loaded = 0
        for k in self.order:
            bs = (regs.get(k) or {}).get("boxes") or []
            self.boxes[k] = [(b[0] * self.iw, b[1] * self.ih, b[2] * self.iw, b[3] * self.ih)
                             for b in bs if len(b) == 4]
            loaded += len(self.boxes[k])
        self.dirty = False
        self._redraw()
        self._update_info()
        print(f"已载入 {path}：{loaded} 个区域框")

    def check(self):
        problems = R.validate(self._build_config())
        if problems:
            messagebox.showwarning("校验未通过", "\n- " + "\n- ".join(problems))
        else:
            messagebox.showinfo("校验通过", "必需区域齐全，坐标合法。")

    def on_close(self):
        if self.dirty:
            r = messagebox.askyesnocancel("未保存", "有未保存的修改，是否保存后退出？")
            if r is None:
                return
            if r:
                self.save()
        self.root.destroy()


def check_only(path):
    cfg = R.load_config(path)
    if not cfg:
        print(f"无法读取 {path}")
        return 1
    problems = R.validate(cfg)
    print(f"配置：{path}")
    print(f"标定图像：{cfg.get('source_image')}  尺寸 {cfg.get('image_size')}")
    for k in R.REGION_TYPES:
        n = len((cfg.get("regions", {}).get(k) or {}).get("boxes") or [])
        req = "必需" if R.REGION_TYPES[k]["required"] else "可选"
        print(f"  {R.REGION_TYPES[k]['label_cn']:<6} {req}  框数 {n}")
    print()
    if problems:
        print("问题：")
        for p in problems:
            print("  -", p)
        return 1
    print("校验通过。")
    return 0


def main():
    ap = argparse.ArgumentParser(description="设施区域标定工具")
    ap.add_argument("image", nargs="?", help="要标定的猪舍照片")
    ap.add_argument("--out", help="输出配置路径（默认与照片同目录的 regions.json）")
    ap.add_argument("--load", help="载入已有配置继续编辑")
    ap.add_argument("--check", help="只校验已有配置，不启动界面")
    args = ap.parse_args()

    if args.check:
        sys.exit(check_only(args.check))

    if not args.image:
        ap.print_help()
        return
    if not os.path.isfile(args.image):
        print(f"图像不存在：{args.image}")
        return

    out = args.out
    if not out:
        d = os.path.dirname(os.path.abspath(args.image))
        out = os.path.join(d, R.DEFAULT_CONFIG_NAME)
    load = args.load
    if not load:
        # 若同目录已有配置，自动载入以便继续调整
        cand = os.path.join(os.path.dirname(os.path.abspath(args.image)), R.DEFAULT_CONFIG_NAME)
        if os.path.isfile(cand) and os.path.abspath(cand) != os.path.abspath(out):
            load = cand
        elif os.path.isfile(cand):
            load = cand

    root = tk.Tk()
    Annotator(root, args.image, load, out)
    root.mainloop()


if __name__ == "__main__":
    main()
