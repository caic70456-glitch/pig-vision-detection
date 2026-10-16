# -*- coding: utf-8 -*-
"""从 PigDetect.zip 中按需解压部分图像与标签（避免一次性解压 1.2GB）。"""
import argparse
import os
import sys
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ZIP = r"E:\harness\aic\vision\data\pigdetect\PigDetect.zip"
OUT = r"E:\harness\aic\vision\data\pigdetect\extract"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "train", "test", "all"])
    ap.add_argument("--limit", type=int, default=60, help="每个 split 最多解压多少张图")
    ap.add_argument("--list", action="store_true", help="只列出结构统计")
    args = ap.parse_args()

    with zipfile.ZipFile(ZIP) as z:
        names = z.namelist()

        if args.list:
            from collections import Counter
            parts = Counter()
            for n in names:
                p = n.split("/")
                key = "/".join(p[:2]) if len(p) >= 2 else n
                parts[key] += 1
            print(f"zip 条目总数: {len(names)}")
            print(f"{'路径':<34}{'文件数':>8}")
            for k, v in sorted(parts.items(), key=lambda x: -x[1]):
                print(f"{k:<34}{v:>8}")
            return

        splits = ["dev", "train", "test"] if args.split == "all" else [args.split]
        total = 0
        for sp in splits:
            imgs = [n for n in names if n.startswith(f"{sp}/images/") and n.lower().endswith(
                (".jpg", ".jpeg", ".png"))]
            imgs = sorted(imgs)
            # 均匀抽样，覆盖不同来源
            step = max(1, len(imgs) // args.limit)
            picked = imgs[::step][:args.limit]
            print(f"[{sp}] 共 {len(imgs)} 张图，抽取 {len(picked)} 张"
                  f"（步长 {step}）")
            for n in picked:
                z.extract(n, OUT)
                # 同时解压对应标签
                lab = n.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt"
                if lab in names:
                    z.extract(lab, OUT)
                total += 1
        print(f"\n解压 {total} 张图 -> {OUT}")


if __name__ == "__main__":
    main()
