"""ByteTrack (Zhang et al., 2022) на numpy: фильтр Калмана + двухэтапное сопоставление.

Сначала треки сопоставляются с уверенными детекциями, затем оставшиеся — с неуверенными
(частично перекрытые люди часто дают низкий score). Потерянный трек живёт `track_buffer`
секунд, поэтому короткие перекрытия не порождают новый ID — а значит, и новое событие.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..geometry.boxes import iou_matrix


def linear_assignment(cost: np.ndarray, thresh: float) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    if cost.size == 0:
        return [], list(range(cost.shape[0])), list(range(cost.shape[1]))
    try:
        from scipy.optimize import linear_sum_assignment

        r, c = linear_sum_assignment(cost)
        pairs = [(i, j) for i, j in zip(r, c) if cost[i, j] <= thresh]
    except ImportError:  # жадное сопоставление, если scipy нет
        pairs, used_r, used_c = [], set(), set()
        for k in np.argsort(cost, axis=None):
            i, j = divmod(int(k), cost.shape[1])
            if cost[i, j] > thresh:
                break
            if i not in used_r and j not in used_c:
                pairs.append((i, j))
                used_r.add(i)
                used_c.add(j)
    mr = {i for i, _ in pairs}
    mc = {j for _, j in pairs}
    return pairs, [i for i in range(cost.shape[0]) if i not in mr], [j for j in range(cost.shape[1]) if j not in mc]


class KalmanXYAH:
    """Постоянная скорость в пространстве (cx, cy, aspect, h), как в SORT/ByteTrack."""

    def __init__(self) -> None:
        self.F = np.eye(8)
        self.F[:4, 4:] = np.eye(4)
        self.Hm = np.eye(4, 8)
        self.wp, self.wv = 1 / 20, 1 / 160

    def initiate(self, z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        h = z[3]
        mean = np.r_[z, np.zeros(4)]
        std = [2 * self.wp * h, 2 * self.wp * h, 1e-2, 2 * self.wp * h,
               10 * self.wv * h, 10 * self.wv * h, 1e-5, 10 * self.wv * h]
        return mean, np.diag(np.square(std))

    def predict(self, mean, cov, dt: float = 1.0):
        F = self.F.copy()
        F[:4, 4:] *= dt
        h = mean[3]
        std = [self.wp * h, self.wp * h, 1e-2, self.wp * h, self.wv * h, self.wv * h, 1e-5, self.wv * h]
        Q = np.diag(np.square(std)) * max(dt, 1e-3)
        return F @ mean, F @ cov @ F.T + Q

    def update(self, mean, cov, z):
        h = mean[3]
        R = np.diag(np.square([self.wp * h, self.wp * h, 1e-1, self.wp * h]))
        S = self.Hm @ cov @ self.Hm.T + R
        K = cov @ self.Hm.T @ np.linalg.inv(S)
        mean = mean + K @ (z - self.Hm @ mean)
        cov = (np.eye(8) - K @ self.Hm) @ cov
        return mean, cov


def xyxy_to_xyah(b: np.ndarray) -> np.ndarray:
    w, h = b[2] - b[0], b[3] - b[1]
    return np.array([b[0] + w / 2, b[1] + h / 2, w / max(h, 1e-6), h], np.float64)


def xyah_to_xyxy(m: np.ndarray) -> np.ndarray:
    w = m[2] * m[3]
    return np.array([m[0] - w / 2, m[1] - m[3] / 2, m[0] + w / 2, m[1] + m[3] / 2], np.float32)


@dataclass
class Track:
    track_id: int
    box: np.ndarray
    score: float
    cls: int
    t_start: float
    t_last: float
    mean: np.ndarray
    cov: np.ndarray
    kpts: np.ndarray | None = None
    hits: int = 1
    state: str = "tentative"  # tentative / tracked / lost / removed
    matched: bool = True  # сопоставлен с детекцией на текущем кадре
    det_index: int = -1  # индекс детекции текущего кадра
    history: deque = field(default_factory=lambda: deque(maxlen=90))  # (t, foot_x, foot_y, box_h)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def foot(self) -> tuple[float, float]:
        return float((self.box[0] + self.box[2]) / 2), float(self.box[3])

    @property
    def confirmed(self) -> bool:
        return self.state in ("tracked", "lost") and self.hits >= 2


class ByteTracker:
    def __init__(self, high_thresh: float = 0.5, low_thresh: float = 0.15, new_track_thresh: float = 0.55,
                 match_thresh: float = 0.8, track_buffer_s: float = 3.0, min_hits: int = 2,
                 relink_s: float = 1.5, relink_min_score: float = 0.3):
        self.high, self.low, self.new_thr = high_thresh, low_thresh, new_track_thresh
        self.relink_s, self.relink_min_score = relink_s, relink_min_score
        self.match_thresh = match_thresh
        self.buffer_s = track_buffer_s
        self.min_hits = min_hits
        self.kf = KalmanXYAH()
        self.tracks: list[Track] = []
        self._next_id = 1
        self._t_prev: float | None = None
        self._dt_nominal = 1 / 8

    def _predict(self, t: float) -> None:
        dt = 1.0 if self._t_prev is None else max((t - self._t_prev) / self._dt_nominal, 0.1)
        for tr in self.tracks:
            if tr.state != "tracked":
                tr.mean[7] = 0  # у потерянных не растягиваем высоту
            tr.mean, tr.cov = self.kf.predict(tr.mean, tr.cov, dt)
            tr.box = xyah_to_xyxy(tr.mean)
            tr.matched = False
            tr.det_index = -1

    @staticmethod
    def _relink_pairs(lost: list[Track], boxes: np.ndarray, dets: list[int]) -> list[tuple[int, Track]]:
        """Жадно: детекция, у которой точка стоп ближе всего к последней точке стоп трека (в долях роста)."""
        cand = []
        for tr in lost:
            t_last, fx, fy, _ = tr.history[-1]
            # рост — по рамке стоя за последние секунды (у уже лежащего рамка низкая)
            h = max(bh for tt, _, _, bh in tr.history if t_last - tt <= 3.0)
            for d in dets:
                b = boxes[d]
                w, bh = b[2] - b[0], b[3] - b[1]
                if w > 1.6 * h or bh > 1.2 * h:  # лежащий не длиннее роста и не выше стоящего
                    continue
                dist = np.hypot((b[0] + b[2]) / 2 - fx, b[3] - fy) / max(h, 1.0)
                if dist < 0.6:
                    cand.append((dist, d, tr))
        out, used_d, used_t = [], set(), set()
        for dist, d, tr in sorted(cand, key=lambda c: c[0]):
            if d in used_d or tr.track_id in used_t:
                continue
            used_d.add(d)
            used_t.add(tr.track_id)
            out.append((d, tr))
        return out

    def _relink(self, tr: Track, box, score, cls, kpts, t, di) -> None:
        # форма рамки сменилась скачком — фильтр Калмана начинаем заново, иначе он «размажет» скачок в скорость
        hits = tr.hits
        self._assign(tr, box, score, cls, kpts, t, di)
        tr.mean, tr.cov = self.kf.initiate(xyxy_to_xyah(box))
        tr.hits = hits + 1

    def _assign(self, tr: Track, box, score, cls, kpts, t, di) -> None:
        tr.mean, tr.cov = self.kf.update(tr.mean, tr.cov, xyxy_to_xyah(box))
        tr.box = np.asarray(box, np.float32)
        tr.score, tr.cls, tr.t_last = float(score), int(cls), t
        tr.kpts = kpts
        tr.hits += 1
        tr.matched, tr.det_index = True, di
        if tr.state in ("tentative", "lost") and tr.hits >= self.min_hits:
            tr.state = "tracked"
        tr.history.append((t, *tr.foot, float(box[3] - box[1])))

    def update(self, boxes: np.ndarray, scores: np.ndarray, t: float, classes: np.ndarray | None = None,
               kpts: np.ndarray | None = None) -> list[Track]:
        """boxes: (N,4) xyxy; t — время кадра в секундах. Возвращает активные (видимые) треки."""
        n = len(boxes)
        classes = np.zeros(n, int) if classes is None else classes
        if self._t_prev is not None and t > self._t_prev:
            self._dt_nominal = 0.9 * self._dt_nominal + 0.1 * min(t - self._t_prev, 1.0)
        self._predict(t)
        self._t_prev = t

        hi = np.nonzero(scores >= self.high)[0]
        lo = np.nonzero((scores >= self.low) & (scores < self.high))[0]
        pool = [tr for tr in self.tracks if tr.state in ("tracked", "lost", "tentative")]

        # 1) уверенные детекции — все живые треки
        cost = 1 - iou_matrix(np.array([tr.box for tr in pool]).reshape(-1, 4), boxes[hi])
        pairs, um_t, um_d = linear_assignment(cost, self.match_thresh)
        for i, j in pairs:
            d = hi[j]
            self._assign(pool[i], boxes[d], scores[d], classes[d], None if kpts is None else kpts[d], t, int(d))
        rest = [pool[i] for i in um_t if pool[i].state == "tracked"]
        left_hi = hi[um_d]

        # 2) неуверенные детекции — оставшиеся подтверждённые треки
        cost = 1 - iou_matrix(np.array([tr.box for tr in rest]).reshape(-1, 4), boxes[lo])
        pairs, um_t2, um_lo = linear_assignment(cost, 0.5)
        for i, j in pairs:
            d = lo[j]
            self._assign(rest[i], boxes[d], scores[d], classes[d], None if kpts is None else kpts[d], t, int(d))

        # 2b) человек упал или присел: рамка резко сменила форму (IoU мал, а детектор у лежащего часто
        # неуверен), но точка стоп осталась на месте — привязываем к тому же треку, а не теряем его
        left = [int(d) for d in left_hi] + [int(lo[j]) for j in um_lo if scores[lo[j]] >= self.relink_min_score]
        lost = [tr for tr in pool if not tr.matched and tr.confirmed and t - tr.t_last <= self.relink_s
                and tr.history]
        for d, tr in self._relink_pairs(lost, boxes, left):
            self._relink(tr, boxes[d], scores[d], classes[d], None if kpts is None else kpts[d], t, d)
            left.remove(d)
        left_hi = [d for d in left if scores[d] >= self.high]

        # 3) новые треки
        for d in left_hi:
            if scores[d] < self.new_thr:
                continue
            m, c = self.kf.initiate(xyxy_to_xyah(boxes[d]))
            tr = Track(self._next_id, np.asarray(boxes[d], np.float32), float(scores[d]), int(classes[d]), t, t,
                       m, c, None if kpts is None else kpts[d], det_index=int(d))
            tr.history.append((t, *tr.foot, float(boxes[d][3] - boxes[d][1])))
            if self.min_hits <= 1:
                tr.state = "tracked"
            self._next_id += 1
            self.tracks.append(tr)

        # 4) жизненный цикл
        for tr in self.tracks:
            if tr.matched:
                continue
            if tr.state == "tentative":
                tr.state = "removed"
            elif tr.state == "tracked":
                tr.state = "lost"
            if tr.state == "lost" and t - tr.t_last > self.buffer_s:
                tr.state = "removed"
        self.tracks = [tr for tr in self.tracks if tr.state != "removed"]
        return [tr for tr in self.tracks if tr.matched and tr.confirmed]

    def lost_tracks(self) -> list[Track]:
        return [tr for tr in self.tracks if tr.state == "lost"]
