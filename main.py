import base64, hashlib, io, json, os, secrets, time, zipfile
from collections import Counter
from datetime import datetime
from typing import Literal, Optional
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import db

VIEW_ROLES = {1, 2, 3, 7}     # мониторинг, аналитика, карта
MANAGE_ROLES = {1, 7}         # участки, камеры, правила, зоны, пользователи (canEditRules на фронте)
PROCESS_ROLES = {1, 2, 3}     # реакция на события
INGEST_KEY = os.environ.get("INGEST_KEY", "dev-ingest-key")   # ключ AI-сервиса для POST /events
SEED_PASSWORD = os.environ.get("SEED_PASSWORD", "linq123")    # пароль демо-пользователей

# 8 паттернов; индекс = позиция в cameras.rulesVector
VIOLATIONS = [("RUNNING", "01", "Бег по цеху / резкие перемещения"), ("DANGER_PROXIMITY", "02", "Опасное сближение с техникой"),
              ("PHONE_USAGE", "03", "Использование мобильного телефона"), ("SMOKING_FIRE", "04", "Курение / открытый огонь"),
              ("FENCE_CLIMBING", "05", "Перелезание через ограждения"), ("NO_HARNESS_HEIGHT", "06", "Работа на высоте без страховки"),
              ("PERSON_FALL", "07", "Падение человека / неподвижность"), ("CARGO_VIOLATION", "08", "Переноска груза с нарушением правил"),
              # СИЗ и опасные зоны — то, что ИИ-модуль (safetyvision) распознаёт; новые типы только в конец, старые векторы остаются валидными
              ("NO_HELMET", "09", "Нет защитной каски"), ("NO_VEST", "10", "Нет спецодежды (сигнальный жилет)"),
              ("DANGER_ZONE", "11", "Нахождение в опасной зоне"), ("NO_GLOVES", "12", "Нет перчаток"),
              ("NO_GOGGLES", "13", "Нет защитных очков / щитка")]
VIOL = {v[0]: v for v in VIOLATIONS}
AI_SUPPORTED = {"RUNNING", "DANGER_PROXIMITY", "PHONE_USAGE", "SMOKING_FIRE", "PERSON_FALL", "NO_HELMET", "NO_VEST",
                "DANGER_ZONE", "NO_GLOVES", "NO_GOGGLES"}   # для остальных у ИИ пока нет детектора
NEW_DEFAULTS = [1, 1, 1, 0, 0]   # значения позиций 09–13 для камер, созданных до их появления
Status = Literal["new", "sent_to_master", "confirmed", "false_alarm"]
AI_STALE_S = 15   # ИИ-модуль присылает статус камер каждые ~3 с; дольше тишины — «не в сети»
AI_STATUS: dict[int, dict] = {}

os.makedirs("uploads/videos", exist_ok=True)
app = FastAPI(title="LinQ backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
now = lambda: datetime.now().astimezone().isoformat(sep=" ", timespec="seconds")   # с поясом: БД не гадает


def pw_hash(pw):  # "salt$hash" в одной колонке password_hash (PBKDF2; при желании заменить на bcrypt здесь и в pw_check)
    salt = secrets.token_hex(16)
    return f"{salt}${hashlib.pbkdf2_hmac('sha256', pw.encode(), bytes.fromhex(salt), 100_000).hex()}"


def pw_check(pw, stored):
    salt, h = stored.split("$")
    return secrets.compare_digest(hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 100_000).hex(), h)


def make_user(login, pw, role_id, full_name):
    return db.user_create({"login": login, "password_hash": pw_hash(pw), "role_id": role_id,
                           "full_name": full_name, "is_active": True})


def user(authorization: str = Header(None)):
    u = db.user_by_session((authorization or "").removeprefix("Bearer "))
    if not u:
        raise HTTPException(401, "Не авторизован")
    return u


def need(roles):  # проверка доступа
    def dep(u=Depends(user)):
        if u["role_id"] not in roles:
            raise HTTPException(403, "Недостаточно прав")
        return u
    return dep


view, manage, process = need(VIEW_ROLES), need(MANAGE_ROLES), need(PROCESS_ROLES)


