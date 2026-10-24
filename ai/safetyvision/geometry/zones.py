"""Зоны: статические (полигон на карте в метрах или в пикселях кадра) и динамические (радиус вокруг техники)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import ZoneConfig


def points_in_polygon(pts: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Векторизованный ray casting: (N,2) точек, (M,2) вершин -> (N,) bool."""
    pts = np.asarray(pts, np.float64).reshape(-1, 2)
    poly = np.asarray(poly, np.float64).reshape(-1, 2)
    x, y = pts[:, 0:1], pts[:, 1:2]
    x1, y1 = poly[:, 0], poly[:, 1]
    x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
    cond = (y1 > y) != (y2 > y)
    xint = (x2 - x1) * (y - y1) / np.where(y2 - y1 == 0, 1e-12, y2 - y1) + x1
    return (np.sum(cond & (x < xint), axis=1) % 2) == 1


def distance_to_segment(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    ab = b - a
    t = float(np.clip(np.dot(p - a, ab) / (np.dot(ab, ab) + 1e-12), 0, 1))
    return float(np.linalg.norm(p - (a + t * ab)))


@dataclass
class DynamicAnchor:
    """Движущийся объект, вокруг которого действует динамическая зона."""

    kind: str  # forklift / vehicle
    map_xy: np.ndarray | None
    foot_px: np.ndarray
    px_per_m: float  # грубая оценка масштаба в окрестности объекта (если нет калибровки)
    box: np.ndarray | None = None  # рамка объекта в кадре: расстояние считаем до её нижнего края


class ZoneIndex:
    def __init__(self, zones: list[ZoneConfig]):
        self.set(zones)

    def set(self, zones: list[ZoneConfig]) -> None:
        self.zones = list(zones)
        self._poly = {z.id: np.asarray(z.polygon, np.float64) for z in self.zones if z.polygon}
        self._poly_px = {z.id: np.asarray(z.polygon_px, np.float64) for z in self.zones if z.polygon_px}

    def at(self, cam_id: str, foot_px, map_xy, ts: float,
           anchors: list[DynamicAnchor] | None = None, person_px_per_m: float | None = None) -> list[ZoneConfig]:
        """Зоны, в которых находится точка (стопы человека) в момент ts."""
        out = []
        for z in self.zones:
            if not z.active_at(ts):
                continue
            if z.kind == "dynamic":
                for a in anchors or []:
                    if z.attach_to and z.attach_to not in (a.kind, "any") and not (
                            z.attach_to == "vehicle" and a.kind == "forklift"):
                        continue
                    if map_xy is not None and a.map_xy is not None:
                        d = float(np.linalg.norm(np.asarray(map_xy) - a.map_xy))
                    else:
                        # без калибровки: пиксели до нижнего края рамки техники, масштаб — по росту человека
                        # (у техники высота рамки зависит от поднятой мачты и груза)
                        f = np.asarray(foot_px, float)
                        if a.box is not None:
                            near = np.array([np.clip(f[0], a.box[0], a.box[2]), a.box[3]])
                        else:
                            near = a.foot_px
                        d = float(np.linalg.norm(f - near)) / max(person_px_per_m or a.px_per_m, 1e-6)
                    if d <= z.radius_m:
                        out.append(z)
                        break
                continue
            if z.id in self._poly_px and z.camera == cam_id:
                if points_in_polygon(np.asarray(foot_px)[None], self._poly_px[z.id])[0]:
                    out.append(z)
            elif z.id in self._poly and map_xy is not None and (z.camera in (None, cam_id)):
                if points_in_polygon(np.asarray(map_xy)[None], self._poly[z.id])[0]:
                    out.append(z)
        return out
