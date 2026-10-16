# -*- coding: utf-8 -*-
"""检测器抽象层：把「检测」与「行为识别」彻底解耦。

设计背景（关键）：
    1. COCO 的 80 个类别里没有 pig。所以 torchvision 的 COCO 预训练检测器
       检不出猪，只能检出 cow/sheep/horse 等近邻动物。
    2. 本机能访问的模型源只有 pypi.org 与 download.pytorch.org，
       GitHub / HuggingFace 均不可达，因此无法下载 YOLO 权重或带猪标注的数据集。

所以本模块提供统一接口，后端可插拔：
    - TorchvisionBackend : 立即可用（COCO 预训练，只认近邻动物，需显式声明）
    - OnnxBackend        : 用户自行提供 ONNX 猪只检测模型时使用（推荐，真正的猪检测）
    - MockBackend        : 无模型时的占位，用于跑通流程与演示界面

行为识别不依赖检测器的类别标签，而是依赖「目标位置 + 时间变化」，
因此即便检测器只给出「动物」这一粗类别，行为推理仍然成立。
"""
import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple

import bootstrap  # noqa: F401  # 把项目自带 pylibs 加入 sys.path（torch 等装在此处）

BASE = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE, "models")

# COCO 中与猪可能混淆的动物类别：用于「近似检测」模式下给出警示
PIG_NEIGHBORS = {"cow", "sheep", "horse", "dog", "cat"}