# ---------- сериализация под фронтенд ----------
def user_out(u):
    return {"id": u["id"], "login": u["login"], "full_name": u["full_name"], "role_id": u["role_id"],
            "role_name": f"Роль {u['role_id']}: {u['role_name']}", "position": u["role_name"], "canEditRules": u["role_id"] in MANAGE_ROLES,
            "is_active": bool(u["is_active"])}


def full_vector(vec):  # вектор правил всегда длины len(VIOLATIONS)
    vec = [int(bool(x)) for x in (vec or [])][:len(VIOLATIONS)]
    vec += [0] * (8 - len(vec))
    return vec + NEW_DEFAULTS[len(vec) - 8:]


def cam_out(c):
    extra = c.get("extra") or {}
    ai = AI_STATUS.get(c["id"], {})
    online = bool(ai) and time.time() - ai.get("updated", 0) < AI_STALE_S
    return {"id": c["id"], "code": c["code"], "site_id": c["site_id"], "site_name": c["site_name"], "name": c["name"],
            "cameraType": c["camera_type"], "panAngle": c["pan_angle"], "zoomLevel": c["zoom_level"],
            "autoPatrol": bool(c["auto_patrol"]), "rtsp_url": c["rtsp_url"], "is_active": bool(c["is_active"]),
            "created_at": c["created_at"], "rulesVector": full_vector(c["rules_vector"]), "mapPos": c["map_pos"],
            "zones": c["zones"] or [], "tiltAngle": 0, "workers": [], **extra,
            # метрики присылает ИИ-модуль (PUT /ai/cameras/{id}/status); пока его нет — нули, а не выдуманные цифры
            "fps": round(ai.get("fps", 0), 1) if online else 0,
            "latency": f"{ai['latency_ms']:.0f} мс" if online and ai.get("latency_ms") is not None else "—",
            "tpuProgram": ai.get("program") or extra.get("tpuProgram") or "—",
            "ai": {**ai, "online": online}}


def ev_out(e):
    v = VIOL[e["violation"]]
    return {"id": e["id"], "camera_id": e["camera_id"], "camera_code": e["camera_code"], "site_name": e["site_name"],
            "violation": v[0], "violation_title": v[2], "pattern_code": v[1], "timestamp": e["timestamp"][11:19],
            "date": e["timestamp"][:10], "end_time": e["ended_at"][11:19] if e.get("ended_at") else None,
            "duration_s": e.get("duration_s"), "clip_url": e.get("clip_url"), "zone": e.get("zone") or "",
            "ai_event_id": e.get("ai_event_id"),
            "created_at": e["created_at"], "frame_url": e["frame_url"], "ai_map_url": e["ai_map_url"], "ai_pos": e["ai_pos"],
            "status": e["status"], "processed_by_id": e["processed_by_id"],
            "processed_by_name": e["processed_by_name"] or "Ожидает реакции",
            "processed_at": e["processed_at"][11:19] if e["processed_at"] else None,
            "confidence": e["confidence"], "description": e["description"] or "", "severity": e["severity"]}


# ---------- авторизация и пользователи ----------
class Creds(BaseModel):
    login: str
    password: str


@app.post("/auth/login")
def login(c: Creds):
    u = db.user_by_login(c.login)
    if not u or not u["is_active"] or not pw_check(c.password, u["password_hash"]):
        raise HTTPException(401, "Неверный логин или пароль")
    tok = secrets.token_urlsafe(32)
    db.session_create(tok, u["id"])
    return {"token": tok, "user": user_out(u)}


@app.get("/me")
def me(u=Depends(user)): return user_out(u)


@app.get("/roles")
def roles(_=Depends(view)): return db.roles_list()


@app.get("/users")
def users(_=Depends(manage)): return [user_out(u) for u in db.users_list()]


class UserIn(BaseModel):
    login: str
    password: str
    role_id: int
    full_name: str


@app.post("/users")
def add_user(b: UserIn, _=Depends(manage)):
    if db.user_by_login(b.login):
        raise HTTPException(409, "Логин занят")
    if b.role_id not in {r["id"] for r in db.roles_list()}:
        raise HTTPException(422, "Нет такой роли")
    return {"id": make_user(b.login, b.password, b.role_id, b.full_name)}


class UserPatch(BaseModel):
    role_id: Optional[int] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


