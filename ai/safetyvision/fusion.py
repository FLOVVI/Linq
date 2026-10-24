"""Глобальные треки людей на карте по нескольким камерам.

Человек, которого видят две камеры, получает один глобальный ID: локальные треки разных
камер связываются, если их положения на карте (метры) совпадают. Благодаря этому
нарушение одного человека, видимое с нескольких камер, — это одно событие, а СИЗ можно
подтвердить с той камеры, откуда лучше видно.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class GlobalTrack:
    gid: int
    xy: np.ndarray
    t: float
    members: dict[str, tuple[int, np.ndarray, float]] = field(default_factory=dict)  # cam -> (local, xy, t)
    vel: np.ndarray = field(default_factory=lambda: np.zeros(2))
    close_count: dict[int, int] = field(default_factory=dict)


class GlobalTracker:
    def __init__(self, gate_m: float = 1.2, ttl_s: float = 3.0, merge_after: int = 4):
        self.gate, self.ttl, self.merge_after = gate_m, ttl_s, merge_after
        self.tracks: dict[int, GlobalTrack] = {}
        self.links: dict[tuple[str, int], int] = {}
        self._next = 1

    def update(self, cam: str, t: float, local: list[tuple[int, np.ndarray | None]]) -> dict[int, str]:
        """local: [(track_id, map_xy|None)] — видимые треки камеры. Возвращает {track_id: subject_key}."""
        out: dict[int, str] = {}
        seen = set()
        for tid, xy in local:
            if xy is None:
                out[tid] = f"{cam}:p{tid}"
                continue
            xy = np.asarray(xy, np.float64)
            key = (cam, tid)
            gid = self.links.get(key)
            if gid is None or gid not in self.tracks:
                gid = self._match(cam, t, xy)
                self.links[key] = gid
            g = self.tracks[gid]
            g.members[cam] = (tid, xy, t)
            seen.add(gid)
            out[tid] = f"g{gid}"
        for gid in seen:
            self._refresh(self.tracks[gid], t)
        self._merge(t)
        self._gc(t)
        # после слияния ключи могли поменяться
        for tid, k in list(out.items()):
            if k.startswith("g"):
                out[tid] = f"g{self.links[(cam, tid)]}"
        return out

    def _match(self, cam: str, t: float, xy: np.ndarray) -> int:
        best, bd = None, self.gate
        for g in self.tracks.values():
            if t - g.t > self.ttl:
                continue
            m = g.members.get(cam)
            if m is not None and t - m[2] < 0.5:
                continue  # эта камера уже видит этого человека другим треком
            pred = g.xy + g.vel * min(t - g.t, 1.0)
            d = float(np.linalg.norm(pred - xy))
            if d < bd:
                best, bd = g.gid, d
        if best is None:
            best = self._next
            self._next += 1
            self.tracks[best] = GlobalTrack(best, xy.copy(), t)
        return best

    def _refresh(self, g: GlobalTrack, t: float) -> None:
        pts = [xy for _, xy, tt in g.members.values() if t - tt < 0.6]
        if not pts:
            return
        new = np.mean(pts, axis=0)
        dt = t - g.t
        if dt > 1e-3:
            g.vel = 0.7 * g.vel + 0.3 * (new - g.xy) / dt
        g.xy, g.t = new, t

    def _merge(self, t: float) -> None:
        live = [g for g in self.tracks.values() if t - g.t < 0.6]
        for i in range(len(live)):
            for j in range(i + 1, len(live)):
                a, b = live[i], live[j]
                if a.gid not in self.tracks or b.gid not in self.tracks:
                    continue
                cams_a = {c for c, (_, _, tt) in a.members.items() if t - tt < 0.6}
                cams_b = {c for c, (_, _, tt) in b.members.items() if t - tt < 0.6}
                if cams_a & cams_b:
                    continue
                # гистерезис: шум положения далеко от камеры ~1 м, поэтому одиночный «выброс» не сбрасывает
                # накопленные совпадения, а явное расхождение (> 2 gate) — сбрасывает
                d = float(np.linalg.norm(a.xy - b.xy))
                n = a.close_count.get(b.gid, 0)
                if d < self.gate:
                    n += 1
                elif d > 2 * self.gate:
                    n = 0
                else:
                    n = max(n - 1, 0)
                a.close_count[b.gid] = n
                if n >= self.merge_after:
                    keep, drop = (a, b) if a.gid < b.gid else (b, a)
                    keep.members.update(drop.members)
                    for k, v in self.links.items():
                        if v == drop.gid:
                            self.links[k] = keep.gid
                    del self.tracks[drop.gid]

    def _gc(self, t: float) -> None:
        for gid in [g.gid for g in self.tracks.values() if t - g.t > self.ttl]:
            del self.tracks[gid]
        for k in [k for k, v in self.links.items() if v not in self.tracks]:
            del self.links[k]

    def positions(self, t: float, max_age: float = 1.0) -> list[tuple[int, np.ndarray, list[str]]]:
        return [(g.gid, g.xy, sorted(c for c, (_, _, tt) in g.members.items() if t - tt < max_age))
                for g in self.tracks.values() if t - g.t < max_age]
