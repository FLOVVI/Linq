"""Бэкенды инференса: один интерфейс для onnxruntime (отладка на ноутбуке) и LinQ TPU.

LinQ TPU доступен двумя путями: локально через pytpu (плата в той же машине) и через облачный
сервис хакатона — брокер RabbitMQ, который передаёт тензоры воркеру с платой (tpu_pycloud_format).

Пред- и постпроцессинг живут вне бэкенда, поэтому одна и та же модель (обрезанный ONNX
и скомпилированная из него .tpu-программа) даёт одинаковый выход на обеих платформах.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections import deque
from typing import Any

import numpy as np


class LatencyMeter:
    def __init__(self, window: int = 200):
        self.samples: deque[float] = deque(maxlen=window)
        self.total_calls = 0
        self.lock = threading.Lock()

    def add(self, ms: float) -> None:
        with self.lock:
            self.samples.append(ms)
            self.total_calls += 1

    def summary(self) -> dict[str, float]:
        with self.lock:
            if not self.samples:
                return {"calls": self.total_calls}
            a = np.asarray(self.samples)
            return {
                "calls": self.total_calls,
                "mean_ms": float(a.mean()),
                "p50_ms": float(np.percentile(a, 50)),
                "p95_ms": float(np.percentile(a, 95)),
                "fps": float(1000.0 / a.mean()) if a.mean() > 0 else 0.0,
            }


class Backend:
    name = "base"

    def __init__(self) -> None:
        self.latency = LatencyMeter()

    def run(self, inputs: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        t0 = time.perf_counter()
        out = self._run(inputs)
        self.latency.add((time.perf_counter() - t0) * 1000.0)
        return out

    def _run(self, inputs: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        raise NotImplementedError

    def close(self) -> None:
        pass


class OnnxBackend(Backend):
    name = "onnx"

    def __init__(self, onnx_path: str, providers: list[str] | None = None, threads: int = 0):
        super().__init__()
        import onnxruntime as ort

        so = ort.SessionOptions()
        if threads:
            so.intra_op_num_threads = threads
        avail = ort.get_available_providers()
        providers = [p for p in (providers or ["CPUExecutionProvider"]) if p in avail] or ["CPUExecutionProvider"]
        self.sess = ort.InferenceSession(onnx_path, sess_options=so, providers=providers)
        self.output_names = [o.name for o in self.sess.get_outputs()]

    def _run(self, inputs):
        outs = self.sess.run(self.output_names, inputs)
        return dict(zip(self.output_names, outs))


class CvDnnBackend(Backend):
    """ONNX на CPU через OpenCV DNN — когда onnxruntime нет (сервер LinQ), а модель не переносит int8."""

    name = "cpu_cv2"

    def __init__(self, onnx_path: str, output_names: list[str]):
        super().__init__()
        import cv2

        self.net = cv2.dnn.readNetFromONNX(onnx_path)
        self.output_names = output_names
        self._lock = threading.Lock()

    def _run(self, inputs):
        with self._lock:
            (x,) = inputs.values()
            self.net.setInput(np.ascontiguousarray(x, np.float32))
            outs = self.net.forward(self.output_names)
        return dict(zip(self.output_names, outs))


    """Одно устройство LinQ TPU открывается один раз и делится между моделями."""

    _lock = threading.Lock()
    _devices: dict[int, Any] = {}
    _stack = contextlib.ExitStack()

    @classmethod
    def get(cls, index: int):
        import pytpu as tpu

        with cls._lock:
            if index not in cls._devices:
                names = tpu.Device.list_devices()
                if not names:
                    raise RuntimeError("LinQ TPU не найден: проверьте ls /dev/tpu*")
                cls._devices[index] = cls._stack.enter_context(tpu.Device.open(names[index % len(names)]))
            return cls._devices[index]


class TpuBackend(Backend):
    """Инференс .tpu-программы на ускорителе LinQ через pytpu."""

    name = "linq_tpu"

    def __init__(self, program_path: str, device_index: int = 0, output_alias: dict[str, str] | None = None):
        super().__init__()
        self._stack = contextlib.ExitStack()
        self.device = _TpuDevicePool.get(device_index)
        self.program = self._stack.enter_context(self.device.load(program_path))
        self.inference = self._stack.enter_context(self.program.inference())
        # имена выходов в .tpu могут отличаться от исходного ONNX — alias переводит их обратно
        self.output_alias = output_alias or {}
        self._lock = threading.Lock()

    def _run(self, inputs):
        with self._lock:  # одна сессия инференса — один поток
            if hasattr(self.inference, "sync"):
                out = self.inference.sync(inputs)
            else:
                out = self.inference.run(inputs)
        return {self.output_alias.get(k, k): np.asarray(v) for k, v in out.items()}

    def close(self):
        self._stack.close()


class CloudTpuBackend(Backend):
    """Инференс .tpu-программы в облаке LinQ: тензоры уходят брокеру RabbitMQ, ответ приходит в свою очередь.

    Конвенции облака (examples/example.ipynb на сервере): exchange ``tpu.direct``, очередь задач ``input``,
    программа — файл в ``/auto/cache/<LOGIN>``, путь передаётся заголовком ``file://...?raw=False``.
    Одно соединение и одна очередь ответов на модель; вызовы модели сериализуются блокировкой."""

    name = "linq_cloud"

    def __init__(self, program_path: str, login: str | None = None, host: str | None = None, port: int = 5672,
                 credentials: tuple[str, str] = ("guest", "guest"), timeout_s: float = 30.0,
                 output_alias: dict[str, str] | None = None):
        super().__init__()
        import getpass
        import os
        import shutil
        import uuid

        import pika
        from tpu_pycloud_format import (MESSAGE_ID_ATTR_NAME, RESPONSE_ROUTING_KEYS_ATTR_NAME,
                                        TARGET_URI_ATTR_NAME, PyTask, deserialize, serialize)

        self._fmt = (MESSAGE_ID_ATTR_NAME, RESPONSE_ROUTING_KEYS_ATTR_NAME, TARGET_URI_ATTR_NAME,
                     PyTask, deserialize, serialize)
        self._pika = pika
        login = login or os.environ.get("LINQ_LOGIN") or getpass.getuser()
        remote = os.environ.get("LINQ_REMOTE_CACHE")  # программы уже загружены на сервер (запуск с другой машины по VPN)
        if remote:
            dst = remote.rstrip("/") + "/" + os.path.basename(program_path)
        else:
            prog_dir = os.path.join("/auto/cache", login)
            dst = os.path.join(prog_dir, os.path.basename(program_path))
            # воркер читает программу только из /auto/cache/<LOGIN>
            if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(program_path):
                shutil.copy(program_path, dst)
        self.uri = f"file://{dst}?raw=False"
        self.timeout_s = float(os.environ.get("LINQ_TIMEOUT", timeout_s))
        self.retries = int(os.environ.get("LINQ_RETRIES", 1))
        self.output_alias = output_alias or {}
        self._uuid = uuid
        self._conn = pika.BlockingConnection(pika.ConnectionParameters(
            host or os.environ.get("LINQ_BROKER", "10.0.114.30"), port,
            credentials=pika.PlainCredentials(*credentials), heartbeat=0))
        self._ch = self._conn.channel()
        self.reply_queue = f"sv_{uuid.uuid4().hex[:12]}"
        # exclusive: очередь живёт, пока открыто соединение (auto_delete удалил бы её после первого ответа)
        self._ch.queue_declare(queue=self.reply_queue, exclusive=True)
        self._ch.queue_bind(exchange="tpu.direct", queue=self.reply_queue, routing_key=self.reply_queue)
        self._pending: set[str] = set()
        self._inbox: dict[str, bytes] = {}
        self._ch.basic_consume(self.reply_queue, self._on_reply, auto_ack=True)
        self._lock = threading.Lock()
        self.last_worker: dict = {}
        self.tpu_latency = LatencyMeter()  # время инференса на плате по отчёту воркера, без сети и очереди

    def _on_reply(self, _ch, _method, props, body):
        tid = (props.headers or {}).get(self._fmt[0])
        if tid in self._pending:  # опоздавшие ответы на брошенные по таймауту задачи не копим
            self._inbox[tid] = body

    def _publish(self, inputs: dict[str, np.ndarray]) -> str:
        import json

        mid, rkeys, target, PyTask, _, serialize = self._fmt
        task_id = self._uuid.uuid4().hex
        self._ch.basic_publish(
            exchange="tpu.direct", routing_key="input",
            body=serialize(PyTask({k: np.ascontiguousarray(v, np.float32) for k, v in inputs.items()})),
            properties=self._pika.BasicProperties(headers={
                target: self.uri, rkeys: json.dumps([self.reply_queue]), mid: task_id}))
        return task_id

    def _collect(self, ids: list[str]) -> dict[str, dict[str, np.ndarray]]:
        deserialize = self._fmt[4]
        self._pending.update(ids)
        t0 = time.monotonic()
        try:
            while not all(i in self._inbox for i in ids):
                if time.monotonic() - t0 > self.timeout_s:
                    raise TimeoutError(f"LinQ: нет ответа за {self.timeout_s} с")
                self._conn.process_data_events(time_limit=0.05)
        finally:
            self._pending.difference_update(ids)
        got = {}
        for tid in ids:
            data, _meta, worker = deserialize(self._inbox.pop(tid))
            self.last_worker = worker
            if not data:
                raise RuntimeError(f"LinQ: ошибка воркера: {worker.get('error_message')}")
            if worker.get("inference_time") is not None:
                self.tpu_latency.add(float(worker["inference_time"]) * 1000.0)
            got[tid] = {self.output_alias.get(k, k): np.asarray(v) for k, v in data.items()}
        return got

    def _run(self, inputs):
        with self._lock:
            for attempt in range(self.retries + 1):
                tid = self._publish(inputs)
                try:
                    return self._collect([tid])[tid]
                except TimeoutError:
                    # одиночная потеря ответа не должна ронять многочасовой поток камер: повторяем задачу
                    if attempt == self.retries:
                        raise
                    print(f"[linq] нет ответа за {self.timeout_s} с, повтор {attempt + 1}/{self.retries}", flush=True)

    def run_many(self, batch: list[dict[str, np.ndarray]]) -> list[dict[str, np.ndarray]]:
        """Несколько задач «в полёте» сразу: сеть до брокера не простаивает между кадрами."""
        with self._lock:
            ids = [self._publish(x) for x in batch]
            got = self._collect(ids)
        return [got[i] for i in ids]

    def close(self):
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001
            pass


def make_backend(kind: str, spec: dict[str, Any], base_dir: str = ".", **opts) -> Backend:
    import importlib.util
    import os

    def p(rel: str) -> str:
        return rel if os.path.isabs(rel) else os.path.join(base_dir, rel)

    if kind == "onnx":
        return OnnxBackend(p(spec["onnx"]), providers=opts.get("providers"), threads=opts.get("threads", 0))
    if kind == "cpu":  # onnxruntime, а если его нет — OpenCV DNN
        if importlib.util.find_spec("onnxruntime") is not None:
            return OnnxBackend(p(spec["onnx"]), threads=opts.get("threads", 0))
        outs = spec.get("outputs") or [lv[k] for lv in spec["levels"] for k in ("box", "cls", "kpt") if k in lv]
        return CvDnnBackend(p(spec["onnx"]), outs)
    if kind in ("tpu", "linq", "linq_tpu", "linq_cloud"):
        if not spec.get("tpu"):
            raise ValueError(f"В спецификации модели {spec.get('name')} нет пути к .tpu-программе")
        prog = p(spec["tpu"])
        # своя плата (pytpu) — напрямую; на сервере хакатона платы в контейнере нет, только облачный брокер
        if kind != "linq_cloud" and importlib.util.find_spec("pytpu") is not None:
            return TpuBackend(prog, device_index=opts.get("device_index", 0),
                              output_alias=spec.get("tpu_output_alias"))
        return CloudTpuBackend(prog, login=opts.get("login"), host=opts.get("broker"),
                               output_alias=spec.get("tpu_output_alias"))
    raise ValueError(f"Неизвестный бэкенд: {kind}")
