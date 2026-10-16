# -*- coding: utf-8 -*-
"""验证网页端在「真猪检测器」下的表现：内置合成场景 + 真实图片上传。"""
import io
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8100"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=180) as r:
        return r.status, r.read().decode("utf-8", "replace")


def post_image(path, field="image"):
    import os
    boundary = "----dshtestboundary"
    name = os.path.basename(path)
    with open(path, "rb") as fh:
        data = fh.read()
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="{field}"; filename="{name}"\r\n'.encode()
    body += b"Content-Type: image/jpeg\r\n\r\n"
    body += data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        BASE + "/upload", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.status, r.read().decode("utf-8", "replace")


print("=== 1) 首页：后端能力 ===")
st, html = get("/")
print(f"  HTTP {st}  长度 {len(html)}")
for k in ["识别「猪」类别能力", "ultralytics-yolo", "pig-detector"]:
    print(f"  含「{k}」: {k in html}")
print(f"  仍显示「近似检测」警示: {'COCO 数据集没有 pig 类别' in html}")

print("\n=== 2) 合成场景 ===")
st, html = get("/?act=scenes")
print(f"  HTTP {st}  内嵌图 {html.count('data:image/png;base64')} 张")

print("\n=== 3) 上传真实猪舍图片 ===")
img = r"E:\harness\aic\vision\data\pigdetect\extract\test\images\danuma_1265.jpg"
st, html = post_image(img)
print(f"  HTTP {st}  长度 {len(html)}")
for k in ["目标数", "pig", "巡检报告", "争斗"]:
    print(f"  含「{k}」: {k in html}")
import re
m = re.search(r"目标数：(\d+)", html)
if m:
    print(f"  → 检出目标数: {m.group(1)}")
m2 = re.search(r"行为构成：([^<]*)", html)
if m2:
    print(f"  → 行为构成: {m2.group(1)[:120]}")