@dataclass
class Detection:
    """一个检测结果。"""
    box: Tuple[float, float, float, float]      # x1,y1,x2,y2（像素）
    label: str                                  # 类别名，如 animal / pig / feeder
    score: float                                # 置信度
    mask: Optional[object] = None               # 实例掩膜（numpy 数组），可选

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.box
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)

    @property
    def center(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.box
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def size(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.box
        return (x2 - x1, y2 - y1)

    def iou(self, other: "Detection") -> float:
        ax1, ay1, ax2, ay2 = self.box
        bx1, by1, bx2, by2 = other.box
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
        inter = iw * ih
        union = self.area + other.area - inter
        return inter / union if union > 0 else 0.0

    def to_dict(self) -> dict:
        d = asdict(self) if self.mask is None else {
            "box": self.box, "label": self.label, "score": self.score}
        d["box"] = [round(float(v), 1) for v in self.box]
        d["score"] = round(float(self.score), 4)
        d["area"] = round(self.area, 1)
        d["center"] = [round(v, 1) for v in self.center]
        return d


@dataclass
class DetectionResult:
    """一张图的完整检测输出。"""
    detections: List[Detection] = field(default_factory=list)
    backend: str = "unknown"
    approximate: bool = False       # True 表示「近似检测」：模型不认识 pig，只给了近邻动物
    warnings: List[str] = field(default_factory=list)
    image_size: Tuple[int, int] = (0, 0)    # (w, h)

    @property
    def animals(self) -> List[Detection]:
        return [d for d in self.detections if d.label == "animal"]

    def to_dict(self) -> dict:
        return {
            "backend": self.backend,
            "approximate": self.approximate,
            "warnings": self.warnings,
            "image_size": list(self.image_size),
            "animal_count": len(self.animals),
            "detections": [d.to_dict() for d in self.detections],
        }


# ============================================================
# 后端实现
# ============================================================

class BaseBackend:
    name = "base"
    can_detect_pig = False      # 该后端是否真的认识「猪」

    def detect(self, image) -> DetectionResult:
        raise NotImplementedError

    def describe(self) -> dict:
        return {"name": self.name, "can_detect_pig": self.can_detect_pig}


class TorchvisionBackend(BaseBackend):
    """torchvision COCO 预训练检测器。

    重要限制：COCO 没有 pig 类，本后端的输出是「动物」粗类别。
    会把 cow/sheep/horse/dog 等近邻动物统一映射为「可能为猪的动物」，
    并置 approximate=True，由上层在结果中明确警示。
    """

    name = "torchvision-fasterrcnn-mobilenet320"
    can_detect_pig = False

    # 可选择把哪些 COCO 类别当作「疑似猪只」
    DEFAULT_NEIGHBORS = ["cow", "sheep", "horse", "dog"]

    def __init__(self, neighbors=None, min_score=0.5, torch_home=None):
        import torchvision
        from torchvision.models.detection import (
            fasterrcnn_mobilenet_v3_large_320_fpn,
            FasterRCNN_MobileNet_V3_Large_320_FPN_Weights,
        )
        os.environ.setdefault("TORCH_HOME", torch_home or os.path.join(MODELS_DIR, "torch"))
        self._tv = torchvision
        self._w = FasterRCNN_MobileNet_V3_Large_320_FPN_Weights.COCO_V1
        self._cats = self._w.meta["categories"]
        self.model = fasterrcnn_mobilenet_v3_large_320_fpn(weights=self._w)
        self.model.eval()
        self.min_score = min_score
        self.neighbors = set(neighbors or self.DEFAULT_NEIGHBORS)

    def detect(self, image) -> DetectionResult:
        """image: PIL.Image"""
        import torch
        from torchvision.transforms.functional import to_tensor

        w, h = image.size
        x = to_tensor(image.convert("RGB"))
        with torch.no_grad():
            out = self.model([x])[0]

        dets, warned = [], []
        for box, label_id, score in zip(out["boxes"], out["labels"], out["scores"]):
            s = float(score)
            if s < self.min_score:
                continue
            cname = self._cats[int(label_id)]
            if cname in self.neighbors:
                dets.append(Detection(tuple(float(v) for v in box), "animal", s))
                warned.append(cname)
            elif cname == "person":
                dets.append(Detection(tuple(float(v) for v in box), "person", s))

        return DetectionResult(
            detections=dets,
            backend=self.name,
            approximate=True,
            warnings=[
                "本检测器基于 COCO 预训练，而 COCO 类别中没有 pig。",
                f"因此输出的是「疑似猪只的动物」粗类别（本次命中：{sorted(set(warned)) or '无'}），",
                "可能把猪统计为 cow/sheep/horse，也可能漏检。要获得真正的猪只检测，"
                "请提供猪只检测模型（ONNX）并改用 OnnxBackend。",
            ],
            image_size=(w, h),
        )

    def describe(self) -> dict:
        return {"name": self.name, "can_detect_pig": False,
                "note": "COCO 无 pig 类，输出为近邻动物粗类别",
                "neighbors": sorted(self.neighbors)}


class OnnxBackend(BaseBackend):
    """用户自备 ONNX 猪只检测模型（推荐，真正的猪检测）。

    支持两种常见输出格式，通过 config 里的 output_format 指定：
        - "yolo"   : YOLOv5/v8 导出格式，输出 shape (1, N, 5+num_classes)
                     或 (1, 5+num_classes, N)
        - "coco"   : torchvision 风格，多输出 (boxes, labels, scores)

    模型类别名通过 labels 列表给出，其中应包含 "pig" 或 "animal"。
    """

    name = "onnx-custom"

    def __init__(self, model_path, labels=None, input_size=(640, 640),
                 min_score=0.5, output_format="yolo", torch_home=None):
        import onnxruntime as ort
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"ONNX 模型不存在: {model_path}")
        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.input_size = input_size
        self.labels = labels or ["pig"]
        self.min_score = min_score
        self.output_format = output_format
        self.model_path = model_path
        if not any(l.lower() in ("pig", "animal", "swine", "hog") for l in self.labels):
            raise ValueError("labels 中应包含 pig / animal / swine / hog 之一")

    name_ = "onnx-custom"

    def detect(self, image) -> DetectionResult:
        import numpy as np
        from PIL import Image

        w, h = image.size
        iw, ih = self.input_size
        resized = image.convert("RGB").resize((iw, ih), Image.BILINEAR)
        arr = np.asarray(resized, dtype=np.float32) / 255.0
        arr = np.transpose(arr, (2, 0, 1))[None, ...]

        outs = self.session.run(None, {self.input_name: arr})
        dets = self._parse(outs, w, h)
        pig_like = [d for d in dets if d.label in ("pig", "animal", "swine", "hog")]
        return DetectionResult(
            detections=dets, backend=f"{self.name}:{os.path.basename(self.model_path)}",
            approximate=not self.can_detect_pig,
            warnings=[] if self.can_detect_pig else ["模型 labels 中未见 pig 类别"],
            image_size=(w, h),
        )

    def _parse(self, outs, w, h):
        import numpy as np
        dets = []
        raw = outs[0]
        # 归一化到 (N, C)
        if raw.ndim == 3:
            if raw.shape[1] < raw.shape[2]:
                raw = np.transpose(raw, (0, 2, 1))
            raw = raw[0]
        sx, sy = w / self.input_size[0], h / self.input_size[1]
        for row in raw:
            if len(row) < 6:
                continue
            cx, cy, bw, bh = row[:4]
            obj = float(row[4])
            cls_scores = row[5:]
            ci = int(np.argmax(cls_scores))
            score = obj * float(cls_scores[ci])
            if score < self.min_score:
                continue
            x1 = (cx - bw / 2) * sx
            y1 = (cy - bh / 2) * sy
            x2 = (cx + bw / 2) * sx
            y2 = (cy + bh / 2) * sy
            label = self.labels[ci] if ci < len(self.labels) else f"class{ci}"
            dets.append(Detection((x1, y1, x2, y2), label, score))
        return dets

    def describe(self) -> dict:
        return {"name": self.name, "can_detect_pig": True,
                "model": os.path.basename(self.model_path),
                "labels": self.labels, "input_size": list(self.input_size)}


class YoloBackend(BaseBackend):
    """Ultralytics YOLO 后端：加载训练好的猪只检测模型（.pt）。

    这是本项目推荐的生产后端——用 PigBench 数据集自训的单类（pig）检测器，
    或任何自备的 YOLOv8/v11 猪只检测权重。

    相比 TorchvisionBackend 的关键差别：**它真的认识「猪」**，
    因此 can_detect_pig = True，报告中不再出现「近似检测」警示。
    """

    name = "ultralytics-yolo"

    def __init__(self, model_path, min_score=0.25, imgsz=640, device="cpu"):
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"YOLO 模型不存在: {model_path}")
        from ultralytics import YOLO
        self.model = YOLO(model_path)
        self.model_path = model_path
        self.min_score = min_score
        self.imgsz = imgsz
        self.device = device

        # 判定该模型是否为「猪」检测器：类别数少且类名含 pig 类关键词
        names = self.model.names
        vals = list(names.values()) if isinstance(names, dict) else list(names)
        self.class_names = [str(v) for v in vals]
        pig_like = any(("pig" in v.lower() or "swine" in v.lower() or "hog" in v.lower())
                       for v in self.class_names)
        # 单类模型且类名不含 pig（例如名为 class0）也视为可用，但如实标注
        self.can_detect_pig = pig_like
        self._single_class = len(self.class_names) == 1
        self.name = f"ultralytics-yolo:{os.path.basename(model_path)}"

    def detect(self, image) -> DetectionResult:
        import numpy as np
        w, h = image.size
        res = self.model.predict(np.asarray(image.convert("RGB")), conf=self.min_score,
                                imgsz=self.imgsz, device=self.device, verbose=False)[0]
        dets = []
        if res.boxes is not None and len(res.boxes) > 0:
            xyxy = res.boxes.xyxy.cpu().numpy()
            confs = res.boxes.conf.cpu().numpy()
            clss = res.boxes.cls.cpu().numpy().astype(int)
            for (x1, y1, x2, y2), c, k in zip(xyxy, confs, clss):
                label = self.class_names[k] if k < len(self.class_names) else f"class{k}"
                # 单类模型统一归一为 animal，便于行为层按几何特征处理
                if self._single_class:
                    label = "animal"
                dets.append(Detection((float(x1), float(y1), float(x2), float(y2)),
                                      label, float(c)))
        warns = []
        if not self.can_detect_pig:
            warns.append(
                f"该模型的类别名（{self.class_names[:6]}）中未见 pig/swine/hog。"
                "若它其实是猪检测器（单类但类名不规范），请把 models/labels.json 的 "
                "labels 写为 [\"pig\"] 以消除本提示。")
        return DetectionResult(detections=dets, backend=self.name,
                               approximate=not self.can_detect_pig,
                               warnings=warns, image_size=(w, h))

    def describe(self) -> dict:
        return {"name": self.name, "can_detect_pig": self.can_detect_pig,
                "model": os.path.basename(self.model_path),
                "classes": self.class_names[:10], "n_classes": len(self.class_names),
                "single_class": self._single_class, "imgsz": self.imgsz}


