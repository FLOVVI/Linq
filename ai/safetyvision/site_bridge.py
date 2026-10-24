"""Мост ИИ-модуля и сайта команды (FastAPI + PostgreSQL + React, корень репозитория над ai/).

    python -m safetyvision bridge configs/site_bridge.yaml [--backend onnx|tpu]

Что делает:
  * берёт с сайта камеры, векторы правил и зоны (GET /ai/cameras) и следит за их изменением:
    правила и зоны применяются на ходу, новая камера или другой источник — перезапуск конвейера участка;
  * каждый участок сайта (site_id) — отдельный конвейер со своей миникартой из камер этого участка;
  * событие: начало сразу уходит на сайт (POST /events: тип, камера, зона, кадр, миникарта, точка на плане),
    по завершении — конец, длительность и клип (PATCH /events/{id}/ai);
  * раз в 3 с шлёт статус камер (FPS, задержка, бэкенд, адрес видеопотока) — PUT /ai/cameras/{id}/status;
  * отдаёт браузеру живое видео с разметкой: GET /stream/{camera_id} (MJPEG), миникарту: GET /map/{site_id}.png;
  * отметки оператора «Подтвердить» / «Ложное» складывает в набор для дообучения (runs/.../review).
"""

from __future__ import annotations

import base64
import copy
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import yaml

from .catalog import RULES
from .config import parse_site
from .pipeline import ModelSet, Pipeline
from .render import draw_camera

# позиция в векторе правил сайта -> правила каталога (пусто — у ИИ нет детектора)
SITE_VECTOR = [("running",), ("vehicle_proximity",), ("phone",), ("smoking", "fire"), (), (), ("fall",), (),
               ("helmet",), ("vest",), ("danger_zone",), ("gloves",), ("goggles",)]
RULE_TO_SITE = {"running": "RUNNING", "vehicle_proximity": "DANGER_PROXIMITY", "phone": "PHONE_USAGE",
                "smoking": "SMOKING_FIRE", "fire": "SMOKING_FIRE", "fall": "PERSON_FALL", "helmet": "NO_HELMET",
                "vest": "NO_VEST", "danger_zone": "DANGER_ZONE", "gloves": "NO_GLOVES", "goggles": "NO_GOGGLES"}
DANGER_ZONE_IDX = 10


def rules_from_vector(vec: list[int]) -> dict[str, int]:
    out = {r.code: 0 for r in RULES}
    for i, codes in enumerate(SITE_VECTOR):
        for c in codes:
            out[c] = int(bool(vec[i])) if i < len(vec) else 0
    return out


def _schedule(s: str | None) -> list[str]:
    """«07:55 – 12:00» -> ["07:55-12:00"]; «Круглосуточно» и пусто — всегда."""
    m = re.findall(r"(\d{1,2}:\d{2})", s or "")
    return [f"{m[0]}-{m[1]}"] if len(m) == 2 else []


def _points(z: dict) -> list[tuple[float, float]]:
    if z.get("shape") == "rect" and z.get("rect"):
        r = z["rect"]
        return [(r["x"], r["y"]), (r["x"] + r["w"], r["y"]), (r["x"] + r["w"], r["y"] + r["h"]), (r["x"], r["y"] + r["h"])]
    pts = [(p["x"], p["y"]) if isinstance(p, dict) else (p[0], p[1]) for p in z.get("points") or []]
    if len(pts) >= 3:  # как на сайте (sortPolygonPoints): вершины по кругу вокруг центра
        cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        pts.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    return pts


def zone_from_site(cam_id: str, z: dict, w: int, h: int, vec: list[int]) -> dict | None:
    """Зона сайта (проценты кадра) -> зона конвейера (пиксели кадра)."""
    pts = _points(z)
    if len(pts) < 3:
        return None
    d = {"id": f"{cam_id}:{z.get('id')}", "name": z.get("label") or "Зона", "camera": cam_id,
         "polygon_px": [[round(x * w / 100, 1), round(y * h / 100, 1)] for x, y in pts],
         "schedule": _schedule(z.get("schedule"))}
    kind = z.get("type", "danger")
    if kind == "danger":  # вход — нарушение, если у камеры включён тип 11 «Опасная зона»
        d.update(kind="danger", rules={"danger_zone": int(bool(vec[DANGER_ZONE_IDX])) if len(vec) > DANGER_ZONE_IDX else 1})
    elif kind == "attention":  # «Особое внимание» — на сайте это контроль СИЗ
        d.update(kind="area", rules={"helmet": 1, "vest": 1}, priority=1)
    else:  # «Слепая зона» — участок кадра, который камера не контролирует
        d.update(kind="area", rules={r.code: 0 for r in RULES}, priority=10)
    return d