@app.patch("/users/{uid}")
def patch_user(uid: int, b: UserPatch, _=Depends(manage)):
    d = b.model_dump(exclude_unset=True)
    if "password" in d:
        d["password_hash"] = pw_hash(d.pop("password"))
    db.user_update(uid, d)
    return user_out(db.user_get(uid))


# ---------- справочники и настройки ----------
@app.get("/violation-types")
def violation_types(_=Depends(view)):
    return [{"id": i, "code": v[1], "enumKey": v[0], "name": v[2], "ai": v[0] in AI_SUPPORTED} for i, v in enumerate(VIOLATIONS)]


@app.get("/settings")  # sirenEnabled, skudLockEnabled, enhanceFilter, stabilizeZonesOnPTZ
def get_settings(_=Depends(view)): return db.settings_get()


@app.put("/settings")
def put_settings(b: dict, _=Depends(manage)):
    db.settings_set(b)
    return db.settings_get()


# ---------- участки ----------
class SiteIn(BaseModel):
    name: Optional[str] = None
    rules: Optional[dict | list] = None


@app.get("/sites")
def sites(_=Depends(view)): return db.sites_list()


@app.post("/sites")
def add_site(b: SiteIn, _=Depends(manage)):
    return {"id": db.site_create(b.name, b.rules)}


@app.patch("/sites/{sid}")
def patch_site(sid: int, b: SiteIn, _=Depends(manage)):
    db.site_update(sid, b.model_dump(exclude_unset=True))
    return db.site_get(sid)


# ---------- камеры ----------
CAM_COLS = {"name": "name", "cameraType": "camera_type", "panAngle": "pan_angle", "zoomLevel": "zoom_level",
            "autoPatrol": "auto_patrol", "rtsp_url": "rtsp_url", "is_active": "is_active", "rulesVector": "rules_vector",
            "mapPos": "map_pos", "zones": "zones", "site_id": "site_id"}
EXTRA_KEYS = ("tiltAngle", "tpuProgram", "workers")   # нет колонок в схеме — хранятся в cameras.extra (jsonb)
PTZ_KEYS = {"panAngle", "tiltAngle", "zoomLevel", "autoPatrol"}   # управление PTZ доступно всем, кто видит камеры


class CameraIn(BaseModel):
    name: str
    site_id: Optional[int] = None
    site_name: Optional[str] = None            # если участка нет — создаётся
    cameraType: Literal["static", "dynamic"] = "dynamic"
    rtsp_url: Optional[str] = None
    is_active: bool = True
    rulesVector: list[int] = [0, 1, 1, 0, 1, 0, 1, 0] + NEW_DEFAULTS
    mapPos: dict = {"x": 50, "y": 50}
    zones: list[dict] = []
    tiltAngle: float = 0
    tpuProgram: Optional[str] = None
    workers: list[dict] = []


@app.get("/cameras")
def cameras(_=Depends(view)): return [cam_out(c) for c in db.cameras_list()]


@app.get("/cameras/{cid}")
def camera(cid: int, _=Depends(view)):
    c = db.camera_get(cid)
    if not c:
        raise HTTPException(404)
    return cam_out(c)


@app.post("/cameras")
def add_camera(b: CameraIn, _=Depends(manage)):
    site = db.site_get(b.site_id) if b.site_id else (b.site_name and (db.site_by_name(b.site_name) or
           db.site_get(db.site_create(b.site_name, None))))
    if not site:
        raise HTTPException(422, "Укажите site_id или site_name")
    cid = db.camera_create({"code": "", "site_id": site["id"], "name": b.name, "camera_type": b.cameraType,
                            "rtsp_url": b.rtsp_url, "is_active": b.is_active, "rules_vector": full_vector(b.rulesVector),
                            "map_pos": b.mapPos, "zones": b.zones,
                            "extra": {k: getattr(b, k) for k in EXTRA_KEYS if getattr(b, k) is not None}})
    db.camera_update(cid, {"code": f"CAM-{cid:02d}"})
    return cam_out(db.camera_get(cid))


class CameraPatch(BaseModel):
    name: Optional[str] = None
    site_id: Optional[int] = None
    cameraType: Optional[Literal["static", "dynamic"]] = None
    panAngle: Optional[float] = None
    zoomLevel: Optional[float] = None
    autoPatrol: Optional[bool] = None
    rtsp_url: Optional[str] = None
    is_active: Optional[bool] = None
    rulesVector: Optional[list[int]] = None
    mapPos: Optional[dict] = None
    zones: Optional[list[dict]] = None
    tiltAngle: Optional[float] = None
    tpuProgram: Optional[str] = None
    workers: Optional[list[dict]] = None


