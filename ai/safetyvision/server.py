"""HTTP API для веб-интерфейса и БД команды.

Запуск: python -m safetyvision serve configs/demo.yaml --port 8000   (документация: /docs)

Основное:
  GET  /api/rules                         каталог правил (индекс = позиция в векторе)
  GET  /api/config                        камеры, зоны, карта, правила
  PUT  /api/cameras/{id}/rules            {"rules": [0,1,0,...]} | {"rules": {"helmet":1}}
  POST /api/cameras/{id}/calibration      {"image_points": [[u,v]...], "map_points": [[x,y]...]}
  POST /api/zones / DELETE /api/zones/{id} зоны на карте (метры) или на кадре (polygon_px + camera)
  GET  /api/events?rule=&camera=&zone=&status=&since=&until=   журнал событий
  POST /api/events/{id}/review            {"status": "confirmed"|"rejected", "comment": ""}
  GET  /api/stats, /api/perf              статистика нарушений, FPS и задержки
  GET  /api/map                           люди/техника/зоны/камеры/слепые зоны в метрах
  GET  /api/map.png, /api/cameras/{id}/frame.jpg, /api/cameras/{id}/stream (MJPEG)
  WS   /ws/events                         поток событий started/ended/... в реальном времени
  GET  /media/...                         снимки и клипы событий
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import cv2
from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .catalog import catalog_as_json, parse_rules, rules_to_vector
from .config import SiteConfig
from .pipeline import Pipeline


def _jpeg(img, q: int = 80) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    return buf.tobytes()


def create_app(site: SiteConfig, autostart: bool = True) -> FastAPI:
    app = FastAPI(title="LinQ SafetyVision API", version="0.1.0",
                  description="Контроль нарушений промышленной безопасности по видео на ускорителях LinQ")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    pipe = Pipeline(site)
    app.state.pipe = pipe
    app.mount("/media", StaticFiles(directory=pipe.out_dir), name="media")
    clients: set[tuple[WebSocket, asyncio.Queue]] = set()
    loop_holder: dict[str, Any] = {}

    def broadcast(kind: str, event: dict[str, Any]) -> None:
        loop = loop_holder.get("loop")
        if loop is None:
            return
        for _, q in list(clients):
            loop.call_soon_threadsafe(q.put_nowait, {"kind": kind, "event": event})

    pipe.store.listeners.append(broadcast)

    @app.on_event("startup")
    async def _startup():
        loop_holder["loop"] = asyncio.get_running_loop()
        if autostart:
            threading.Thread(target=pipe.run, daemon=True, name="pipeline").start()

    @app.on_event("shutdown")
    async def _shutdown():
        pipe.stop()

    # ------------------------------------------------------------ правила и конфигурация
    @app.get("/api/rules")
    def rules():
        return catalog_as_json()

    @app.get("/api/config")
    def config():
        d = site.to_dict()
        for c in d["cameras"]:
            cam = site.camera(c["id"])
            eff = site.effective_rules(cam.id, [])
            c["rules_vector"] = rules_to_vector({k for k, v in eff.items() if v})
        return d

    @app.put("/api/cameras/{cam_id}/rules")
    def set_rules(cam_id: str, body: dict = Body(...)):
        try:
            site.camera(cam_id)
            rules = parse_rules(body.get("rules"))
        except KeyError:
            raise HTTPException(404, "камера не найдена")
        except (ValueError, TypeError) as e:
            raise HTTPException(400, str(e))
        pipe.set_camera_rules(cam_id, rules)
        eff = site.effective_rules(cam_id, [])
        return {"camera": cam_id, "rules": rules, "effective_vector": rules_to_vector({k for k, v in eff.items() if v})}

    @app.post("/api/cameras/{cam_id}/calibration")
    def calibrate(cam_id: str, body: dict = Body(...)):
        if cam_id not in pipe.cams:
            raise HTTPException(404, "камера не найдена")
        try:
            return pipe.set_calibration(cam_id, body["image_points"], body["map_points"])
        except (KeyError, ValueError) as e:
            raise HTTPException(400, str(e))

    @app.get("/api/zones")
    def zones():
        return site.to_dict()["zones"]

    @app.post("/api/zones")
    def upsert_zone(body: dict = Body(...)):
        try:
            z = pipe.upsert_zone(body)
        except (KeyError, ValueError, TypeError) as e:
            raise HTTPException(400, f"неверная зона: {e}")
        return {k: v for k, v in vars(z).items() if v not in (None, [], {})}

    @app.delete("/api/zones/{zone_id}")
    def delete_zone(zone_id: str):
        if not pipe.delete_zone(zone_id):
            raise HTTPException(404, "зона не найдена")
        return {"deleted": zone_id}

    # ------------------------------------------------------------ события
    @app.get("/api/events")
    def events(rule: str | None = None, camera: str | None = None, zone: str | None = None,
               status: str | None = None, review: str | None = None, since: float | None = None,
               until: float | None = None, limit: int = 200, offset: int = 0):
        return pipe.store.query(rule, camera, zone, status, review, since, until, limit, offset)

    @app.get("/api/events/{event_id}")
    def event(event_id: str):
        e = pipe.store.get(event_id)
        if e is None:
            raise HTTPException(404, "событие не найдено")
        return e

    @app.post("/api/events/{event_id}/review")
    def review(event_id: str, body: dict = Body(...)):
        st = body.get("status")
        if st not in ("confirmed", "rejected"):
            raise HTTPException(400, "status: confirmed | rejected")
        try:
            return pipe.review(event_id, st, body.get("comment", ""), body.get("user"))
        except KeyError:
            raise HTTPException(404, "событие не найдено")

    @app.get("/api/stats")
    def stats(since: float | None = None):
        return pipe.store.stats(since)

    @app.get("/api/perf")
    def perf():
        return pipe.perf()

    # ------------------------------------------------------------ карта и видео
    @app.get("/api/map")
    def map_state():
        return pipe.map_state()

    @app.get("/api/map.png")
    def map_png():
        ok, buf = cv2.imencode(".png", pipe.minimap())
        return Response(buf.tobytes(), media_type="image/png")

    @app.get("/api/cameras/{cam_id}/frame.jpg")
    def frame(cam_id: str, raw: bool = False):
        cam = pipe.cams.get(cam_id)
        if cam is None or cam.last_pkt is None:
            raise HTTPException(404, "кадра ещё нет")
        img = cam.last_pkt.frame if raw else pipe.camera_view(cam_id)
        return Response(_jpeg(img), media_type="image/jpeg")

    @app.get("/api/cameras/{cam_id}/stream")
    def stream(cam_id: str, fps: float = 8.0):
        if cam_id not in pipe.cams:
            raise HTTPException(404, "камера не найдена")

        def gen():
            last = None
            while True:
                cam = pipe.cams[cam_id]
                if cam.last_pkt is not None and cam.last_pkt is not last:
                    last = cam.last_pkt
                    img = pipe.camera_view(cam_id)
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + _jpeg(img, 70) + b"\r\n"
                time.sleep(1.0 / fps)

        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket):
        await ws.accept()
        q: asyncio.Queue = asyncio.Queue()
        item = (ws, q)
        clients.add(item)
        try:
            while True:
                msg = await q.get()
                await ws.send_json(msg)
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(item)

    @app.get("/", response_class=HTMLResponse)
    def index():
        cams = "".join(f'<div class="cam"><h3>{c.name or c.id}</h3><img src="/api/cameras/{c.id}/stream"></div>'
                       for c in site.cameras)
        return f"""<!doctype html><html><head><meta charset="utf-8"><title>LinQ SafetyVision</title>
