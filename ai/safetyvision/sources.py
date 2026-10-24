"""Источники кадров: видеофайл, RTSP/HTTP-поток, веб-камера, папка с изображениями.

Живой поток читается отдельным потоком (thread), который держит только последний кадр, —
если обработка не успевает, старые кадры выбрасываются и задержка не копится.
Файл в офлайн-режиме читается последовательно с прореживанием до process_fps, а метки
времени берутся из видео (так несколько записей одного помещения обрабатываются синхронно).
"""

from __future__ import annotations

import glob
import os
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class FramePacket:
    ts: float  # время кадра (эпоха, сек)
    frame: np.ndarray
    capture_wall: float  # когда кадр получен (для измерения задержки)
    index: int


class FrameSource:
    live = False

    def next_ts(self) -> float | None:
        """Время следующего кадра (для синхронной обработки нескольких файлов)."""
        return None

    def read(self) -> FramePacket | None:
        raise NotImplementedError

    def close(self) -> None:
        pass

    @property
    def finished(self) -> bool:
        return False


def _parse_source(src):
    if isinstance(src, int) or (isinstance(src, str) and src.isdigit()):
        return int(src)
    return src


class VideoFileSource(FrameSource):
    def __init__(self, path: str, process_fps: float, t0: float, loop: bool = False, realtime: bool = False,
                 offset_s: float = 0.0):
        self.path = path
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise RuntimeError(f"Не удалось открыть видео {path}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
        if not (1 <= self.fps <= 240):
            self.fps = 25.0
        self.step = 1.0 / max(process_fps, 0.1)
        self.t0, self.loop, self.realtime, self.offset = t0, loop, realtime, offset_s
        self.frame_no = 0
        self.next_media_t = 0.0
        self.loops = 0
        self.duration = (self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / self.fps
        self._done = False
        self._wall0 = time.time()
        self._index = 0

    def next_ts(self) -> float | None:
        return None if self._done else self.t0 + self.offset + self.loops * self.duration + self.next_media_t

    @property
    def finished(self) -> bool:
        return self._done

    def read(self) -> FramePacket | None:
        if self._done:
            return None
        target = self.next_media_t
        if self.realtime:  # не успеваем за временем ролика — пропускаем кадры, как живой поток, а не замедляем видео
            target = max(target, time.time() - self._wall0 - self.offset - self.loops * self.duration)
        while True:
            media_t = self.frame_no / self.fps
            if media_t + 0.5 / self.fps >= target:
                ok, frame = self.cap.read()
                self.frame_no += 1
                if not ok:
                    return self._eof()
                break
            if not self.cap.grab():
                return self._eof()
            self.frame_no += 1
        self.next_media_t = target + self.step
        ts = self.t0 + self.offset + self.loops * self.duration + media_t
        if self.realtime:
            lag = (ts - self.t0) - (time.time() - self._wall0)
            if lag > 0:
                time.sleep(min(lag, 1.0))
        self._index += 1
        return FramePacket(ts, frame, time.time(), self._index)

    def _eof(self) -> FramePacket | None:
        if self.loop and self.frame_no > 1:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self.loops += 1
            self.frame_no, self.next_media_t = 0, 0.0
            return self.read()
        self._done = True
        return None

    def close(self):
        self.cap.release()


class LiveSource(FrameSource):
    live = True

    def __init__(self, src, reconnect_s: float = 2.0):
        self.src = _parse_source(src)
        self.reconnect_s = reconnect_s
        self._lock = threading.Lock()
        self._pkt: FramePacket | None = None
        self._consumed = True
        self._stop = False
        self._index = 0
        self.connected = False
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while not self._stop:
            cap = cv2.VideoCapture(self.src)
            if isinstance(self.src, str) and self.src.startswith("rtsp"):
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.isOpened():
                self.connected = False
                time.sleep(self.reconnect_s)
                continue
            self.connected = True
            while not self._stop:
                ok, frame = cap.read()
                if not ok:
                    break
                now = time.time()
                self._index += 1
                with self._lock:
                    self._pkt = FramePacket(now, frame, now, self._index)
                    self._consumed = False
            cap.release()
            self.connected = False
            time.sleep(self.reconnect_s)

    def read(self) -> FramePacket | None:
        with self._lock:
            if self._consumed or self._pkt is None:
                return None
            self._consumed = True
            return self._pkt

    def close(self):
        self._stop = True


class ImageFolderSource(FrameSource):
    """Набор фотографий: каждый файл — отдельный кадр (интервал step секунд)."""

    def __init__(self, pattern: str, t0: float, step: float = 1.0):
        if os.path.isdir(pattern):
            files = sorted(sum((glob.glob(os.path.join(pattern, e)) for e in ("*.jpg", "*.jpeg", "*.png", "*.bmp")), []))
        else:
            files = sorted(glob.glob(pattern))
        self.files = files
        self.t0, self.step = t0, step
        self.i = 0

    def next_ts(self):
        return None if self.i >= len(self.files) else self.t0 + self.i * self.step

    @property
    def finished(self):
        return self.i >= len(self.files)

    def read(self):
        while self.i < len(self.files):
            f = self.files[self.i]
            self.i += 1
            img = cv2.imread(f)
            if img is not None:
                return FramePacket(self.t0 + (self.i - 1) * self.step, img, time.time(), self.i)
        return None


def open_source(src, process_fps: float, t0: float, loop: bool = False, realtime: bool = False,
                offset_s: float = 0.0) -> FrameSource:
    s = _parse_source(src)
    if isinstance(s, int) or (isinstance(s, str) and "://" in s):
        return LiveSource(s)
    if isinstance(s, str) and (os.path.isdir(s) or any(ch in s for ch in "*?")):
        return ImageFolderSource(s, t0, 1.0 / max(process_fps, 0.1))
    if isinstance(s, str) and s.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
        return ImageFolderSource(s, t0)
    return VideoFileSource(s, process_fps, t0, loop=loop, realtime=realtime, offset_s=offset_s)
