# -*- coding: utf-8 -*-
"""检查 PigDetect 的 YOLO 标签类别分布。"""
import collections
import glob
import io
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

for split in ("test", "dev"):
    d = rf"E:\harness\aic\vision\data\pigdetect\extract\{split}\labels"
    fs = glob.glob(os.path.join(d, "*.txt"))
    cls, nbox = collections.Counter(), 0
    for f in fs:
        for line in io.open(f, encoding="utf-8"):
            p = line.split()
            if len(p) >= 5:
                cls[p[0]] += 1
                nbox += 1
    print(f"[{split}] 标签文件 {len(fs)} 个，总框 {nbox} 个")
    print(f"        类别分布: {dict(cls)}")
    if fs:
        print(f"        样例 {os.path.basename(fs[0])}:")
        for line in list(io.open(fs[0], encoding="utf-8"))[:3]:
            print("          ", line.strip())
    print()
