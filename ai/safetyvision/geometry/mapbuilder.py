"""Миникарта помещения: вид сверху, собранный из кадров камер, зоны покрытия и слепые зоны."""

from __future__ import annotations

import cv2
import numpy as np

from ..config import MapConfig
from .homography import GroundMapping


class MapCanvas:
    """Метры карты <-> пиксели изображения миникарты."""

    def __init__(self, cfg: MapConfig):
        self.cfg = cfg
        self.s = float(cfg.px_per_m)
        self.ox, self.oy = cfg.origin_m
        self.W = int(round(cfg.size_m[0] * self.s))
        self.H = int(round(cfg.size_m[1] * self.s))

    @property
    def S(self) -> np.ndarray:
        return np.array([[self.s, 0, -self.ox * self.s], [0, self.s, -self.oy * self.s], [0, 0, 1]], np.float64)

    def to_px(self, xy) -> np.ndarray:
        xy = np.asarray(xy, np.float64).reshape(-1, 2)
        return np.c_[(xy[:, 0] - self.ox) * self.s, (xy[:, 1] - self.oy) * self.s]

    def to_m(self, px) -> np.ndarray:
        px = np.asarray(px, np.float64).reshape(-1, 2)
        return np.c_[px[:, 0] / self.s + self.ox, px[:, 1] / self.s + self.oy]

    @staticmethod
    def fit_to(polygons: list[np.ndarray], px_per_m: float = 25.0, margin_m: float = 1.0) -> MapConfig:
        """Подбирает границы карты так, чтобы в неё попали все зоны обзора камер."""
        pts = np.concatenate([p for p in polygons if len(p)])
        lo, hi = pts.min(0) - margin_m, pts.max(0) + margin_m
        return MapConfig(size_m=(float(hi[0] - lo[0]), float(hi[1] - lo[1])), px_per_m=px_per_m,
                         origin_m=(float(lo[0]), float(lo[1])))


class MapBuilder:
    def __init__(self, canvas: MapCanvas, max_range_m: float = 25.0):
        self.canvas = canvas
        self.max_range_m = max_range_m
        self.background: np.ndarray | None = None
        self.coverage: dict[str, np.ndarray] = {}  # cam -> маска покрытия (uint8)
        self.footprints: dict[str, np.ndarray] = {}  # cam -> полигон (метры)

    def build(self, frames: dict[str, np.ndarray], mappings: dict[str, GroundMapping],
              room: np.ndarray | None = None) -> np.ndarray:
        c = self.canvas
        acc = np.zeros((c.H, c.W, 3), np.float32)
        wsum = np.zeros((c.H, c.W), np.float32)
        for cam, frame in frames.items():
            gm = mappings.get(cam)
            if gm is None or frame is None:
                continue
            h, w = frame.shape[:2]
            fp = gm.footprint((h, w), self.max_range_m)
            if len(fp) < 3:
                continue
            self.footprints[cam] = fp
            M = c.S @ gm.H
            warped = cv2.warpPerspective(frame, M, (c.W, c.H), flags=cv2.INTER_LINEAR,
                                         borderMode=cv2.BORDER_CONSTANT)
            mask = np.zeros((c.H, c.W), np.uint8)
            cv2.fillPoly(mask, [np.round(c.to_px(fp)).astype(np.int32)], 255)
            self.coverage[cam] = mask
            # вес: ближе к камере (ниже в кадре) — чётче, поэтому больший вес
            dist = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, 3)
            wgt = (mask > 0).astype(np.float32) * (0.2 + np.minimum(dist / (2 * c.s), 1.0))
            acc += warped.astype(np.float32) * wgt[..., None]
            wsum += wgt
        bg = np.full((c.H, c.W, 3), 236, np.uint8)
        nz = wsum > 0
        bg[nz] = (acc[nz] / wsum[nz, None]).clip(0, 255).astype(np.uint8)
        # приглушаем мозаику, чтобы поверх неё читались зоны и люди
        bg[nz] = cv2.addWeighted(bg, 0.75, np.full_like(bg, 255), 0.25, 0)[nz]
        self.background = bg
        return bg

    def blind_zones(self, room: np.ndarray | None = None, min_area_m2: float = 1.0) -> list[np.ndarray]:
        """Слепые зоны: части помещения (или всей карты), которые не видит ни одна камера."""
        c = self.canvas
        area = np.zeros((c.H, c.W), np.uint8)
        if room is not None and len(room) >= 3:
            cv2.fillPoly(area, [np.round(c.to_px(room)).astype(np.int32)], 255)
        else:
            area[:] = 255
        covered = np.zeros_like(area)
        for m in self.coverage.values():
            covered |= m
        blind = cv2.bitwise_and(area, cv2.bitwise_not(covered))
        cnts, _ = cv2.findContours(blind, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out = []
        for cn in cnts:
            if cv2.contourArea(cn) / (c.s * c.s) >= min_area_m2:
                approx = cv2.approxPolyDP(cn, 0.15 * c.s, True)[:, 0, :]
                out.append(c.to_m(approx))
        return out

    def coverage_ratio(self, room: np.ndarray | None = None) -> float:
        c = self.canvas
        area = np.zeros((c.H, c.W), np.uint8)
        if room is not None and len(room) >= 3:
            cv2.fillPoly(area, [np.round(c.to_px(room)).astype(np.int32)], 255)
        else:
            area[:] = 255
        covered = np.zeros_like(area)
        for m in self.coverage.values():
            covered |= m
        return float(np.count_nonzero(covered & area)) / max(np.count_nonzero(area), 1)
