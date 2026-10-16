# -*- coding: utf-8 -*-
"""把成果包打成 zip。

用 Python 而非 PowerShell 的 Compress-Archive：后者遇到被阅读器打开的文件会
直接中断并留下不完整的压缩包。这里对单个文件做容错，被占用的先报告，
不写入不完整的压缩包。
"""
import os
import sys
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PKG = r"E:\harness\aic\成果包"
NAME = "AI+农业-动物科学技术学院-陈麒光-基于视觉行为感知的猪只疫病辅助诊断系统.zip"
ZIP = os.path.join(r"E:\harness\aic", NAME)
DOWNLOADS = r"C:\Users\ASUS\Downloads"


def main():
    if os.path.isfile(ZIP):
        os.remove(ZIP)

    locked = []
    n = 0
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, _d, files in os.walk(PKG):
            for f in sorted(files):
                p = os.path.join(root, f)
                arc = os.path.relpath(p, PKG)
                try:
                    z.write(p, arc)
                    n += 1
                except (PermissionError, OSError) as e:
                    locked.append((arc, str(e)))

    if locked:
        print("以下文件被占用，未能写入压缩包：")
        for arc, err in locked:
            print(f"  {arc}")
        print("\n请关闭对应的阅读器（WPS / Adobe 等）后重新运行本脚本。")
        os.remove(ZIP)
        print("已删除不完整的压缩包。")
        return 1

    size = os.path.getsize(ZIP) / 1024 / 1024
    print(f"压缩包已生成：{NAME}")
    print(f"  {n} 个文件，{size:.1f} MB")

    dst = os.path.join(DOWNLOADS, NAME)
    try:
        import shutil
        shutil.copy2(ZIP, dst)
        print(f"  已复制到 {DOWNLOADS}")
    except Exception as e:
        print(f"  复制到 Downloads 失败：{e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
