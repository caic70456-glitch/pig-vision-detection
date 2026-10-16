# -*- coding: utf-8 -*-
"""依赖引导：把项目自带的 pylibs 目录加入 sys.path。

背景：本机网络只允许访问 pypi.org 与 download.pytorch.org，
torch/torchvision/onnxruntime 被安装到项目内的 vision/pylibs 目录
（而非全局 site-packages），因此每个入口脚本都需要在导入它们之前
先把该目录加入 sys.path。

用法：在任何会 import torch / onnxruntime 的模块最前面
    import bootstrap  # noqa: F401
"""
import glob
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
PYLIBS = os.path.join(_HERE, "pylibs")


def _abi_tag():
    return "cp%d%d" % (sys.version_info.major, sys.version_info.minor)


def _pylibs_usable():
    """pylibs 内是按某一 CPython ABI 编译的二进制包（如 cp312）。

    当前解释器 ABI 不匹配时，把 pylibs 放进 sys.path 会让 numpy/torch 的
    C 扩展导入失败（ImportError: No module named 'numpy._core...'），
    反而遮蔽掉系统 site-packages 里可用的版本。因此仅在 ABI 一致时启用。
    """
    core = os.path.join(PYLIBS, "numpy", "_core")
    if not os.path.isdir(core):
        return True                      # 无二进制包，纯 Python，可直接用
    if glob.glob(os.path.join(core, "*%s*.pyd" % _abi_tag())):
        return True                      # ABI 一致
    return not glob.glob(os.path.join(core, "*cp3*.pyd"))  # 只有别的 ABI → 跳过


if os.path.isdir(PYLIBS) and PYLIBS not in sys.path and _pylibs_usable():
    sys.path.insert(0, PYLIBS)

# torchvision 的预训练权重缓存目录固定到项目内，避免重复下载
os.environ.setdefault("TORCH_HOME", os.path.join(_HERE, "models", "torch"))