class MockBackend(BaseBackend):
    """无模型时的占位后端：按配置生成固定检测框，用于跑通流程与界面演示。

    绝不用于真实识别。会在结果中明确标注为模拟数据。
    """

    name = "mock"
    can_detect_pig = False

    def __init__(self, scene=None, image_size=(640, 480)):
        self.scene = scene or []
        self.image_size = image_size

    def detect(self, image) -> DetectionResult:
        w, h = image.size if hasattr(image, "size") else self.image_size
        dets = [Detection(tuple(b), lab, sc) for b, lab, sc in
                [(tuple(x[:4]), x[4], x[5]) for x in self.scene]]
        return DetectionResult(
            detections=dets, backend=self.name, approximate=True,
            warnings=["当前使用模拟后端，检测框为预设值，不代表真实识别结果。"],
            image_size=(w, h),
        )

    def describe(self) -> dict:
        return {"name": self.name, "can_detect_pig": False, "note": "占位后端，仅用于流程演示"}


# ============================================================
# 工厂
# ============================================================

def list_available_models(exts=(".onnx", ".pt")):
    """列出 models/ 目录下可用的检测模型。"""
    if not os.path.isdir(MODELS_DIR):
        return []
    return sorted(f for f in os.listdir(MODELS_DIR)
                  if f.lower().endswith(tuple(exts))
                  and "coco" not in f.lower())          # 排除 COCO 通用权重（不认识猪）