class SiteApi:
    def __init__(self, url: str, key: str):
        self.url, self.key = url.rstrip("/"), key

    def req(self, method: str, path: str, body: Any = None, timeout: float = 15.0) -> Any:
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        r = urllib.request.Request(self.url + path, data=data, method=method,
                                   headers={"Content-Type": "application/json", "X-Api-Key": self.key})
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return json.loads(resp.read() or b"null")

    def download(self, path: str, dst: str) -> None:
        r = urllib.request.Request(self.url + path, headers={"X-Api-Key": self.key})
        with urllib.request.urlopen(r, timeout=120) as resp, open(dst + ".part", "wb") as f:
            while chunk := resp.read(1 << 20):
                f.write(chunk)
        os.replace(dst + ".part", dst)


def _b64(path: str | None) -> str | None:
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _ts(ts: float | None) -> str | None:
    return None if ts is None else datetime.fromtimestamp(ts).astimezone().isoformat(sep=" ", timespec="seconds")


class SitePipeline:
    """Конвейер одного участка сайта: его камеры, зоны и миникарта."""

    def __init__(self, bridge: "Bridge", site_id: int, cams: list[dict]):
        self.bridge, self.site_id, self.cams = bridge, site_id, cams
        self.sizes: dict[str, tuple[int, int]] = {}
        self.applied: dict[str, str] = {}
        raw = copy.deepcopy(bridge.template)
        raw["site"].update(id=f"site{site_id}", name=cams[0].get("site_name", f"Участок {site_id}"), rules={})
        raw["cameras"], raw["zones"] = [], []
        for c in cams:  # свои параметры правил демо-камеры (например, синие жилеты завода) — на весь участок
            for code, p in (bridge.demo(c).get("rule_params") or {}).items():
                raw["site"].setdefault("rule_params", {}).setdefault(code, {}).update(p)
        for c in cams:
            src, live = bridge.source_for(c)
            cid = f"c{c['id']}"
            raw["cameras"].append({"id": cid, "name": f"{c['code']} {c['name']}", "source": src, "loop": not live,
                                   "realtime": not live, "process_fps": bridge.cfg.get("process_fps", 5),
                                   "rules": rules_from_vector(c["rulesVector"]),
                                   "calibration": {"auto": {"person_height_m": 1.7}}})
            self.sizes[cid] = _probe_size(src)
            raw["zones"] += self._zones(c, cid)
            self.applied[cid] = self._sig(c)
        raw["events"]["output_dir"] = os.path.join(raw["events"].get("output_dir", "runs/site_bridge"), f"site{site_id}")
        self.site = parse_site(raw, base_dir=bridge.base_dir)
        models = bridge.models.get(site_id) or ModelSet(self.site)  # у каждого участка свои сессии моделей
        bridge.models[site_id] = models
        self.pipe = Pipeline(self.site, models, log=lambda m: bridge.log(f"[участок {site_id}] {m}"))
        self.pipe.sinks.append(lambda kind, ev: bridge.on_event(self, kind, ev))
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"site{site_id}")

    def _zones(self, c: dict, cid: str) -> list[dict]:
        w, h = self.sizes.get(cid) or (1280, 720)
        return [d for z in c.get("zones") or [] if (d := zone_from_site(cid, z, w, h, c["rulesVector"]))]

    @staticmethod
    def _sig(c: dict) -> str:
        return json.dumps([c["rulesVector"], c.get("zones")], sort_keys=True)

    def _run(self) -> None:
        try:
            self.pipe.run()
        except Exception as e:  # noqa: BLE001
            self.bridge.log(f"[участок {self.site_id}] конвейер остановился: {e!r}")

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.pipe.stop()
        self.thread.join(timeout=15)

    def update(self, c: dict) -> None:
        """Правила и зоны камеры изменились на сайте — применяем без перезапуска."""
        cid = f"c{c['id']}"
        rt = self.pipe.cams.get(cid)
        if rt is not None and rt.frame_hw:
            self.sizes[cid] = (rt.frame_hw[1], rt.frame_hw[0])
        if self.applied.get(cid) == self._sig(c) + str(self.sizes.get(cid)):
            return
        self.pipe.set_camera_rules(cid, rules_from_vector(c["rulesVector"]))
        for z in [z for z in self.site.zones if z.camera == cid]:
            self.pipe.delete_zone(z.id)
        for z in self._zones(c, cid):
            self.pipe.upsert_zone(z)
        self.applied[cid] = self._sig(c) + str(self.sizes.get(cid))
        self.cams = [c if x["id"] == c["id"] else x for x in self.cams]
        self.bridge.log(f"[участок {self.site_id}] {c['code']}: правила и зоны обновлены")


