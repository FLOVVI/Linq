"""YOLOv8 (detect/pose) с «сырыми» выходами головы сети.

Для LinQ TPU сеть обрезается перед декодированием (DFL-softmax, якоря, sigmoid, NMS):
на ускоритель уходят только свёртки, а декодирование выполняется здесь на CPU. Так же
поступают с поддерживаемыми LinQ моделями yolov8n_pose/yolov8m_seg (см. tpu_framework.pdf, гл. 6).
Выходы на каждый уровень пирамиды (stride 8/16/32):
    box_pN  — (1, 4*reg_max, H, W) логиты распределения расстояний до сторон рамки
    cls_pN  — (1, nc, H, W) логиты классов
    kpt_pN  — (1, K*3, H, W) ключевые точки (только pose)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from .backends import Backend, make_backend


@dataclass
class Detections:
    boxes: np.ndarray  # (N, 4) xyxy, пиксели исходного кадра
    scores: np.ndarray  # (N,)
    classes: np.ndarray  # (N,) int
    names: list[str]
    kpts: np.ndarray | None = None  # (N, K, 3): x, y, видимость

    def __len__(self) -> int:
        return len(self.scores)

    def select(self, mask: np.ndarray) -> "Detections":
        return Detections(self.boxes[mask], self.scores[mask], self.classes[mask], self.names,
                          None if self.kpts is None else self.kpts[mask])

    def of(self, *names: str) -> "Detections":
        ids = [i for i, n in enumerate(self.names) if n in names]
        return self.select(np.isin(self.classes, ids))

    @staticmethod
    def empty(names: list[str], k: int | None = None) -> "Detections":
        return Detections(np.zeros((0, 4), np.float32), np.zeros(0, np.float32), np.zeros(0, int), names,
                          None if k is None else np.zeros((0, k, 3), np.float32))


@dataclass
class Letterbox:
    ratio: float
    pad: tuple[float, float]  # (dx, dy)
    src_hw: tuple[int, int]


def letterbox(img: np.ndarray, out_hw: tuple[int, int], color: int = 114) -> tuple[np.ndarray, Letterbox]:
    h, w = img.shape[:2]
    oh, ow = out_hw
    r = min(oh / h, ow / w)
    nw, nh = int(round(w * r)), int(round(h * r))
    if (nw, nh) != (w, h):
        img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    dx, dy = (ow - nw) / 2, (oh - nh) / 2
    top, left = int(round(dy - 0.1)), int(round(dx - 0.1))
    out = cv2.copyMakeBorder(img, top, oh - nh - top, left, ow - nw - left, cv2.BORDER_CONSTANT,
                             value=(color, color, color))
    return out, Letterbox(r, (left, top), (h, w))


def preprocess(img_bgr: np.ndarray, out_hw: tuple[int, int]) -> tuple[np.ndarray, Letterbox]:
    lb_img, lb = letterbox(img_bgr, out_hw)
    x = cv2.cvtColor(lb_img, cv2.COLOR_BGR2RGB).astype(np.float32) * (1.0 / 255.0)
    return np.ascontiguousarray(x.transpose(2, 0, 1)[None]), lb


def _to_cn(a: np.ndarray, c: int, h: int, w: int) -> np.ndarray:
    """Приводит выход уровня к (C, H*W) независимо от раскладки (NCHW от ONNX / NHWC от TF-конвертера)."""
    a = np.asarray(a, dtype=np.float32)
    if a.ndim == 4:
        a = a[0]
    if a.shape == (c, h, w):
        return a.reshape(c, h * w)
    if a.shape == (h, w, c):
        return a.transpose(2, 0, 1).reshape(c, h * w)
    if a.ndim == 2 and a.shape == (c, h * w):
        return a
    if a.ndim == 2 and a.shape == (h * w, c):
        return a.T
    if a.size == c * h * w:
        return a.reshape(c, h * w)
    raise ValueError(f"Неожиданная форма выхода {a.shape}, ожидалось C={c}, H={h}, W={w}")


def nms(boxes: np.ndarray, scores: np.ndarray, iou_thr: float, max_det: int = 300) -> np.ndarray:
    order = scores.argsort()[::-1]
    keep = []
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    while order.size and len(keep) < max_det:
        i = order[0]
        keep.append(i)
        rest = order[1:]
        xx1 = np.maximum(boxes[i, 0], boxes[rest, 0])
        yy1 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[rest, 2])
        yy2 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        iou = inter / (areas[i] + areas[rest] - inter + 1e-9)
        order = rest[iou <= iou_thr]
    return np.asarray(keep, dtype=int)


def decode(outputs: dict[str, np.ndarray], spec: dict[str, Any], conf: float, iou: float,
           class_conf: dict[str, float] | None = None, max_det: int = 300) -> tuple[np.ndarray, ...]:
    """Декодирует сырые выходы в рамки в координатах входа сети (до снятия letterbox)."""
    ih, iw = spec["input"]["shape"][2:]
    names = spec["classes"]
    nc = len(names)
    reg = spec.get("reg_max", 16)
    kshape = spec.get("kpt_shape")
    thr = np.full(nc, conf, np.float32)
    for n, v in (class_conf or {}).items():
        if n in names:
            thr[names.index(n)] = v
    min_thr = float(thr.min())
    logit_thr = np.log(min_thr / (1 - min_thr))
    bins = np.arange(reg, dtype=np.float32)

    all_b, all_s, all_c, all_k = [], [], [], []
    for lvl in spec["levels"]:
        s = lvl["stride"]
        h, w = ih // s, iw // s
        cls = _to_cn(outputs[lvl["cls"]], nc, h, w)
        idx = np.nonzero(cls.max(0) > logit_thr)[0]
        if idx.size == 0:
            continue
        sc = 1.0 / (1.0 + np.exp(-cls[:, idx]))  # (nc, k)
        ci, ai = np.nonzero(sc > thr[:, None])  # мульти-метка: класс x якорь
        if ai.size == 0:
            continue
        box = _to_cn(outputs[lvl["box"]], 4 * reg, h, w)[:, idx].reshape(4, reg, -1)
        if reg > 1:  # DFL: матожидание распределения расстояний
            box = np.exp(box - box.max(1, keepdims=True))
            dist = (box * bins[None, :, None]).sum(1) / box.sum(1)  # (4, k)
        else:  # YOLO26 и др. без DFL: расстояния до сторон напрямую
            dist = box[:, 0, :]
        gx = (idx % w).astype(np.float32) + 0.5
        gy = (idx // w).astype(np.float32) + 0.5
        xyxy = np.stack([(gx - dist[0]) * s, (gy - dist[1]) * s, (gx + dist[2]) * s, (gy + dist[3]) * s], 1)
        all_b.append(xyxy[ai])
        all_s.append(sc[ci, ai])
        all_c.append(ci)
        if kshape:
            K, D = kshape
            kr = _to_cn(outputs[lvl["kpt"]], K * D, h, w)[:, idx].reshape(K, D, -1)
            kx = (kr[:, 0] * 2.0 + (gx - 0.5)) * s
            ky = (kr[:, 1] * 2.0 + (gy - 0.5)) * s
            kv = 1.0 / (1.0 + np.exp(-kr[:, 2])) if D == 3 else np.ones_like(kx)
            all_k.append(np.stack([kx, ky, kv], -1).transpose(1, 0, 2)[ai])  # (k, K, 3)

    if not all_b:
        k = kshape[0] if kshape else None
        return (np.zeros((0, 4), np.float32), np.zeros(0, np.float32), np.zeros(0, int),
                None if k is None else np.zeros((0, k, 3), np.float32))
    b = np.concatenate(all_b).astype(np.float32)
    sc = np.concatenate(all_s).astype(np.float32)
    c = np.concatenate(all_c).astype(int)
    kp = np.concatenate(all_k).astype(np.float32) if all_k else None
    keep = nms(b + (c[:, None] * 4096.0), sc, iou, max_det)  # NMS по классам
    return b[keep], sc[keep], c[keep], (kp[keep] if kp is not None else None)


def _tpu_stats(backend: Backend) -> dict[str, Any]:
    """Облако LinQ: чистое время на плате (по отчёту воркера) отдельно от круговой задержки с сетью."""
    tl = getattr(backend, "tpu_latency", None)
    return {f"tpu_{k}": v for k, v in tl.summary().items() if k != "calls"} if tl else {}


class YoloModel:
    """Модель YOLOv8 (detect/pose), работающая через любой бэкенд."""

    def __init__(self, spec_path: str, backend: str = "onnx", conf: float = 0.35, iou: float = 0.5,
                 class_conf: dict[str, float] | None = None, **backend_opts):
        with open(spec_path, encoding="utf-8") as f:
            self.spec = json.load(f)
        self.name = self.spec["name"]
        self.task = self.spec["task"]
        self.names: list[str] = self.spec["classes"]
        self.input_name = self.spec["input"]["name"]
        self.in_hw = tuple(self.spec["input"]["shape"][2:])
        self.conf, self.iou, self.class_conf = conf, iou, class_conf
        self.backend: Backend = make_backend(backend, self.spec, os.path.dirname(spec_path), **backend_opts)

    def __call__(self, img_bgr: np.ndarray) -> Detections:
        x, lb = preprocess(img_bgr, self.in_hw)
        out = self.backend.run({self.input_name: x})
        b, s, c, k = decode(out, self.spec, self.conf, self.iou, self.class_conf)
        dx, dy = lb.pad
        h, w = lb.src_hw
        if len(b):
            b[:, [0, 2]] = np.clip((b[:, [0, 2]] - dx) / lb.ratio, 0, w - 1)
            b[:, [1, 3]] = np.clip((b[:, [1, 3]] - dy) / lb.ratio, 0, h - 1)
        if k is not None and len(k):
            k[..., 0] = (k[..., 0] - dx) / lb.ratio
            k[..., 1] = (k[..., 1] - dy) / lb.ratio
        return Detections(b, s, c, self.names, k)

    def stats(self) -> dict[str, Any]:
        return {"model": self.name, "backend": self.backend.name, "input": list(self.in_hw),
                **self.backend.latency.summary(), **_tpu_stats(self.backend)}


class ClassifierModel:
    """Классификатор вырезок (например, «каска / без каски»); вход фиксирован, батч 1 (как на TPU)."""

    def __init__(self, spec_path: str, backend: str = "onnx", **backend_opts):
        with open(spec_path, encoding="utf-8") as f:
            self.spec = json.load(f)
        self.name = self.spec["name"]
        self.names: list[str] = self.spec["classes"]
        self.input_name = self.spec["input"]["name"]
        self.size = int(self.spec["input"]["shape"][2])
        self.out_name = self.spec.get("outputs", ["probs"])[0]
        self.logits = self.spec.get("output_kind") == "logits"  # softmax считается здесь, а не на ускорителе
        self.backend: Backend = make_backend(backend, self.spec, os.path.dirname(spec_path), **backend_opts)

    def __call__(self, crops: list[np.ndarray]) -> np.ndarray:
        """crops: BGR-вырезки любого размера -> (N, C) вероятности."""
        out = []
        for c in crops:
            x = cv2.cvtColor(cv2.resize(c, (self.size, self.size), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
            x = np.ascontiguousarray((x.astype(np.float32) / 255.0).transpose(2, 0, 1)[None])
            r = self.backend.run({self.input_name: x})
            p = np.asarray(r.get(self.out_name, next(iter(r.values()))), np.float32).reshape(-1)
            if self.logits or p.min() < 0 or abs(p.sum() - 1) > 1e-2:  # логиты -> вероятности
                p = np.exp(p - p.max())
                p = p / p.sum()
            out.append(p)
        return np.asarray(out, np.float32).reshape(len(crops), len(self.names))

    def stats(self) -> dict[str, Any]:
        return {"model": self.name, "backend": self.backend.name, "input": [self.size, self.size],
                **self.backend.latency.summary(), **_tpu_stats(self.backend)}
