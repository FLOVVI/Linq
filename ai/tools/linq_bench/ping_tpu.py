"""Диагностика облака LinQ: жив ли брокер, сколько задач в очереди, есть ли воркеры, отвечает ли плата.

Шлёт ровно один запрос (самая маленькая модель) и ждёт до --timeout секунд.
    python tools/linq_bench/ping_tpu.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default=os.path.join(ROOT, "models", "helmet_cls_v8n_v2_96.json"))
    ap.add_argument("--timeout", type=float, default=120)
    a = ap.parse_args()
    import pika

    host = os.environ.get("LINQ_BROKER", "10.0.114.30")
    t0 = time.monotonic()
    conn = pika.BlockingConnection(pika.ConnectionParameters(host, 5672, credentials=pika.PlainCredentials("guest", "guest"),
                                                             socket_timeout=10, blocked_connection_timeout=10))
    ch = conn.channel()
    q = ch.queue_declare(queue="input", passive=True).method
    print(f"брокер {host}: подключение {time.monotonic() - t0:.2f} с; очередь input: задач {q.message_count}, "
          f"воркеров (consumers) {q.consumer_count}")
    conn.close()
    if q.consumer_count == 0:
        print("Воркеров нет — облачный TPU сейчас не обслуживает очередь (сторона организаторов).")

    from safetyvision.inference.backends import make_backend

    spec = json.load(open(a.spec, encoding="utf-8"))
    be = make_backend("linq_cloud", spec, os.path.dirname(a.spec))
    be.timeout_s = a.timeout
    x = {spec["input"]["name"]: np.zeros(spec["input"]["shape"], np.float32)}
    t0 = time.monotonic()
    try:
        out = be.run(x)
        print(f"ответ за {time.monotonic() - t0:.2f} с: {[(k, list(np.asarray(v).shape)) for k, v in out.items()]}, "
              f"воркер {be.last_worker}")
    except Exception as e:  # noqa: BLE001
        print(f"нет ответа за {time.monotonic() - t0:.1f} с: {e!r}")
    finally:
        be.close()


if __name__ == "__main__":
    main()
