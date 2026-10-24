"""Кадр-снимок и видеоклип для каждого события.

У каждой камеры кольцевой буфер последних pre_roll_s секунд (кадры хранятся сжатыми в JPEG,
чтобы не держать в памяти сырые). Когда событие стартует, клип начинается с кадров из
буфера (что было ДО нарушения), продолжается, пока событие активно (не дольше max_clip_s),
и ещё post_roll_s после его конца. Рамка нарушителя подсвечивается на каждом кадре клипа.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

import cv2
import numpy as np


@dataclass
class _Frame:
    ts: float
    jpg: bytes
    scale: float
    boxes: dict[str, np.ndarray]  # subject -> рамка (в пикселях исходного кадра)


@dataclass
class _ClipJob:
    event_id: str
    subject_keys: set[str]
    label: str
    path: str
    end_ts: float | None = None
    max_ts: float = 0.0
    frames: list[_Frame] = field(default_factory=list)
    done_cb: Callable[[str, str | None], None] | None = None


def _pick_writer(path_base: str, fps: float, size: tuple[int, int]) -> tuple[cv2.VideoWriter | None, str]:
    """H.264 в mp4 (играется в браузере) -> VP8 webm -> mp4v."""
    for fourcc, ext in (("avc1", ".mp4"), ("VP80", ".webm"), ("mp4v", ".mp4")):
        p = path_base + ext
        w = cv2.VideoWriter(p, cv2.VideoWriter_fourcc(*fourcc), fps, size)
        if w.isOpened():
            return w, p
        w.release()
        if os.path.exists(p):
            os.remove(p)
    return None, ""


class ClipRecorder:
    def __init__(self, out_dir: str, pre_roll_s: float = 4.0, post_roll_s: float = 2.0, max_clip_s: float = 60.0,
                 width: int = 960, jpeg_quality: int = 80):
        self.out_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)
        self.pre, self.post, self.max_len = pre_roll_s, post_roll_s, max_clip_s
        self.width, self.q = width, jpeg_quality
        self.buffers: dict[str, deque[_Frame]] = {}
        self.jobs: dict[str, list[_ClipJob]] = {}
        self.fps: dict[str, float] = {}
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []
        self._ffmpeg = shutil.which("ffmpeg")

    def push(self, cam: str, ts: float, frame: np.ndarray, boxes: dict[str, np.ndarray]) -> None:
        h, w = frame.shape[:2]
        s = min(1.0, self.width / w)
        small = cv2.resize(frame, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else frame
        ok, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, self.q])
        fr = _Frame(ts, jpg.tobytes(), s, boxes)
        with self._lock:
            buf = self.buffers.setdefault(cam, deque())
            if buf:
                dt = ts - buf[-1].ts
                if dt > 0:
                    self.fps[cam] = 0.9 * self.fps.get(cam, 1 / dt) + 0.1 / dt
            buf.append(fr)
            while buf and ts - buf[0].ts > self.pre:
                buf.popleft()
            finished = []
            for job in self.jobs.get(cam, []):
                if ts <= job.max_ts and (job.end_ts is None or ts <= job.end_ts + self.post):
                    job.frames.append(fr)
                else:
                    finished.append(job)
            for job in finished:
                self.jobs[cam].remove(job)
                th = threading.Thread(target=self._write, args=(cam, job), daemon=True)
                th.start()
                self._threads = [t for t in self._threads if t.is_alive()] + [th]

    def snapshot(self, cam: str, frame: np.ndarray, box, label: str, path: str) -> str:
        img = frame.copy()
        if box is not None:
            x1, y1, x2, y2 = [int(v) for v in box]
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 3)
            _label(img, label, x1, y1)
        h, w = img.shape[:2]
        s = min(1.0, 1280 / w)
        if s < 1:
            img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, 88])
        return path

    def start(self, cam: str, event_id: str, subject_keys: set[str], label: str, start_ts: float,
              done_cb: Callable[[str, str | None], None] | None = None, suffix: str = "") -> None:
        with self._lock:
            pre = [f for f in self.buffers.get(cam, []) if f.ts >= start_ts - self.pre]
            job = _ClipJob(event_id, set(subject_keys), label,
                           os.path.join(self.out_dir, f"{event_id}{suffix}"),
                           max_ts=(pre[0].ts if pre else start_ts) + self.max_len, frames=list(pre), done_cb=done_cb)
            self.jobs.setdefault(cam, []).append(job)

    def add_subject(self, event_id: str, key: str) -> None:
        with self._lock:
            for jobs in self.jobs.values():
                for j in jobs:
                    if j.event_id == event_id:
                        j.subject_keys.add(key)

    def stop(self, event_id: str, end_ts: float) -> None:
        with self._lock:
            for jobs in self.jobs.values():
                for j in jobs:
                    if j.event_id == event_id and j.end_ts is None:
                        j.end_ts = end_ts

    def flush(self) -> None:
        with self._lock:
            pending = [(cam, j) for cam, jobs in self.jobs.items() for j in jobs]
            self.jobs = {}
            threads = list(self._threads)
        for th in threads:  # клипы, которые уже пишутся в фоне
            th.join(timeout=60)
        for cam, j in pending:
            self._write(cam, j)

    def _write(self, cam: str, job: _ClipJob) -> None:
        path = None
        try:
            if job.frames:
                first = cv2.imdecode(np.frombuffer(job.frames[0].jpg, np.uint8), cv2.IMREAD_COLOR)
                h, w = first.shape[:2]
                fps = float(np.clip(self.fps.get(cam, 8.0), 1.0, 30.0))
                writer, path = _pick_writer(job.path, fps, (w, h))
                if writer is not None:
                    for fr in job.frames:
                        img = cv2.imdecode(np.frombuffer(fr.jpg, np.uint8), cv2.IMREAD_COLOR)
                        for key, b in fr.boxes.items():
                            if key in job.subject_keys:
                                x1, y1, x2, y2 = (np.asarray(b) * fr.scale).astype(int)
                                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
                                _label(img, job.label, x1, y1)
                        cv2.putText(img, _fmt_ts(fr.ts), (8, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                                    (255, 255, 255), 2, cv2.LINE_AA)
                        writer.write(img)
                    writer.release()
                    path = self._maybe_transcode(path)
        except Exception as e:  # noqa: BLE001 — клип не должен ронять пайплайн
            print(f"[recorder] ошибка записи клипа {job.event_id}: {e!r}")
            path = None
        if job.done_cb:
            job.done_cb(job.event_id, path)

    def _maybe_transcode(self, path: str) -> str:
        if not path.endswith(".mp4") or not self._ffmpeg:
            return path
        try:  # mp4v браузеры не играют — перекодируем в H.264, если есть ffmpeg
            probe = subprocess.run([self._ffmpeg, "-v", "error", "-i", path, "-f", "null", "-"], capture_output=True,
                                   timeout=5)
            tmp = path[:-4] + ".h264.mp4"
            r = subprocess.run([self._ffmpeg, "-y", "-v", "error", "-i", path, "-c:v", "libx264", "-preset", "veryfast",
                                "-pix_fmt", "yuv420p", "-movflags", "+faststart", tmp], capture_output=True, timeout=120)
            if r.returncode == 0 and os.path.getsize(tmp) > 0 and probe.returncode == 0:
                os.replace(tmp, path)
            elif os.path.exists(tmp):
                os.remove(tmp)
        except Exception:  # noqa: BLE001
            pass
        return path


def _fmt_ts(ts: float) -> str:
    import time

    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def _label(img: np.ndarray, text: str, x: int, y: int) -> None:
    """Подпись латиницей/кириллицей: Hershey-шрифты OpenCV кириллицу не умеют, поэтому через PIL если есть."""
    try:
        from .text import put_text

        put_text(img, text, (x, max(0, y - 24)), (255, 255, 255), bg=(0, 0, 200))
    except Exception:  # noqa: BLE001
        cv2.putText(img, text.encode("ascii", "ignore").decode() or "violation", (x, max(12, y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)
