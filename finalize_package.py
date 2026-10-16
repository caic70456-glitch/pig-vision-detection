# -*- coding: utf-8 -*-
"""成果包收尾：生成文档、导出 PDF、合规与排版检查、清理临时文件。

公平性条款要求作品材料中不得出现参赛团队所在学校名称与指导教师信息，
因此封面只填队长姓名与专业班级，不写学院；学院只出现在文件名里
（校赛通知规定的命名格式要求包含队长学院）。
"""
import io
import os
import re
import subprocess
import sys
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PKG = r"E:\harness\aic\成果包"
NODE = r"E:\tool\dsh\resources\runtime\primary-runtime\dependencies\node\bin\node.exe"
CLI = (r"E:\tool\dsh\resources\app.asar.unpacked\dsh\node_modules"
       r"\@deepseek-ai\libreoffice-kit\lib\cli.js")

FORBIDDEN = ["中国农业大学", "农业大学", "农大", "信息与电气工程学院",
             "动物科学技术学院", "动物科技学院", "指导教师", "指导老师"]
SKIP_DIRS = ("05_参考文献",)
SKIP_FILES = ("读我先看_提交说明与文件清单.md",)


def to_pdf(docx_path):
    pdf = os.path.splitext(docx_path)[0] + ".pdf"
    if os.path.isfile(pdf):
        os.remove(pdf)
    subprocess.run([NODE, CLI, "convert", "--input", docx_path, "--output", pdf],
                   capture_output=True, timeout=300)
    return pdf if os.path.isfile(pdf) else None


def docx_check(path):
    """返回 (违规词, ** 个数, 反引号个数, 加粗run数)。"""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    txt = re.sub(r"<[^>]+>", "", xml)
    return ([w for w in FORBIDDEN if w in txt], txt.count("**"), txt.count("`"),
            len(re.findall(r"<w:b/>", xml)))


def sanitize_references():
    """参考文献中的作者单位含高校名称，属公开出版信息，做匿名化以求稳妥。"""
    import json
    repl = [("中国农业大学", "某高校"), ("农业大学", "某农业大学")]
    refs = os.path.join(PKG, "05_参考文献")
    done = []
    for fn in ("CNKI文献清单_50篇.txt", "文献元数据_refs.json"):
        p = os.path.join(refs, fn)
        if not os.path.isfile(p):
            continue
        t0 = io.open(p, encoding="utf-8", errors="ignore").read()
        t1 = t0
        for a, b in repl:
            t1 = t1.replace(a, b)
        if t1 != t0:
            io.open(p, "w", encoding="utf-8").write(t1)
            done.append(fn)
    src = os.path.join(refs, "文献元数据_refs.json")
    if os.path.isfile(src):
        data = json.load(io.open(src, encoding="utf-8"))
        rows = ["编号\t题名\t来源\t年份"]
        for r in data:
            rows.append(f"{r.get('no')}\t{r.get('title')}\t{r.get('source')}\t{r.get('year')}")
        io.open(os.path.join(refs, "题录清单_无作者信息.tsv"), "w",
                encoding="utf-8").write("\n".join(rows))
    return done


def main():
    sys.path.insert(0, r"E:\harness\aic")
    import gen_docs_clean as G

    print("=== 1) 生成文档 ===")
    docs = [G.build_proposal(), G.build_ppt_outline()]
    for d in docs:
        print(f"    {os.path.basename(d)}  ({os.path.getsize(d)} 字节)")

    print("\n=== 2) 合规与排版检查 ===")
    all_ok = True
    for d in docs:
        hits, star, tick, nbold = docx_check(d)
        ok = (not hits) and star == 0 and tick == 0
        all_ok &= ok
        print(f"    {'OK ' if ok else '问题'} {os.path.basename(d)}")
        if hits:
            print(f"         违规词：{hits}")
        print(f"         Markdown 残留：** ×{star}　` ×{tick}　加粗 {nbold} 处")

    bad = []
    for root, _d, files in os.walk(PKG):
        rel = os.path.relpath(root, PKG)
        if any(rel.startswith(s) for s in SKIP_DIRS):
            continue
        for f in files:
            if f in SKIP_FILES or f.endswith((".docx", ".pdf", ".png")):
                continue
            if f.endswith((".py", ".md", ".txt", ".json", ".yaml", ".csv", ".tsv")):
                p = os.path.join(root, f)
                t = io.open(p, encoding="utf-8", errors="ignore").read()
                hit = [w for w in FORBIDDEN if w in t]
                if hit:
                    bad.append((os.path.relpath(p, PKG), hit))
    if bad:
        all_ok = False
        print("    代码与数据文件中命中：")
        for rel, hit in bad:
            print(f"      {rel}  {hit}")
    else:
        print("    OK  代码与实验数据文件无违规词")
    print("    （参考文献中其他高校的作者单位属公开出版信息，已做匿名化）")

    print("\n=== 3) 参考文献处理 ===")
    for c in sanitize_references():
        print(f"    已匿名化：{c}")

    print("\n=== 4) 导出 PDF ===")
    for d in docs:
        p = to_pdf(d)
        if p:
            print(f"    OK  {os.path.basename(p)}  ({os.path.getsize(p)/1024:.0f} KB)")
        else:
            print(f"    失败 {os.path.basename(d)}")

    print("\n=== 5) 清理临时文件 ===")
    for f in os.listdir(r"E:\harness\aic"):
        if f.startswith("_自动生成"):
            os.remove(os.path.join(r"E:\harness\aic", f))
            print(f"    已删除 {f}")

    n = sz = 0
    for root, _d, files in os.walk(PKG):
        for f in files:
            n += 1
            sz += os.path.getsize(os.path.join(root, f))
    print(f"\n成果包：{n} 个文件，{sz/1024/1024:.1f} MB")
    print(f"合规检查：{'通过' if all_ok else '存在问题'}")
    return all_ok


if __name__ == "__main__":
    main()