MAP_BOX_PX = (800, 560)   # типичный размер карты цеха на сайте: луч обзора камеры там рисуется в пикселях


def plan_pos(cam: dict, fx: float | None, fy: float | None) -> dict:
    """Точка кадра (fx, fy в %) -> точка на карте цеха (% карты) внутри луча обзора камеры.

    Так же считает сайт (eventPlanPos в App.jsx): низ кадра — у камеры, верх — на дальнем краю луча,
    левый/правый край кадра — края луча; направление — азимут камеры на карте + поворот PTZ."""
    pos = cam.get("mapPos") or {"x": 50, "y": 50}
    if fx is None or fy is None:
        return {"x": pos["x"], "y": pos["y"]}
    d = 0.3 + 0.7 * (1 - fy / 100)
    fwd, lat = d * 54, (fx / 100 - 0.5) * 2 * d * 27
    a = math.radians((cam.get("mapDirection") or 0) + (cam.get("panAngle") or 0))
    dx, dy = lat * math.cos(a) + fwd * math.sin(a), lat * math.sin(a) - fwd * math.cos(a)
    return {"x": round(min(98, max(2, pos["x"] + dx / MAP_BOX_PX[0] * 100)), 1),
            "y": round(min(98, max(2, pos["y"] + dy / MAP_BOX_PX[1] * 100)), 1)}


def _probe_size(src: Any) -> tuple[int, int] | None:
    if not isinstance(src, str) or "://" in src:
        return None  # поток: размер узнаем по первому кадру
    cap = cv2.VideoCapture(src)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return (w, h) if w and h else None


