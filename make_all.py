# -*- coding: utf-8 -*-
"""一键生成成果包：按正确顺序跑完全部步骤。

顺序很关键：
    1. build_package   先搭目录、复制代码与数据
    2. finalize        生成作品方案与 PPT 大纲，并导出它们的 PDF
    3. gen_ppt         生成答辩 PPT（.pptx）
    4. export_ppt_pdf  把 .pptx 导出为 .pdf（校赛要求 PDF 格式）
    5. checks          合规、数据一致性、几何检查

注意：build_package 会清空成果包目录，因此它必须排在最前，
否则会删掉第 3、4 步生成的文件。
"""
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PY = (r"C:\Users\ASUS\.dsh\dsh-runtimes\dsh-primary-runtime"
      r"\dependencies\python\python.exe")
NODE = r"E:\tool\dsh\resources\runtime\primary-runtime\dependencies\node\bin\node.exe"
CLI = (r"E:\tool\dsh\resources\app.asar.unpacked\dsh\node_modules"
       r"\@deepseek-ai\libreoffice-kit\lib\cli.js")
AIC = r"E:\harness\aic"
PKG = os.path.join(AIC, "成果包")
PPTX = os.path.join(PKG, "02_答辩PPT", "答辩PPT.pptx")
PPTPDF = os.path.join(PKG, "02_答辩PPT", "答辩PPT.pdf")


def run(script):
    print(f"\n{'='*66}\n运行 {script}\n{'='*66}")
    r = subprocess.run([PY, os.path.join(AIC, script)], cwd=AIC,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    out = (r.stdout or "").strip()
    if out:
        print(out)
    if r.returncode != 0:
        print(f"[失败] {script} 返回码 {r.returncode}")
        if r.stderr:
            print((r.stderr or "")[-1500:])
        return False
    return True


def export_ppt_pdf():
    print(f"\n{'='*66}\n导出 答辩PPT.pdf\n{'='*66}")
    os.makedirs(os.path.dirname(PPTPDF), exist_ok=True)
    if os.path.isfile(PPTPDF):
        try:
            os.remove(PPTPDF)
        except PermissionError:
            print("  目标 PDF 被占用，请先关闭阅读器后重试")
            return False
    r = subprocess.run([NODE, CLI, "convert", "--input", PPTX,
                        "--output", PPTPDF],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if os.path.isfile(PPTPDF):
        print(f"  OK {os.path.getsize(PPTPDF)/1024:.0f} KB")
        return True
    print("  导出失败：", (r.stdout or "")[-400:], (r.stderr or "")[-400:])
    return False


def main():
    steps = [
        ("build_package.py", "搭建成果包目录并复制代码与数据"),
        ("finalize_package.py", "生成作品方案与 PPT 大纲，导出 PDF"),
        ("gen_ppt.py", "生成答辩 PPT（.pptx）"),
    ]
    for script, desc in steps:
        if not run(script):
            print(f"\n流程中断于：{desc}")
            return 1
    if not export_ppt_pdf():
        return 1

    print(f"\n{'='*66}\n校验\n{'='*66}")
    for script in ("check_ppt_geometry.py", "check_ppt_compliance.py",
                   "check_consistency.py"):
        run(script)

    n = sz = 0
    for root, _d, files in os.walk(PKG):
        for f in files:
            n += 1
            sz += os.path.getsize(os.path.join(root, f))
    print(f"\n{'='*66}")
    print(f"成果包：{n} 个文件，{sz/1024/1024:.1f} MB")
    print("02_答辩PPT 内容：")
    d = os.path.join(PKG, "02_答辩PPT")
    for root, _dd, files in os.walk(d):
        for f in sorted(files):
            p = os.path.join(root, f)
            rel = os.path.relpath(p, d)
            print(f"    {os.path.getsize(p)/1024:8.0f} KB  {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