@app.patch("/cameras/{cid}")  # частичное обновление: правила, зоны, позиция на карте, PTZ
def patch_camera(cid: int, b: CameraPatch, u=Depends(view)):
    d = b.model_dump(exclude_unset=True)
    if not set(d) <= PTZ_KEYS and u["role_id"] not in MANAGE_ROLES:
        raise HTTPException(403, "Недостаточно прав")
    cam = db.camera_get(cid)
    if not cam:
        raise HTTPException(404)
    upd = {CAM_COLS[k]: v for k, v in d.items() if k in CAM_COLS}
    if "rules_vector" in upd:
        upd["rules_vector"] = full_vector(upd["rules_vector"])
    ex = {k: d[k] for k in EXTRA_KEYS if k in d}
    if ex:
        upd["extra"] = {**(cam.get("extra") or {}), **ex}
    db.camera_update(cid, upd)
    return cam_out(db.camera_get(cid))


@app.delete("/cameras/{cid}")
def del_camera(cid: int, _=Depends(manage)):
    db.camera_delete(cid)
    return {"ok": True}


VIDEO_EXT = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".mpg", ".m4v"}


@app.put("/cameras/{cid}/video")  # видеофайл вместо потока: тело запроса — сам файл, имя — в X-Filename
async def upload_video(cid: int, request: Request, x_filename: str = Header("video.mp4"), _=Depends(manage)):
    if not db.camera_get(cid):
        raise HTTPException(404)
    ext = os.path.splitext(x_filename)[1].lower()
    if ext not in VIDEO_EXT:
        raise HTTPException(422, f"Формат {ext or '?'} не поддерживается")
    name = f"videos/cam{cid}_{secrets.token_hex(6)}{ext}"
    with open(os.path.join("uploads", name), "wb") as f:
        async for chunk in request.stream():
            f.write(chunk)
    db.camera_update(cid, {"rtsp_url": f"/uploads/{name}"})   # ИИ-модуль скачает файл и начнёт его анализ
    return cam_out(db.camera_get(cid))


# ---------- ИИ-модуль (safetyvision): камеры, статус, события; доступ по X-Api-Key ----------
def service(x_api_key: str = Header(None)):
    if not (x_api_key and secrets.compare_digest(x_api_key, INGEST_KEY)):
        raise HTTPException(401, "Нужен X-Api-Key ИИ-модуля")


@app.get("/ai/cameras")
def ai_cameras(_=Depends(service)): return [cam_out(c) for c in db.cameras_list()]


@app.put("/ai/cameras/{cid}/status")  # {fps, latency_ms, backend, program, stream_url, frame: [w, h], error}
def ai_status(cid: int, b: dict, _=Depends(service)):
    if not db.camera_get(cid):
        raise HTTPException(404)
    AI_STATUS[cid] = {**b, "updated": time.time()}   # живое состояние, в БД не пишется
    return {"ok": True}


@app.get("/ai/events")  # статусы обработки — ИИ-модуль складывает ложные срабатывания в набор для дообучения
def ai_events(status: Optional[Status] = None, limit: int = 500, _=Depends(service)):
    return [{"id": e["id"], "ai_event_id": e["ai_event_id"], "status": e["status"], "description": e["description"] or ""}
            for e in db.events_list(status, None, 0, limit) if e.get("ai_event_id")]


# ---------- события ----------
def save_b64(data, prefix, ext=".jpg"):
    name = f"{prefix}_{secrets.token_hex(8)}{ext}"
    with open(os.path.join("uploads", name), "wb") as f:
        f.write(base64.b64decode(data))
    return f"/uploads/{name}"


