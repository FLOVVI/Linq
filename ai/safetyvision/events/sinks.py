"""Куда уходят события: журнал JSONL, вебхуки (бэкенд/БД команды), подписчики API (WebSocket)."""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import urllib.request
from collections import OrderedDict
from typing import Any, Callable


class JsonlSink:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.Lock()

    def __call__(self, kind: str, event: dict[str, Any]) -> None:
        with self._lock, open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": kind, "ts": round(time.time(), 3), "event": event}, ensure_ascii=False) + "\n")


class WebhookSink:
    """POST JSON на URL бэкенда; отправка в фоне с повторами, чтобы не тормозить видеоконвейер."""

    def __init__(self, url: str, timeout: float = 3.0, retries: int = 3):
        self.url, self.timeout, self.retries = url, timeout, retries
        self.q: queue.Queue = queue.Queue(maxsize=1000)
        threading.Thread(target=self._loop, daemon=True).start()

    def __call__(self, kind: str, event: dict[str, Any]) -> None:
        try:
            self.q.put_nowait({"kind": kind, "event": event})
        except queue.Full:
            pass

    def _loop(self) -> None:
        while True:
            msg = self.q.get()
            data = json.dumps(msg, ensure_ascii=False).encode()
            for attempt in range(self.retries):
                try:
                    req = urllib.request.Request(self.url, data=data, headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(req, timeout=self.timeout).read()
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(0.5 * 2 ** attempt)


class EventStore:
    """Журнал событий в памяти для API: фильтры по типу, камере, зоне, времени, статусу."""

    def __init__(self, max_events: int = 20000, persist_path: str | None = None):
        self.events: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.max = max_events
        self.listeners: list[Callable[[str, dict[str, Any]], None]] = []
        self._lock = threading.Lock()
        self.persist_path = persist_path
        if persist_path and os.path.exists(persist_path):
            self._load(persist_path)

    def _load(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ev = rec.get("event", {})
                if "id" in ev:
                    self.events[ev["id"]] = {**self.events.get(ev["id"], {}), **ev}

    def __call__(self, kind: str, event: dict[str, Any]) -> None:
        with self._lock:
            old = self.events.get(event["id"], {})
            if "review" in old and old["review"].get("status") != "pending":
                event = {**event, "review": old["review"]}
            self.events[event["id"]] = {**old, **event}
            self.events.move_to_end(event["id"])
            while len(self.events) > self.max:
                self.events.popitem(last=False)
        for cb in list(self.listeners):
            try:
                cb(kind, event)
            except Exception:  # noqa: BLE001
                pass

    def query(self, rule: str | None = None, camera: str | None = None, zone: str | None = None,
              status: str | None = None, review: str | None = None, since: float | None = None,
              until: float | None = None, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self.events.values())
        rules = set(rule.split(",")) if rule else None
        out = []
        for e in reversed(items):
            if rules and e["rule"] not in rules:
                continue
            if camera and camera != e["camera_id"] and camera not in e.get("cameras", []):
                continue
            if zone and zone not in e.get("zone_ids", []):
                continue
            if status and e["status"] != status:
                continue
            if review and e.get("review", {}).get("status") != review:
                continue
            end = e.get("end_ts") or e["start_ts"]
            if since is not None and end < since:
                continue
            if until is not None and e["start_ts"] > until:
                continue
            out.append(e)
        return out[offset: offset + limit]

    def get(self, event_id: str) -> dict[str, Any] | None:
        return self.events.get(event_id)

    def stats(self, since: float | None = None) -> dict[str, Any]:
        by_rule: dict[str, int] = {}
        by_cam: dict[str, int] = {}
        by_zone: dict[str, int] = {}
        by_hour: dict[str, int] = {}
        by_review: dict[str, int] = {}
        for e in self.query(since=since, limit=10 ** 9):
            by_rule[e["rule"]] = by_rule.get(e["rule"], 0) + 1
            by_cam[e["camera_id"]] = by_cam.get(e["camera_id"], 0) + 1
            for z in e.get("zone_ids", []):
                by_zone[z] = by_zone.get(z, 0) + 1
            h = time.strftime("%Y-%m-%d %H:00", time.localtime(e["start_ts"]))
            by_hour[h] = by_hour.get(h, 0) + 1
            r = e.get("review", {}).get("status", "pending")
            by_review[r] = by_review.get(r, 0) + 1
        return {"total": sum(by_rule.values()), "by_rule": by_rule, "by_camera": by_cam, "by_zone": by_zone,
                "by_hour": dict(sorted(by_hour.items())), "by_review": by_review}
