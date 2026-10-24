"""Слой БД (PostgreSQL) — единственное место с SQL. Схема: schema.sql (создаётся docker-compose
или автоматически при старте, если таблиц ещё нет). Строка подключения: DATABASE_URL (env или .env).
Функции принимают/возвращают dict/list/None; jsonb — Python-объекты, timestamptz — строки 'YYYY-MM-DD HH:MM:SS'.
Имена колонок в *_create/*_update приходят только из белых списков в main.py, значения — только параметрами.
"""
import os, threading
from datetime import datetime
from zoneinfo import ZoneInfo
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = os.path.dirname(os.path.abspath(__file__))
_JSON = {"rules", "rules_vector", "map_pos", "zones", "ai_pos", "value", "extra"}


def _url():
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    try:
        for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return "postgresql://linq_user:linq_password@localhost:5432/linq_db"


_lock = threading.RLock()
_conn = psycopg.connect(_url(), row_factory=dict_row, autocommit=True)
_conn.execute("SELECT set_config('TimeZone', %s, false)", (os.environ.get("APP_TZ", "Europe/Moscow"),))
if not _conn.execute("SELECT to_regclass('public.users') AS t").fetchone()["t"]:
    _conn.execute(open(os.path.join(ROOT, "schema.sql"), encoding="utf-8").read())
# миграции для БД, созданных по прежней схеме (docker volume): каждая безопасна при повторе
for _sql in ["ALTER TABLE sessions ADD COLUMN IF NOT EXISTS expires_at timestamptz",
             "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS extra jsonb NOT NULL DEFAULT '{}'",
             *[f"ALTER TYPE violation_type ADD VALUE IF NOT EXISTS '{v}'"
               for v in ("NO_HELMET", "NO_VEST", "DANGER_ZONE", "NO_GLOVES", "NO_GOGGLES")],
             "ALTER TABLE events ADD COLUMN IF NOT EXISTS ended_at timestamptz",
             "ALTER TABLE events ADD COLUMN IF NOT EXISTS duration_s real",
             "ALTER TABLE events ADD COLUMN IF NOT EXISTS clip_url text",
             "ALTER TABLE events ADD COLUMN IF NOT EXISTS zone text",
             "ALTER TABLE events ADD COLUMN IF NOT EXISTS ai_event_id text",
             "CREATE UNIQUE INDEX IF NOT EXISTS ux_events_ai_id ON events(ai_event_id)"]:
    _conn.execute(_sql)


_TZ = ZoneInfo(os.environ.get("APP_TZ", "Europe/Moscow"))


def _row(r):  # время — строкой в часовом поясе цеха, независимо от пояса сервера БД
    if r is None:
        return None
    return {k: (v.astimezone(_TZ).strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v) for k, v in r.items()}


def _all(sql, args=()):
    with _lock:
        return [_row(r) for r in _conn.execute(sql, args).fetchall()]


def _one(sql, args=()):
    with _lock:
        return _row(_conn.execute(sql, args).fetchone())


def _run(sql, args=()):
    with _lock:
        _conn.execute(sql, args)


def _enc(k, v): return Jsonb(v) if k in _JSON else v


def _ins(t, d):
    r = _one(f"INSERT INTO {t}({','.join(d)}) VALUES({','.join(['%s'] * len(d))}) RETURNING id", [_enc(k, v) for k, v in d.items()])
    return r["id"]


def _upd(t, i, d):
    if d:
        _run(f"UPDATE {t} SET {','.join(k + '=%s' for k in d)} WHERE id=%s", [_enc(k, v) for k, v in d.items()] + [i])


# ---- роли / пользователи / сессии ----
_U = "SELECT u.*, r.name AS role_name FROM users u JOIN roles r ON r.id=u.role_id"
def role_create(rid, name): _run("INSERT INTO roles VALUES(%s,%s) ON CONFLICT DO NOTHING", (rid, name))
def roles_list(): return _all("SELECT * FROM roles ORDER BY id")
def user_create(d): return _ins("users", d)        # login, password_hash, role_id, full_name, is_active
def user_update(uid, d): _upd("users", uid, d)
def user_get(uid): return _one(_U + " WHERE u.id=%s", (uid,))
def user_by_login(login): return _one(_U + " WHERE u.login=%s", (login,))
def users_list(): return _all(_U + " ORDER BY u.id")
def session_create(token, uid): _run("INSERT INTO sessions(token,user_id,expires_at) VALUES(%s,%s, now() + interval '7 days')", (token, uid))
def user_by_session(token):
    return _one(_U + " JOIN sessions s ON s.user_id=u.id WHERE s.token=%s AND u.is_active "
                "AND (s.expires_at IS NULL OR s.expires_at>now())", (token,))


# ---- участки ----
def site_create(name, rules): return _ins("sites", {"name": name, "rules": rules})
def site_update(sid, d): _upd("sites", sid, d)      # name, rules
def site_get(sid): return _one("SELECT * FROM sites WHERE id=%s", (sid,))
def site_by_name(name): return _one("SELECT * FROM sites WHERE name=%s", (name,))
def sites_list(): return _all("SELECT * FROM sites ORDER BY id")


# ---- камеры (в ответе есть site_name) ----
_C = "SELECT c.*, s.name AS site_name FROM cameras c JOIN sites s ON s.id=c.site_id"
def camera_create(d): return _ins("cameras", d)
def camera_update(cid, d): _upd("cameras", cid, d)
def camera_delete(cid): _run("DELETE FROM cameras WHERE id=%s", (cid,))   # события удаляются каскадом
def camera_get(cid): return _one(_C + " WHERE c.id=%s", (cid,))
def cameras_list(): return _all(_C + " ORDER BY c.id")


# ---- события (в ответе есть camera_code, site_name, processed_by_name) ----
_E = ("SELECT e.*, c.code AS camera_code, s.name AS site_name, u.full_name AS processed_by_name FROM events e "
      "JOIN cameras c ON c.id=e.camera_id JOIN sites s ON s.id=c.site_id LEFT JOIN users u ON u.id=e.processed_by_id")
def event_create(d): return _ins("events", d)
def event_update(eid, d): _upd("events", eid, d)
def event_get(eid): return _one(_E + " WHERE e.id=%s", (eid,))
def event_by_ai_id(ai_id): return _one(_E + " WHERE e.ai_event_id=%s", (ai_id,))


def events_list(status=None, camera_id=None, since_id=0, limit=200):  # новые первыми
    w, a = ["e.id>%s"], [since_id]
    for col, v in (("e.status", status), ("e.camera_id", camera_id)):
        if v is not None:
            w.append(col + "=%s"); a.append(v)
    return _all(_E + " WHERE " + " AND ".join(w) + " ORDER BY e.id DESC LIMIT %s", a + [limit])


def events_for_stats():  # [{violation, status, site_name, timestamp}]
    return _all("SELECT e.violation::text AS violation, e.status::text AS status, s.name AS site_name, e.timestamp FROM events e "
                "JOIN cameras c ON c.id=e.camera_id JOIN sites s ON s.id=c.site_id")


# ---- настройки (sirenEnabled, skudLockEnabled, ...) ----
def settings_get(): return {r["key"]: r["value"] for r in _all("SELECT * FROM settings")}
def settings_set(d):
    for k, v in d.items():
        _run("INSERT INTO settings VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, Jsonb(v)))