class EventIn(BaseModel):
    camera_id: int
    violation: str
    confidence: float = 0.95
    description: str = ""
    severity: Optional[Literal["critical", "warning"]] = None
    frame_url: Optional[str] = None
    ai_map_url: Optional[str] = None
    frame_b64: Optional[str] = None      # либо ссылка, либо base64
    ai_map_b64: Optional[str] = None
    ai_pos: Optional[dict] = None        # {x, y} в процентах на карте
    timestamp: Optional[str] = None      # время нарушения "YYYY-MM-DD HH:MM:SS[+03:00]"; по умолчанию — сейчас
    ended_at: Optional[str] = None       # конец нарушения (ИИ присылает его позже через PATCH /events/{id}/ai)
    duration_s: Optional[float] = None
    clip_url: Optional[str] = None
    clip_b64: Optional[str] = None
    clip_ext: str = ".mp4"
    zone: Optional[str] = None           # названия зон через запятую
    ai_event_id: Optional[str] = None    # id события в ИИ-модуле


def ingest(x_api_key: str = Header(None), authorization: str = Header(None)):
    if x_api_key and secrets.compare_digest(x_api_key, INGEST_KEY):   # AI-сервис
        return
    view(user(authorization))                                         # либо залогиненный пользователь (кнопка симуляции инцидента)


@app.post("/events")  # фиксация нарушения AI-сервисом
def add_event(b: EventIn, _=Depends(ingest)):
    if b.violation not in VIOL or not db.camera_get(b.camera_id):
        raise HTTPException(422, "Неверный violation или camera_id")
    if b.ai_event_id and (old := db.event_by_ai_id(b.ai_event_id)):   # повтор отправки после сбоя сети
        return ev_out(old)
    eid = db.event_create({
        "camera_id": b.camera_id, "violation": b.violation, "confidence": b.confidence, "description": b.description,
        "severity": b.severity or ("critical" if b.violation == "PERSON_FALL" else "warning"),
        "frame_url": save_b64(b.frame_b64, "frame") if b.frame_b64 else b.frame_url,
        "ai_map_url": save_b64(b.ai_map_b64, "map", ".png") if b.ai_map_b64 else b.ai_map_url,
        "ai_pos": b.ai_pos, "status": "new", "timestamp": b.timestamp or now(),
        "ended_at": b.ended_at, "duration_s": b.duration_s, "zone": b.zone, "ai_event_id": b.ai_event_id,
        "clip_url": save_b64(b.clip_b64, "clip", b.clip_ext) if b.clip_b64 else b.clip_url})
    return ev_out(db.event_get(eid))


class EventAI(BaseModel):   # завершение события: конец, длительность, клип
    ended_at: Optional[str] = None
    duration_s: Optional[float] = None
    confidence: Optional[float] = None
    clip_url: Optional[str] = None
    clip_b64: Optional[str] = None
    clip_ext: str = ".mp4"
    zone: Optional[str] = None
    ai_map_b64: Optional[str] = None     # миникарта на момент конца (к началу карта могла ещё строиться)


@app.patch("/events/{eid}/ai")
def finish_event(eid: int, b: EventAI, _=Depends(service)):
    if not db.event_get(eid):
        raise HTTPException(404)
    d = b.model_dump(exclude_unset=True, exclude={"clip_b64", "clip_ext", "ai_map_b64"})
    if b.clip_b64:
        d["clip_url"] = save_b64(b.clip_b64, "clip", b.clip_ext)
    if b.ai_map_b64:
        d["ai_map_url"] = save_b64(b.ai_map_b64, "map", ".png")
    db.event_update(eid, d)
    return ev_out(db.event_get(eid))


@app.get("/events")  # since_id — опрос новых событий для оповещений
def events(status: Optional[Status] = None, camera_id: Optional[int] = None, since_id: int = 0, limit: int = 200,
           _=Depends(view)):
    return [ev_out(e) for e in db.events_list(status, camera_id, since_id, limit)]


@app.get("/events/{eid}")
def event(eid: int, _=Depends(view)):
    e = db.event_get(eid)
    if not e:
        raise HTTPException(404)
    return ev_out(e)


class Process(BaseModel):
    status: Status


@app.patch("/events/{eid}/process")  # confirmed / sent_to_master / false_alarm
def process_event(eid: int, b: Process, u=Depends(process)):
    if not db.event_get(eid):
        raise HTTPException(404)
    db.event_update(eid, {"status": b.status, "processed_by_id": u["id"], "processed_at": now()})
    return ev_out(db.event_get(eid))


class Comment(BaseModel):
    description: str


@app.patch("/events/{eid}/comment")
def comment_event(eid: int, b: Comment, _=Depends(process)):
    if not db.event_get(eid):
        raise HTTPException(404)
    db.event_update(eid, {"description": b.description})
    return ev_out(db.event_get(eid))


