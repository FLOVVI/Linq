"""Перевод точек пола из пикселей кадра в метры карты (и обратно)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np


def apply_h(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    pts = np.asarray(pts, np.float64).reshape(-1, 2)
    p = np.c_[pts, np.ones(len(pts))] @ H.T
    w = p[:, 2:3]
    w = np.where(np.abs(w) < 1e-12, 1e-12, w)
    return p[:, :2] / w


def clip_below(pts, v: float) -> np.ndarray:
    """Часть многоугольника кадра ниже строки v (отсечение Сазерленда — Ходжмена по одной полуплоскости)."""
    pts = np.asarray(pts, np.float64).reshape(-1, 2)
    out = []
    for i in range(len(pts)):
        a, b = pts[i - 1], pts[i]
        if (a[1] >= v) != (b[1] >= v):
            out.append(a + (v - a[1]) / (b[1] - a[1]) * (b - a))
        if b[1] >= v:
            out.append(b)
    return np.asarray(out, np.float64).reshape(-1, 2)


def rigid2d(theta: float, tx: float, ty: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s, tx], [s, c, ty], [0, 0, 1]], np.float64)


@dataclass
class CameraModel:
    """Пинхол-камера над плоскостью пола: фокус f (px), наклон вниз tilt, крен roll (рад), высота h (м)."""

    f: float
    tilt: float
    roll: float
    height: float
    cx: float
    cy: float

    def rotation(self) -> np.ndarray:
        t = self.tilt
        # строки — оси камеры (x вправо, y вниз, z вперёд) в мировой системе (X вправо, Y вперёд, Z вверх)
        R = np.array([[1, 0, 0], [0, -math.sin(t), -math.cos(t)], [0, math.cos(t), -math.sin(t)]], np.float64)
        c, s = math.cos(self.roll), math.sin(self.roll)
        Rr = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], np.float64)
        return Rr @ R

    def K(self) -> np.ndarray:
        return np.array([[self.f, 0, self.cx], [0, self.f, self.cy], [0, 0, 1]], np.float64)

    def ground_to_image(self) -> np.ndarray:
        R = self.rotation()
        return self.K() @ np.column_stack([R[:, 0], R[:, 1], -self.height * R[:, 2]])

    def project(self, P: np.ndarray) -> np.ndarray:
        """Мировые точки (N,3) -> пиксели (N,2)."""
        R = self.rotation()
        Pc = (np.asarray(P, np.float64) - np.array([0, 0, self.height])) @ R.T
        z = np.where(Pc[:, 2] < 1e-6, 1e-6, Pc[:, 2])
        return np.c_[self.cx + self.f * Pc[:, 0] / z, self.cy + self.f * Pc[:, 1] / z]

    def horizon_v(self, u: float | None = None) -> float:
        """Строка горизонта (точки выше неё на пол не проецируются)."""
        return self.cy - self.f * math.tan(self.tilt)

    def to_dict(self) -> dict:
        return {"f": self.f, "tilt_deg": math.degrees(self.tilt), "roll_deg": math.degrees(self.roll),
                "height_m": self.height, "cx": self.cx, "cy": self.cy}

    @staticmethod
    def from_dict(d: dict) -> "CameraModel":
        return CameraModel(d["f"], math.radians(d["tilt_deg"]), math.radians(d.get("roll_deg", 0.0)),
                           d["height_m"], d["cx"], d["cy"])


class GroundMapping:
    """Пиксели кадра <-> метры карты для одной камеры.

    H — гомография кадр->карта. Если известна модель камеры, дополнительно знаем горизонт
    и можем отсечь точки, лежащие слишком далеко (там гомография неустойчива).
    """

    def __init__(self, H: np.ndarray, camera: CameraModel | None = None, max_range_m: float = 40.0,
                 frame_hw: tuple[int, int] | None = None):
        self.H = np.asarray(H, np.float64)
        self.Hinv = np.linalg.inv(self.H)
        self.camera = camera
        self.max_range_m = max_range_m
        self.frame_hw = frame_hw

    @staticmethod
    def from_points(image_points, map_points, **kw) -> "GroundMapping":
        src = np.asarray(image_points, np.float64)
        dst = np.asarray(map_points, np.float64)
        if len(src) < 4:
            raise ValueError("Для калибровки нужно минимум 4 пары точек (кадр <-> карта)")
        H, _ = cv2.findHomography(src, dst, cv2.RANSAC if len(src) > 4 else 0, 0.5)
        if H is None:
            raise ValueError("Не удалось вычислить гомографию: точки вырождены")
        return GroundMapping(H, **kw)

    @staticmethod
    def from_camera(cam: CameraModel, placement: np.ndarray | None = None, **kw) -> "GroundMapping":
        """placement — жёсткое преобразование 3x3 из системы камеры (м) в систему карты (м)."""
        G = np.linalg.inv(cam.ground_to_image())  # кадр -> пол в системе камеры
        P = np.eye(3) if placement is None else placement
        return GroundMapping(P @ G, camera=cam, **kw)

    def to_map(self, pts) -> np.ndarray:
        return apply_h(self.H, pts)

    def to_image(self, pts) -> np.ndarray:
        return apply_h(self.Hinv, pts)

    def valid_image_points(self, pts) -> np.ndarray:
        """True для пикселей, которые лежат на полу ниже горизонта (с запасом)."""
        pts = np.asarray(pts, np.float64).reshape(-1, 2)
        p = np.c_[pts, np.ones(len(pts))] @ self.H.T
        ok = p[:, 2] > 1e-9 if np.median(p[:, 2]) > 0 else p[:, 2] < -1e-9
        if self.camera is not None:
            ok &= pts[:, 1] > self.camera.horizon_v() + 0.02 * (self.frame_hw[0] if self.frame_hw else 1000)
        return ok

    def floor_top(self, frame_hw: tuple[int, int], max_range_m: float | None = None) -> float:
        """Верхняя строка кадра, до которой пол ещё берём: горизонт с запасом или дальность max_range_m."""
        h = frame_hw[0]
        if self.camera is None:
            return 0.0
        cam = self.camera
        top = max(0.0, cam.horizon_v() + 0.03 * h)
        # строка кадра, соответствующая дальности rng по оси камеры
        ang = math.atan2(cam.height, max_range_m or self.max_range_m)
        v_far = cam.cy + cam.f * math.tan(ang - cam.tilt)
        return max(top, min(v_far, h - 2))

    def footprint(self, frame_hw: tuple[int, int], max_range_m: float | None = None, n: int = 24) -> np.ndarray:
        """Полигон (метры карты), который камера видит на полу: нижняя часть кадра до горизонта/дальности."""
        h, w = frame_hw
        top = self.floor_top(frame_hw, max_range_m)
        xs = np.linspace(0, w - 1, n)
        border = np.r_[np.c_[xs, np.full(n, h - 1)],  # низ слева направо
                       np.c_[np.full(n, w - 1), np.linspace(h - 1, top, n)],
                       np.c_[xs[::-1], np.full(n, top)],
                       np.c_[np.zeros(n), np.linspace(top, h - 1, n)]]
        ok = self.valid_image_points(border)
        return self.to_map(border[ok])

    def to_dict(self) -> dict:
        d = {"homography": self.H.round(8).tolist()}
        if self.camera is not None:
            d["camera"] = self.camera.to_dict()
        return d
