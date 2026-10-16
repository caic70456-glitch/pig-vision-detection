# -*- coding: utf-8 -*-
"""依赖引导：把项目自带的 pylibs 目录加入 sys.path。

背景：本机网络只允许访问 pypi.org 与 download.pytorch.org，
torch/torchvision/onnxruntime 被安装到项目内的 vision/pylibs 目录
（而非全局 site-packages），因此每个入口脚本都需要在导入它们之前
先把该目录加入 sys.path。

用法：在任何会 import torch / onnxruntime 的模块最前面
    import bootstrap  # noqa: F401
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
PYLIBS = os.path.join(_HERE, "pylibs")

if os.path.isdir(PYLIBS) and PYLIBS not in sys.path:
    sys.path.insert(0, PYLIBS)

# torchvision 的预训练权重缓存目录固定到项目内，避免重复下载
os.environ.setdefault("TORCH_HOME", os.path.join(_HERE, "models", "torch"))