@app.get("/training/false-alarms.zip")  # выборка для дообучения: кадры и клипы событий, отмеченных «Ложное»
def false_alarms_zip(_=Depends(view)):
    buf = io.BytesIO()
    evs = db.events_list("false_alarm", None, 0, 10000)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for e in evs:
            o = ev_out(e)
            base = f"{o['violation']}/event_{o['id']}"
            z.writestr(base + ".json", json.dumps(o, ensure_ascii=False, indent=2))
            for key in ("frame_url", "clip_url"):
                p = (o.get(key) or "").lstrip("/")
                if p.startswith("uploads/") and os.path.exists(p):
                    z.write(p, base + os.path.splitext(p)[1] if key == "frame_url" else base + "_clip" + os.path.splitext(p)[1])
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="linq_false_alarms.zip"'})


# ---------- аналитика ----------
@app.get("/stats")
def stats(_=Depends(view)):
    ev = db.events_for_stats()
    hourly = Counter(int(e["timestamp"][11:13]) // 2 * 2 for e in ev)
    by_status, by_viol, by_site = (Counter(e[k] for e in ev) for k in ("status", "violation", "site_name"))
    return {"total": len(ev), "pending": by_status["new"], "by_status": by_status,
            "by_violation": [{"violation": v[0], "title": v[2], "count": by_viol[v[0]]} for v in VIOLATIONS],
            "top_sites": [{"site_name": s, "count": n} for s, n in by_site.most_common(10)],
            "hourly": [{"hour": f"{h:02d}:00", "count": hourly[h]} for h in range(0, 24, 2)],
            "cameras": len(db.cameras_list())}


# ---------- демо-данные при первом запуске (как в моках фронтенда) ----------
def seed():
    for rid, name in {1: "Специалист по ОТ", 2: "Мастер", 3: "Диспетчер", 7: "IT-служба"}.items():
        db.role_create(rid, name)   # обычно роли уже есть из schema.sql
    if not db.users_list():
        for login, rid, fn in [("mikhalyich_ot", 1, "Кузьмин М.П."), ("disp_smena1", 3, "Соколов А.В."),
                               ("master_ceh1", 2, "Громов И.С."), ("it_linq_admin", 7, "Дехтерюк Д.К.")]:
            make_user(login, SEED_PASSWORD, rid, fn)
    if db.sites_list():
        return
    z = lambda i, t, label, x, y, w, h, sch="Круглосуточно": {"id": f"z-{i}", "type": t, "shape": "rect", "label": label, "schedule": sch, "rect": {"x": x, "y": y, "w": w, "h": h}}
    for site, cam, ctype, vec, pos, zones in [
        ("Участок №1 — Сборочный цех (ОПО А-1)", "Камера 01 • Линия конвейера", "dynamic", [0, 1, 1, 0, 1, 0, 1, 0], (22, 26),
         [z(1, "danger", "Робот-манипулятор", 56, 32, 32, 48), z(2, "attention", "Проход у конвейера", 10, 40, 30, 44, "08:00 – 20:00")]),
        ("Участок №2 — Склад и отгрузка (ОПО А-2)", "Камера 02 • Зона погрузчиков", "static", [1, 1, 0, 0, 0, 0, 1, 1], (52, 72),
         [z(3, "danger", "Проезд погрузчика", 25, 38, 48, 46, "08:00 – 12:00")]),
        ("Участок №3 — Окрасочная и ГСМ (ОПО А-3)", "Камера 03 • Хим. блок", "dynamic", [0, 0, 0, 1, 1, 1, 1, 0], (80, 64), [])]:
        sid = db.site_create(site, None)
        cid = db.camera_create({"code": "", "site_id": sid, "name": cam, "camera_type": ctype, "rtsp_url": f"rtsp://10.0.114.1{sid}:554/linq_stream_0{sid}",
                                "rules_vector": vec, "map_pos": {"x": pos[0], "y": pos[1]}, "zones": zones,
                                "extra": {"workers": [{"id": f"TRK-{sid}1", "label": f"ID #{sid}1 • Сотрудник", "x": 35, "y": 40, "w": 12, "h": 34, "ppeOk": True}]}})
        db.camera_update(cid, {"code": f"CAM-{cid:02d}"})


seed()