def build_backend(kind="auto", onnx_model=None, labels=None,
                  output_format="yolo", min_score=0.5):
    """按优先级构建检测后端。

    auto 的优先级：
        1) models/ 下有自训 YOLO 权重（.pt，非 coco）-> YoloBackend（真猪检测）
        2) models/ 下有 ONNX 模型                 -> OnnxBackend（真猪检测）
        3) 退化到 TorchvisionBackend（COCO 预训练，不认识猪，结果仅供参考）
    """
    if kind == "mock":
        return MockBackend()

    if kind in ("auto", "yolo"):
        pt = [m for m in list_available_models((".pt",))
              if "coco" not in m.lower()]
        if pt:
            return YoloBackend(os.path.join(MODELS_DIR, pt[0]), min_score=min_score)
        if kind == "yolo":
            raise FileNotFoundError(
                f"未找到 YOLO 权重。请把训练好的猪只检测模型（.pt）放入 {MODELS_DIR}\\")

    if kind == "onnx" or (kind == "auto" and (onnx_model or list_available_models((".onnx",)))):
        path = onnx_model
        if not path:
            cands = list_available_models((".onnx",))
            path = os.path.join(MODELS_DIR, cands[0]) if cands else None
        if path:
            if labels is None:
                cfg = os.path.join(MODELS_DIR, "labels.json")
                if os.path.isfile(cfg):
                    with open(cfg, encoding="utf-8") as fh:
                        labels = json.load(fh).get("labels")
            return OnnxBackend(path, labels=labels, output_format=output_format,
                               min_score=min_score)
        if kind == "onnx":
            raise FileNotFoundError(
                f"未找到 ONNX 模型。请把猪只检测模型放入 {MODELS_DIR}\\ 目录"
                "（并在同目录放 labels.json 声明类别名）")

    return TorchvisionBackend(min_score=min_score)


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print("可用 ONNX 模型:", list_available_models() or "（无）")
    print()
    b = build_backend()
    info = b.describe()
    print("当前后端:", json.dumps(info, ensure_ascii=False, indent=1))
    if not info.get("can_detect_pig"):
        print("\n⚠ 当前后端不认识「猪」。要获得真正的猪只检测，请提供 ONNX 模型到 models\\ 目录。")