<style>body{{font-family:system-ui;margin:12px;background:#111;color:#eee}} .row{{display:flex;gap:12px;flex-wrap:wrap}}
.cam img{{max-width:640px;width:100%}} #map{{max-width:520px;background:#fff}} #ev div{{padding:4px;border-bottom:1px solid #333}}
.started{{color:#ff6b6b}} .ended{{color:#9be59b}} a{{color:#8ab4ff}}</style></head><body>
<h2>LinQ SafetyVision — отладочный просмотр (основной интерфейс делает веб-команда)</h2>
<div class="row">{cams}<div><h3>Миникарта</h3><img id="map" src="/api/map.png"></div></div>
<h3>События</h3><div id="ev"></div>
<script>
setInterval(()=>{{document.getElementById('map').src='/api/map.png?'+Date.now()}},1000);
const ev=document.getElementById('ev');
function row(m){{const e=m.event;const d=document.createElement('div');d.className=m.kind;
d.innerHTML=`<b>${{m.kind}}</b> [${{e.camera_id}}] ${{e.title}} — ${{e.subject}} с ${{e.start_time}} по ${{e.end_time||'…'}}
 ${{e.snapshot?`<a href="/media/${{e.snapshot}}" target=_blank>кадр</a>`:''}} ${{e.clip?`<a href="/media/${{e.clip}}" target=_blank>клип</a>`:''}}`;
ev.prepend(d)}}
fetch('/api/events?limit=50').then(r=>r.json()).then(a=>a.reverse().forEach(e=>row({{kind:e.status,event:e}})));
const ws=new WebSocket((location.protocol=='https:'?'wss://':'ws://')+location.host+'/ws/events');ws.onmessage=m=>row(JSON.parse(m.data));
</script></body></html>"""

    return app
