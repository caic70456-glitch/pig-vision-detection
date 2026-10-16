# -*- coding: utf-8 -*-
"""数据一致性校验：把文档中的关键数字与结果文件逐项比对。

起因：文档里的数字原先手写，改过抽取算法后未同步，导致「22 种疾病、259 条症状关联」
与知识库实际的 21 种、211 条不符。本脚本用于提交前自动核对，防止再次出现。
"""
import io
import os
import re
import sys
import zipfile

sys.path.insert(0, r"E:\harness\aic")
import metrics_source as M  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PKG = r"E:\harness\aic\成果包"


def docx_text(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    return re.sub(r"<[^>]+>", "", xml)


def main():
    KB = M.kb_stats()
    DX = M.dx_eval()
    DET = M.detection()

    docs = []
    for root, _d, files in os.walk(PKG):
        for f in files:
            if f.endswith(".docx"):
                docs.append(os.path.join(root, f))

    print("=== 结果文件中的真值 ===")
    print(f"  知识库：{KB['docs']} 篇文献 / {KB['diseases']} 种疾病 / {KB['symptoms']} 条关联")
    print(f"  诊断：Top-1 {DX.get('top1',0):.1%}  Top-3 {DX.get('top3',0):.1%}  "
          f"MRR {DX.get('mrr',0):.3f}  安全 {DX.get('safety_passed')}/{DX.get('safety_n')}")
    print(f"  分层：证据充分 {DX.get('strong_n')} 例 {DX.get('strong_top3',0):.1%} / "
          f"薄弱 {DX.get('weak_n')} 例 {DX.get('weak_top3',0):.1%}")
    print(f"  检测：mAP50 {DET.get('map50',0):.4f}  mAP50-95 {DET.get('map5095',0):.4f}  "
          f"P {DET.get('precision',0):.4f}  R {DET.get('recall',0):.4f}")

    # 必须出现的新数字（仅对含该主题的文档要求）
    checks = [
        ("作品方案", ["21 种疾病", "211 条症状关联"],
         ["22 种疾病", "259 条症状关联", "22 种猪病", "259 条关联"]),
        ("答辩PPT大纲", ["21 种疾病", "211 条症状关联"],
         ["22 种疾病", "259 条症状关联"]),
    ]

    print("\n=== 逐份核对 ===")
    all_ok = True
    for d in docs:
        name = os.path.basename(d)
        txt = docx_text(d)
        # 按文件名判断属于哪一类文档
        if "作品方案" in name:
            key = "作品方案"
        elif "PPT" in name or "ppt" in name:
            key = "答辩PPT大纲"
        else:
            continue
        want, forbid = None, None
        for k, w, f in checks:
            if k == key:
                want, forbid = w, f
                break
        if want is None:
            print(f"  跳过（无对应校验项）{name}")
            continue
        missing = [s for s in want if s not in txt]
        stale = [s for s in forbid if s in txt]
        ok = not missing and not stale
        all_ok &= ok
        print(f"  {'OK ' if ok else '问题'} {name}")
        if missing:
            print(f"       缺少应有表述：{missing}")
        if stale:
            print(f"       仍含旧数字：{stale}")

    # 全库扫描任何残留的旧数字组合
    # 说明：源代码目录下的 README 记录了知识库的迭代过程（中间数字 259 → 最终 211），
    # 属于开发文档而非提交材料，允许出现旧数字。这里只扫描提交材料。
    print("\n=== 扫描提交材料中的旧数字 ===")
    hits = []
    ALLOW = ("03_源代码",)          # 开发文档，允许记录中间数字
    for root, _d, files in os.walk(PKG):
        rel_root = os.path.relpath(root, PKG)
        if any(rel_root.startswith(a) for a in ALLOW):
            continue
        for f in files:
            if not f.endswith((".docx", ".md", ".json", ".txt", ".tsv")):
                continue
            p = os.path.join(root, f)
            if f.endswith(".docx"):
                t = docx_text(p)
            else:
                t = io.open(p, encoding="utf-8", errors="ignore").read()
            for pat in ("259 条", "259条", "22 种疾病", "22种疾病", "22 种猪病"):
                if pat in t:
                    hits.append((os.path.relpath(p, PKG), pat))
    if hits:
        all_ok = False
        for rel, pat in hits:
            print(f"  残留：{rel}  含「{pat}」")
    else:
        print("  提交材料中未发现 259 条 / 22 种 的残留")
    print("  （03_源代码 下的说明文件记录了迭代过程，含中间数字，属正常）")

    print(f"\n数据一致性：{'通过' if all_ok else '存在问题'}")
    return all_ok


if __name__ == "__main__":
    main()