class Bridge:
    def __init__(self, cfg_path: str, backend: str | None = None):
        self.base_dir = Path(cfg_path).resolve().parent
        self.template = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
        self.cfg = self.template.pop("bridge")
        if backend:
            self.template.setdefault("models", {})["backend"] = backend
        self.api = SiteApi(os.environ.get("LINQ_SITE_URL", self.cfg["site_url"]),
                           os.environ.get("LINQ_INGEST_KEY", self.cfg.get("api_key", "dev-ingest-key")))
        self.public_url = self.cfg.get("public_url", f"http://127.0.0.1:{self.cfg.get('port', 8001)}").rstrip("/")
        self.sites: dict[int, SitePipeline] = {}
        self.structure: dict[int, str] = {}
        self.models: dict[int, ModelSet] = {}
        self.site_ids: dict[str, int] = {}   # id события ИИ -> id события на сайте
        self.reviewed: set[tuple[str, str]] = set()
        self.repeats: set[str] = set()   # события повторных проходов зацикленной записи
        # где в зацикленной записи уже были отправленные нарушения: (камера, правило) -> [(секунда ролика, x в кадре)]
        self.spots: dict[tuple[str, str], list[tuple[float, float]]] = {}
        self.cache = self.base_dir / self.template.get("events", {}).get("output_dir", "runs/site_bridge") / "videos"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    # ------------------------------------------------------------- источники
    def log(self, msg: str) -> None:
        print(time.strftime("%H:%M:%S"), msg, flush=True)

    def source_for(self, c: dict) -> tuple[Any, bool]:
        """(источник, живой ли): загруженный на сайт файл > демо-ролик по коду камеры > rtsp_url из БД."""
        url = (c.get("rtsp_url") or "").strip()
        if url.startswith("/uploads/"):
            dst = self.cache / os.path.basename(url)
            if not dst.exists():
                self.log(f"{c['code']}: скачиваю загруженное видео {url}")
                self.api.download(url, str(dst))
            return str(dst), False
        demo = self.demo(c).get("source")
        if demo:
            return str((self.base_dir / demo).resolve()), False
        if re.fullmatch(r"\d+", url):
            return int(url), True
        return url, "://" in url

    def demo(self, c: dict) -> dict:
        d = (self.cfg.get("sources") or {}).get(c["code"]) or {}
        return {"source": d} if isinstance(d, str) else d

    def _structure(self, cams: list[dict]) -> str:
        return json.dumps([(c["id"], c.get("rtsp_url"), self.demo(c)) for c in cams])

    # ------------------------------------------------------------- синхронизация с сайтом
    def sync(self) -> None:
        cams = [c for c in self.api.req("GET", "/ai/cameras") if c.get("is_active", True)]
        by_site: dict[int, list[dict]] = {}
        for c in cams:
            if not (c.get("rtsp_url") or "").strip() and not self.demo(c).get("source"):
                continue  # у камеры нет источника видео
            by_site.setdefault(c["site_id"], []).append(c)
        for sid in list(self.sites):
            if sid not in by_site:
                self.log(f"[участок {sid}] камер больше нет — останавливаю")
                self.sites.pop(sid).stop()
                self.structure.pop(sid, None)
        for sid, group in by_site.items():
            st = self._structure(group)
            if self.structure.get(sid) != st:
                if sid in self.sites:
                    self.log(f"[участок {sid}] камеры или источники изменились — перезапуск")
                    self.sites.pop(sid).stop()
                ids = {f"c{c['id']}" for c in group}   # новый источник — новая запись, прежние места не в счёт
                self.spots = {k: v for k, v in self.spots.items() if k[0] not in ids}
                sp = SitePipeline(self, sid, group)
                with self.lock:
                    self.sites[sid] = sp
                self.structure[sid] = st
                sp.start()
                self.log(f"[участок {sid}] запущен: {', '.join(c['code'] for c in group)}")
            else:
                for c in group:
                    self.sites[sid].update(c)

    def status(self) -> None:
        for sp in list(self.sites.values()):
            perf = sp.pipe.perf()
            prog = " + ".join(Path(m.spec).stem for m in sp.site.models.values())
            for c in sp.cams:
                cid = f"c{c['id']}"
                p, rt = perf["cameras"].get(cid, {}), sp.pipe.cams.get(cid)
                frame = None if rt is None or rt.frame_hw is None else [rt.frame_hw[1], rt.frame_hw[0]]
                body = {"fps": p.get("fps", 0), "latency_ms": p.get("proc_ms_mean"), "backend": sp.site.backend,
                        "program": f"{'LinQ TPU' if sp.site.backend == 'tpu' else 'ONNX CPU'}: {prog}",
                        "stream_url": f"{self.public_url}/stream/{c['id']}", "map_url": f"{self.public_url}/map/{sp.site_id}.png",
                        "plans_url": f"{self.public_url}/plans.json",
                        "frame": frame, "persons": p.get("persons", 0), "mapped": p.get("mapped", False),
                        "error": None if rt is not None and rt.last_pkt is not None else "нет кадров с источника"}
                try:
                    self.api.req("PUT", f"/ai/cameras/{c['id']}/status", body)
                except Exception as e:  # noqa: BLE001
                    self.log(f"статус {c['code']}: {e!r}")

    def sync_reviews(self) -> None:
        """«Подтвердить» / «Ложное» на сайте -> материалы события в набор для дообучения."""
        for e in self.api.req("GET", "/ai/events"):
            aid, st = e["ai_event_id"], {"confirmed": "confirmed", "false_alarm": "rejected"}.get(e["status"])
            if not st or (aid, st) in self.reviewed:
                continue
            for sp in list(self.sites.values()):
                if sp.pipe.store.get(aid):
                    sp.pipe.review(aid, st, e.get("description", ""), "site")
                    self.reviewed.add((aid, st))
                    self.log(f"событие {aid}: {st} оператором → review/{st}")

    # ------------------------------------------------------------- события
    def _is_repeat(self, sp: SitePipeline, ev: dict) -> bool:
        """Запись крутится по кругу: нарушение повторного прохода — то же самое, в журнал его не дублируем.

        Повтор — то же правило, то же место ролика (±3 с) и та же часть кадра, что у уже отправленного события.
        Сравниваем по месту, а не по номеру прохода: на медленном компьютере первый проход идёт с пропуском кадров,
        и пропущенное в нём нарушение должно попасть в журнал со второго прохода."""
        rt = sp.pipe.cams.get(ev["camera_id"])
        src = None if rt is None else rt.source
        dur = getattr(src, "duration", 0) or 0
        if not dur or not getattr(src, "loop", False):
            return False
        pos = (ev["start_ts"] - src.t0 - src.offset) % dur
        w = (sp.sizes.get(ev["camera_id"]) or (1280, 720))[0]
        fx = (ev["bbox"][0] + ev["bbox"][2]) / 2 / w if ev.get("bbox") else 0.5
        seen = self.spots.setdefault((ev["camera_id"], ev["rule"]), [])
        if getattr(src, "loops", 0) > 0 and any(
                min(abs(p - pos), dur - abs(p - pos)) < 3.0 and abs(x - fx) < 0.2 for p, x in seen):
            return True
        seen.append((pos, fx))
        return False

    def on_event(self, sp: SitePipeline, kind: str, ev: dict) -> None:
        if kind == "started" and self._is_repeat(sp, ev):
            self.repeats.add(ev["id"])
            return
        if kind in ("started", "ended") and ev["id"] not in self.repeats:
            threading.Thread(target=self._send, args=(sp, kind, ev), daemon=True).start()

    def _send(self, sp: SitePipeline, kind: str, ev: dict) -> None:
        out = sp.pipe.out_dir
        clip = os.path.join(out, ev["clip"]) if ev.get("clip") else None
        end = {"ended_at": _ts(ev.get("end_ts")), "duration_s": ev.get("duration_s"), "confidence": ev.get("confidence"),
               "zone": ", ".join(ev.get("zone_names") or []) or None}
        if clip and os.path.exists(clip):
            end.update(clip_b64=_b64(clip), clip_ext=os.path.splitext(clip)[1])
        rt = sp.pipe.cams.get(ev["camera_id"])
        if kind == "ended" and rt is not None and rt.mapping is not None:  # к концу карта уже построена
            end["ai_map_b64"] = self._map_png(sp)
        if kind == "ended":  # начало ещё отправляется — подождём его, чтобы не создать второе событие
            for _ in range(40):
                with self.lock:
                    if ev["id"] in self.site_ids:
                        break
                time.sleep(0.5)
        for attempt in range(3):
            try:
                with self.lock:
                    sid = self.site_ids.get(ev["id"])
                if kind == "ended" and sid is not None:
                    self.api.req("PATCH", f"/events/{sid}/ai", end, timeout=60)
                    self.log(f"→ сайт: событие #{sid} завершено ({ev.get('duration_s')} с, клип {'есть' if clip else 'нет'})")
                    return
                body = self._started_body(sp, ev)
                if kind == "ended":
                    body.update(end)
                r = self.api.req("POST", "/events", body, timeout=60)
                with self.lock:
                    self.site_ids[ev["id"]] = r["id"]
                self.log(f"→ сайт: событие #{r['id']} {r['violation_title']} ({r['camera_code']})")
                return
            except Exception as e:  # noqa: BLE001
                self.log(f"отправка события {ev['id']} ({kind}): {e!r}")
                time.sleep(1 + attempt * 2)

    def _started_body(self, sp: SitePipeline, ev: dict) -> dict:
        cam_id = int(ev["camera_id"][1:])
        cam = next((c for c in sp.cams if c["id"] == cam_id), {})
        w, h = sp.sizes.get(ev["camera_id"]) or (1280, 720)
        ai_pos = plan_pos(cam, None, None)
        if ev.get("bbox"):
            # fx, fy — где в кадре нарушение (%, у человека — точка ног, у огня — центр очага): по ним сайт строит
            # тепловую карту кадра; x, y — та же точка на карте цеха, в луче обзора камеры
            x1, y1, x2, y2 = ev["bbox"]
            fx = min(100.0, max(0.0, (x1 + x2) / 2 / w * 100))
            fy = min(100.0, max(0.0, ((y1 + y2) / 2 if ev["rule"] == "fire" else y2) / h * 100))
            ai_pos = {**plan_pos(cam, fx, fy), "fx": round(fx, 1), "fy": round(fy, 1)}
            rt = sp.pipe.cams.get(ev["camera_id"])
            pt = [[fx / 100 * w, fy / 100 * h]]
            if rt is not None and rt.local is not None and rt.local.valid_image_points(pt)[0]:
                # та же точка на полу в метрах от камеры (X — вправо, Y — вперёд): так сайт ставит её
                # на ИИ-карту камеры на плане цеха
                ai_pos["lx"], ai_pos["ly"] = (round(float(v), 2) for v in rt.local.to_map(pt)[0])
        who = [m.group(1) for t in ev.get("track_ids") or [] if (m := re.search(r"p(\d+)$", str(t)))]
        desc = f"ИИ: {ev['title']}" + (f", человек ID {who[-1]}" if who else "")
        if ev.get("zone_names"):
            desc += f", зона «{', '.join(ev['zone_names'])}»"
        return {"camera_id": cam_id, "violation": RULE_TO_SITE[ev["rule"]], "confidence": ev.get("confidence", 0.9),
                "severity": "critical" if ev.get("severity") == "critical" else "warning",
                "timestamp": _ts(ev["start_ts"]), "description": desc, "ai_pos": ai_pos, "ai_event_id": ev["id"],
                "zone": ", ".join(ev.get("zone_names") or []) or None,
                "frame_b64": _b64(os.path.join(sp.pipe.out_dir, ev["snapshot"]) if ev.get("snapshot") else None),
                "ai_map_b64": self._map_png(sp)}

    @staticmethod
    def _map_png(sp: SitePipeline) -> str | None:
        try:
            ok, buf = cv2.imencode(".png", sp.pipe.minimap(long_side=720))
            return base64.b64encode(buf.tobytes()).decode() if ok else None
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------- видео для браузера
    def pipeline_of(self, cam_id: int) -> SitePipeline | None:
        for sp in list(self.sites.values()):
            if f"c{cam_id}" in sp.pipe.cams:
                return sp
        return None

    def app(self):
        from fastapi import FastAPI, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import Response, StreamingResponse

        app = FastAPI(title="LinQ SafetyVision — мост с сайтом")
        app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

        def view(cam_id: int):
            sp = self.pipeline_of(cam_id)
            rt = None if sp is None else sp.pipe.cams.get(f"c{cam_id}")
            if rt is None or rt.last_pkt is None:
                return None
            # зоны сайт рисует сам поверх видео (их можно двигать мышкой), поэтому в кадре их нет
            return draw_camera(rt.last_pkt.frame, {**rt.last_state, "zones": []})

        @app.get("/health")
        def health():
            return {"sites": {sid: [c["code"] for c in sp.cams] for sid, sp in self.sites.items()}}

        @app.get("/frame/{cam_id}.jpg")
        def frame(cam_id: int):
            img = view(cam_id)
            if img is None:
                raise HTTPException(404, "кадра ещё нет")
            return Response(cv2.imencode(".jpg", img)[1].tobytes(), media_type="image/jpeg")

        @app.get("/stream/{cam_id}")
        def stream(cam_id: int, fps: float = 10.0):
            def gen():
                last = None
                while True:
                    sp = self.pipeline_of(cam_id)
                    rt = None if sp is None else sp.pipe.cams.get(f"c{cam_id}")
                    if rt is not None and rt.last_pkt is not None and rt.last_pkt is not last:
                        last = rt.last_pkt
                        img = view(cam_id)
                        if img is not None:
                            jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])[1].tobytes()
                            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                    time.sleep(1.0 / fps)

            return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

        @app.get("/map/{site_id}.png")
        def map_png(site_id: int):
            sp = self.sites.get(site_id)
            if sp is None:
                raise HTTPException(404)
            return Response(cv2.imencode(".png", sp.pipe.minimap())[1].tobytes(), media_type="image/png")

        @app.get("/plans.json")
        def plans():
            """ИИ-карта каждой камеры для плана цеха на сайте: ключ — id камеры на сайте, метры от камеры."""
            out = {}
            for sp in list(self.sites.values()):
                for cid in list(sp.pipe.cams):
                    try:
                        out[cid[1:]] = sp.pipe.camera_floor(cid)
                    except Exception as e:  # noqa: BLE001 — кадр обновился посреди чтения; карта придёт со следующим опросом
                        out[cid[1:]] = {"mapped": False, "error": repr(e)}
            return out

        return app

    # ------------------------------------------------------------- главный цикл
    def run(self) -> None:
        import uvicorn

        port = int(self.cfg.get("port", 8001))
        threading.Thread(target=lambda: uvicorn.run(self.app(), host=self.cfg.get("host", "0.0.0.0"), port=port,
                                                    log_level="warning"), daemon=True).start()
        self.log(f"мост: сайт {self.api.url}, видео для браузера {self.public_url}/stream/<id камеры>")
        poll = float(self.cfg.get("poll_s", 2))
        last_status = last_review = 0.0
        while True:
            try:
                self.sync()
                now = time.time()
                if now - last_status >= 3:
                    self.status()
                    last_status = now
                if now - last_review >= 10:
                    self.sync_reviews()
                    last_review = now
            except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
                self.log(f"сайт недоступен ({e}); повтор через {poll:.0f} с")
            except Exception as e:  # noqa: BLE001
                self.log(f"ошибка синхронизации: {e!r}")
            time.sleep(poll)
