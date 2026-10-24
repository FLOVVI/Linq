#!/usr/bin/env python3
"""LinQ одной командой: БД, бэкенд, ИИ-модуль и сайт (Linux, macOS, Windows).

    python run.py          всё; ИИ на ускорителе LinQ, если он доступен (плата в компьютере или облако по VPN),
                           иначе на процессоре (ONNX)
    python run.py cpu      ИИ на процессоре
    python run.py tpu      ИИ строго на ускорителе LinQ (если его нет — ошибка)
    python run.py noai     без ИИ-модуля (сайт и журнал работают, видео с разметкой нет)
    python run.py stop     остановить то, что осталось от прошлого запуска (если окно закрыли без Ctrl+C)

Ярлыки: ./run.sh (Linux, macOS), run.bat или run.ps1 (Windows) — с теми же словами.
Нужны только Python 3.10+ и Node.js 20.19+ (или 22.12+). Остальное ставится само при первом запуске:
Python-библиотеки — в .venv, библиотеки сайта — в frontend/node_modules, а база данных берётся так:
уже запущенная (адрес из DATABASE_URL в .env) → Docker (docker compose, если Docker запущен) →
установленный PostgreSQL (своя база в localdb/pg) → PGlite (PostgreSQL на Node.js, данные в localdb/pglite).
Выбрать способ явно: переменная LINQ_DB=docker | pg | pglite (в окружении или в .env).
Остановка — Ctrl+C в этом окне. Логи каждого сервиса — в logs/.
"""

import glob
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WIN = os.name == "nt"
API_PORT, WEB_PORT, AI_PORT, DB_PORT = 8000, 5173, 8001, 5433
LOGS = ROOT / "logs"
STATE = LOGS / "run_state.json"
VENV = ROOT / ".venv"
VPY = VENV / ("Scripts/python.exe" if WIN else "bin/python")
LOCALDB = ROOT / "localdb"
DEFAULT_DB_URL = f"postgresql://linq_user:linq_password@localhost:{DB_PORT}/linq_db"
PGLITE_PKG = {"name": "linq-localdb", "private": True,
              "dependencies": {"@electric-sql/pglite": "0.5.11", "@electric-sql/pglite-socket": "0.2.14"}}
PY_ENV = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}

try:  # кириллица и значки в логах ИИ-модуля не должны ронять вывод в старых консолях Windows
    sys.stdout.reconfigure(errors="replace")
except AttributeError:
    pass


def say(msg=""):
    print(msg, flush=True)


def die(msg):
    say(f"\nОшибка: {msg}")
    sys.exit(1)


def run(cmd, cwd=None, env=None, quiet=False):
    """Шаг установки: при ошибке — выход с понятным сообщением."""
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env,
                       stdout=subprocess.DEVNULL if quiet else None, stderr=subprocess.STDOUT if quiet else None)
    if r.returncode:
        die(f"команда завершилась с кодом {r.returncode}: {' '.join(str(c) for c in cmd)}")


def port_open(port, host="127.0.0.1", timeout=0.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_port(port, name, sec, proc=None):
    end = time.time() + sec
    while not port_open(port):
        if proc is not None and proc.p.poll() is not None:
            proc.dump_tail()
            die(f"{name} не запустился (код {proc.p.returncode}), подробности — {proc.log_path}")
        if time.time() > end:
            die(f"{name} не запустился за {sec} с (порт {port}), подробности — в logs/")
        time.sleep(0.3)


def env_value(name):
    """Переменная окружения или строка NAME=значение из .env."""
    if os.environ.get(name):
        return os.environ[name]
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None


def digest(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, bytes) else str(p).encode())
    return h.hexdigest()


# ------------------------------------------------------------------ дочерние процессы
class Proc:
    """Сервис в фоне: вывод — в logs/<name>.log и в эту консоль с подписью."""

    def __init__(self, title, slug, cmd, cwd, env=None):
        self.title = title
        self.log_path = LOGS / f"{slug}.log"
        self.log = open(self.log_path, "a", encoding="utf-8")
        self.log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} {' '.join(map(str, cmd))}\n")
        self.tail = deque(maxlen=25)
        kw = {"cwd": cwd, "env": env, "stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE,
              "stderr": subprocess.STDOUT}
        if WIN:
            kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kw["start_new_session"] = True  # Ctrl+C получает только run.py, сервисы он гасит сам и по порядку
        self.p = subprocess.Popen([str(c) for c in cmd], **kw)
        self.reported = False
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for raw in iter(self.p.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip()
            self.log.write(line + "\n")
            self.log.flush()
            self.tail.append(line)
            if line.strip():
                say(f"[{self.title}] {line}")

    def dump_tail(self):
        for line in self.tail:
            say(f"    {line}")

    def stop(self):
        if self.p.poll() is None:
            kill_tree(self.p.pid)
            try:
                self.p.wait(10)
            except subprocess.TimeoutExpired:
                kill_tree(self.p.pid, force=True)


def kill_tree(pid, force=False):
    if WIN:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        return
    try:
        os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


def pid_alive(pid):
    if WIN:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def save_state(procs, db_mode):
    STATE.write_text(json.dumps({"pids": [p.p.pid for p in procs], "db": db_mode}), encoding="utf-8")


# ------------------------------------------------------------------ Python и Node.js
def find_python():
    """Интерпретатор для .venv: 3.10–3.13 (под них есть колёса onnxruntime и opencv), иначе тот, что запустил run.py."""
    cands = []
    for v in ("3.12", "3.11", "3.13", "3.10"):
        if WIN and shutil.which("py"):
            cands.append(["py", f"-{v}"])
        exe = shutil.which(f"python{v}")
        if exe:
            cands.append([exe])
    cands.append([sys.executable])
    for c in cands:
        try:
            r = subprocess.run(c + ["-c", "import sys; print(*sys.version_info[:2], sys.executable)"],
                               capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode == 0 and r.stdout.strip():
            major, minor, exe = r.stdout.strip().split(" ", 2)
            if (int(major), int(minor)) >= (3, 10):
                return exe
    die("нужен Python 3.10 или новее: https://www.python.org/downloads/ (в установщике Windows — галочка «Add to PATH»)")


def ensure_venv():
    if VPY.exists():
        return
    base = find_python()
    # плата LinQ в этом компьютере: её pytpu и numpy 1.x стоят в системе — .venv видит их, а numpy не обновляет
    r = subprocess.run([base, "-c", "import pytpu, numpy; print(numpy.__version__)"], capture_output=True, text=True)
    board = r.returncode == 0
    say(f"Python: создаю .venv ({base}{', с системной средой платы LinQ' if board else ''})…")
    run([base, "-m", "venv", *(["--system-site-packages"] if board else []), str(VENV)])
    if board:
        (VENV / "linq-constraints.txt").write_text(f"numpy=={r.stdout.strip()}\n", encoding="utf-8")


def ensure_python_deps():
    req = ROOT / "requirements.txt"
    cons = VENV / "linq-constraints.txt"
    stamp = VENV / ".linq-requirements"
    want = digest(req.read_bytes(), cons.read_bytes() if cons.exists() else b"")
    if stamp.exists() and stamp.read_text() == want:
        return
    say("Python-библиотеки: установка в .venv (первый раз — несколько минут)…")
    run([VPY, "-m", "pip", "install", "--disable-pip-version-check", "-q", "--upgrade", "pip"])
    run([VPY, "-m", "pip", "install", "--disable-pip-version-check", "-r", req, *(["-c", cons] if cons.exists() else [])])
    stamp.write_text(want)


def find_node():
    node, npm = shutil.which("node"), (WIN and shutil.which("npm.cmd")) or shutil.which("npm")
    if not node or not npm:
        die("нужен Node.js 20.19+ (https://nodejs.org, вариант LTS) — на нём работает сайт")
    v = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    ver = tuple(int(x) for x in re.findall(r"\d+", v)[:2])
    if ver < (20, 19) or (21, 0) <= ver < (22, 12):
        die(f"Node.js {v} слишком старый для сайта (Vite 8): нужен 20.19+ или 22.12+ — https://nodejs.org")
    return node, npm


def ensure_node_deps(npm, folder, what):
    lock = folder / "package-lock.json"
    stamp = folder / "node_modules" / ".linq-installed"
    # в node_modules есть нативные модули под ОС — папку, принесённую с другой системы, ставим заново
    want = lambda: digest((folder / "package.json").read_bytes(), lock.read_bytes() if lock.exists() else b"",  # noqa: E731
                          sys.platform, platform.machine())
    if stamp.exists() and stamp.read_text() == want():
        return
    say(f"{what}: установка библиотек npm (первый раз — около минуты)…")
    run([npm, "ci" if lock.exists() else "install", "--no-audit", "--no-fund"], cwd=folder)
    stamp.write_text(want())  # npm install мог создать package-lock.json — отметка по итоговому состоянию


# ------------------------------------------------------------------ база данных
def parse_db_url(url):
    m = re.match(r"postgres(?:ql)?://(?:([^:@/]+)(?::([^@/]*))?@)?([^:/?]+)(?::(\d+))?/([^?]+)", url)
    if not m:
        die(f"не понял DATABASE_URL: {url}")
    user, pw, host, port, db = m.groups()
    return {"user": user or "postgres", "password": pw or "", "host": host, "port": int(port or 5432), "db": db}


def db_ready(url):
    code = "import sys, psycopg; psycopg.connect(sys.argv[1], connect_timeout=3).close()"
    return subprocess.run([VPY, "-c", code, url], capture_output=True).returncode == 0


def wait_db(url, sec, proc=None):
    end = time.time() + sec
    while not db_ready(url):
        if proc is not None and proc.p.poll() is not None:
            proc.dump_tail()
            die(f"БД не запустилась, подробности — {proc.log_path}")
        if time.time() > end:
            die(f"БД не отвечает за {sec} с по адресу {url} — подробности в logs/")
        time.sleep(1)


def docker_cmd():
    d = shutil.which("docker")
    if d:
        try:
            if subprocess.run([d, "info"], capture_output=True, timeout=20).returncode != 0:
                return None  # Docker установлен, но не запущен
        except subprocess.TimeoutExpired:
            return None
        if subprocess.run([d, "compose", "version"], capture_output=True).returncode == 0:
            return [d, "compose"]
    dc = shutil.which("docker-compose")
    return [dc] if dc else None


def find_pg_bin():
    exe = ".exe" if WIN else ""
    pg = shutil.which("pg_ctl")
    if pg and shutil.which("initdb"):
        return Path(pg).parent
    if WIN:
        pats = [r"C:\Program Files\PostgreSQL\*\bin"]
    elif sys.platform == "darwin":
        pats = ["/opt/homebrew/opt/postgresql*/bin", "/usr/local/opt/postgresql*/bin",
                "/Applications/Postgres.app/Contents/Versions/*/bin"]
    else:
        pats = ["/usr/lib/postgresql/*/bin", "/usr/pgsql-*/bin"]
    for pat in pats:
        for d in sorted(glob.glob(pat), key=lambda p: [int(x) for x in re.findall(r"\d+", p)] or [0], reverse=True):
            if (Path(d) / f"pg_ctl{exe}").exists() and (Path(d) / f"initdb{exe}").exists():
                return Path(d)
    return None


def start_local_pg(bindir, cfg, url):
    exe = ".exe" if WIN else ""
    data = LOCALDB / "pg"
    env = {**os.environ, "LC_ALL": "C", "LANG": "C"}
    if not (data / "PG_VERSION").exists():
        say(f"БД: создаю свою базу PostgreSQL в {data.relative_to(ROOT)}…")
        LOCALDB.mkdir(exist_ok=True)
        pw = LOCALDB / "pw.tmp"
        pw.write_text(cfg["password"], encoding="utf-8")
        try:
            run([bindir / f"initdb{exe}", "-D", data, "-U", cfg["user"], f"--pwfile={pw}", "-A", "scram-sha-256",
                 "-E", "UTF8", "--locale=C"], env=env, quiet=True)
        finally:
            pw.unlink()
    opts = f"-p {cfg['port']} -c listen_addresses=127.0.0.1"
    if not WIN:  # сокет — в /tmp по умолчанию; у пакетного PostgreSQL Linux папка /var/run/postgresql недоступна
        opts += " -c unix_socket_directories=''"
    say(f"БД: PostgreSQL ({bindir}) на порту {cfg['port']}")
    run([bindir / f"pg_ctl{exe}", "-D", data, "-l", LOGS / "db.log", "-w", "-t", "60", "-o", opts, "start"], env=env)
    admin = re.sub(r"/[^/?]+(\?|$)", r"/postgres\1", url)
    code = ("import sys, psycopg\nc = psycopg.connect(sys.argv[1], autocommit=True)\n"
            "if not c.execute('SELECT 1 FROM pg_database WHERE datname=%s', (sys.argv[2],)).fetchone():\n"
            "    c.execute('CREATE DATABASE \"%s\"' % sys.argv[2])\n")
    run([VPY, "-c", code, admin, cfg["db"]])


def stop_local_pg():
    bindir = find_pg_bin()
    if bindir and (LOCALDB / "pg" / "postmaster.pid").exists():
        subprocess.run([bindir / ("pg_ctl.exe" if WIN else "pg_ctl"), "-D", LOCALDB / "pg", "-m", "fast", "stop"],
                       capture_output=True)


def start_pglite(node, npm, cfg):
    folder = LOCALDB / "pglite"
    folder.mkdir(parents=True, exist_ok=True)
    pkg = folder / "package.json"
    if not pkg.exists() or json.loads(pkg.read_text(encoding="utf-8")) != PGLITE_PKG:
        pkg.write_text(json.dumps(PGLITE_PKG, indent=2), encoding="utf-8")
    ensure_node_deps(npm, folder, "БД (PGlite)")
    server = folder / "node_modules/@electric-sql/pglite-socket/dist/scripts/server.js"
    say(f"БД: PGlite (PostgreSQL на Node.js, данные в {(folder / 'data').relative_to(ROOT)}) на порту {cfg['port']}")
    return Proc("БД", "db", [node, server, "--db=./data", f"--port={cfg['port']}", "--host=127.0.0.1",
                              "--max-connections=4"], cwd=folder)


# ------------------------------------------------------------------ ИИ-модуль
def lfs_pointers(paths):
    bad = []
    for p in paths:
        if p.exists() and p.stat().st_size < 1024 and p.read_bytes().startswith(b"version https://git-lfs"):
            bad.append(p)
    return bad


def ai_files_problem():
    ai = ROOT / "ai"
    files = list((ai / "models").glob("*.onnx")) + list((ai / "models").glob("*.tpu"))
    cfg = (ai / "configs" / "site_bridge.yaml").read_text(encoding="utf-8")
    files += [(ai / "configs" / v).resolve() for v in re.findall(r"(\.\./data/videos/[^\s}]+)", cfg)]
    missing = [p for p in files if not p.exists()]
    bad = lfs_pointers(files)
    if not files or missing or bad:
        names = ", ".join(sorted({p.name for p in (missing + bad)})[:4]) or "ai/models/*.onnx"
        why = "это указатели Git LFS, а не сами файлы" if bad else "их нет"
        return (f"модели и демо-видео ИИ ({names}…) — {why}. Скопируйте настоящие ai/models и ai/data/videos "
                f"из полной копии проекта (или скачайте их через git lfs pull)")
    return None


def accelerator():
    """('board' | 'cloud' | None, чего не хватает для ускорителя)."""
    code = ("import importlib.util as u\n"
            "print(' '.join(m for m in ('pytpu', 'pika', 'google.protobuf', 'tpu_pycloud_format') if u.find_spec(m)))")
    mods = set(subprocess.run([VPY, "-c", code], cwd=ROOT / "ai", capture_output=True, text=True).stdout.split())
    if "pytpu" in mods:
        return "board", ""
    missing = []
    if not env_value("LINQ_LOGIN"):
        missing.append("LINQ_LOGIN=<логин Jupyter> в .env")
    missing += [f"библиотека {m}" for m in ("pika", "google.protobuf", "tpu_pycloud_format") if m not in mods]
    broker = env_value("LINQ_BROKER") or "10.0.114.30"
    if not port_open(5672, broker, timeout=1.5):
        missing.append(f"брокер {broker}:5672 недоступен (включите VPN хакатона)")
    return (None, "; ".join(missing)) if missing else ("cloud", "")


# ------------------------------------------------------------------ запуск и остановка
def stop_previous(verbose):
    if not STATE.exists():
        if verbose:
            stop_local_pg()
            say("Запущенных сервисов LinQ не найдено.")
        return
    st = json.loads(STATE.read_text(encoding="utf-8"))
    for pid in st.get("pids", []):
        if pid_alive(pid):
            kill_tree(pid, force=True)
    if st.get("db") == "pg":
        stop_local_pg()
    elif st.get("db") == "docker" and docker_cmd():
        subprocess.run(docker_cmd() + ["stop"], cwd=ROOT, capture_output=True)
    STATE.unlink()
    if verbose:
        say("Всё остановлено.")


def main():
    args = [a.lower().lstrip("-/") for a in sys.argv[1:]]
    action = args[0] if args else "start"
    if action in ("h", "help", "?"):
        say(__doc__)
        return
    if action not in ("start", "cpu", "tpu", "noai", "stop"):
        die(f"неизвестная команда «{action}». Доступно: start (по умолчанию), cpu, tpu, noai, stop")
    LOGS.mkdir(exist_ok=True)
    if action == "stop":
        stop_previous(verbose=True)
        return
    if STATE.exists():
        st = json.loads(STATE.read_text(encoding="utf-8"))
        if any(pid_alive(p) for p in st.get("pids", [])):
            die("LinQ уже запущен в другом окне. Остановите его (Ctrl+C там) или: python run.py stop")
        stop_previous(verbose=False)  # окно прошлого запуска закрыли без Ctrl+C — убираем остатки
    with_ai = action != "noai"
    for port, name in [(API_PORT, "бэкенда"), (WEB_PORT, "сайта")] + ([(AI_PORT, "ИИ-модуля")] if with_ai else []):
        if port_open(port):
            die(f"порт {port} ({name}) уже занят другой программой. Закройте её или выполните: python run.py stop")

    if not (ROOT / ".env").exists():
        (ROOT / ".env").write_text(f"DATABASE_URL={DEFAULT_DB_URL}\n", encoding="utf-8")
        say("Создан .env с адресом БД. Для ИИ на ускорителе LinQ по VPN добавьте в него строку LINQ_LOGIN=<логин Jupyter>")
    db_url = env_value("DATABASE_URL") or DEFAULT_DB_URL
    db = parse_db_url(db_url)
    node, npm = find_node()
    ensure_venv()
    ensure_python_deps()
    ensure_node_deps(npm, ROOT / "frontend", "Сайт")

    procs, db_mode = [], None
    py_env = {**os.environ, **PY_ENV, "DATABASE_URL": db_url}
    ingest_key = env_value("INGEST_KEY") or "dev-ingest-key"
    try:
        # 1. База данных
        local = db["host"] in ("localhost", "127.0.0.1", "::1")
        force = (env_value("LINQ_DB") or "").lower()
        if force not in ("", "docker", "pg", "pglite"):
            die(f"LINQ_DB={force}: допустимо docker, pg или pglite")
        if force == "docker" and not docker_cmd():
            die("LINQ_DB=docker, но Docker не установлен или не запущен")
        if force == "pg" and not find_pg_bin():
            die("LINQ_DB=pg, но PostgreSQL (pg_ctl, initdb) не найден")
        if port_open(db["port"], "127.0.0.1" if local else db["host"]) or not local:
            say(f"БД: уже запущена ({db['host']}:{db['port']})")
        elif force in ("", "docker") and docker_cmd():
            say("БД: Docker (docker compose up -d)")
            run(docker_cmd() + ["up", "-d"], cwd=ROOT)
            db_mode = "docker"
        elif force in ("", "pg") and find_pg_bin():
            db_mode = "pg"
            save_state(procs, db_mode)
            start_local_pg(find_pg_bin(), db, db_url)
        else:
            procs.append(start_pglite(node, npm, db))
            db_mode = "pglite"
        save_state(procs, db_mode)
        wait_db(db_url, 90, procs[0] if db_mode == "pglite" else None)

        # 2. Бэкенд: схему и демо-данные создаёт сам при первом запуске
        api = Proc("бэкенд", "backend", [VPY, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", API_PORT,
                                          "--no-access-log"], cwd=ROOT, env={**py_env, "INGEST_KEY": ingest_key})
        procs.append(api)
        save_state(procs, db_mode)
        wait_port(API_PORT, "Бэкенд", 90, api)

        # 3. Сайт (Vite; /api и /uploads проксируются на бэкенд)
        web = Proc("сайт", "frontend", [node, "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", WEB_PORT,
                                         "--strictPort"], cwd=ROOT / "frontend")
        procs.append(web)
        save_state(procs, db_mode)
        wait_port(WEB_PORT, "Сайт", 90, web)

        # 4. ИИ-модуль: камеры, правила и зоны берёт с сайта, присылает нарушения, видео с разметкой — на :8001
        ai_note = "выключен (python run.py noai)"
        if with_ai:
            problem = ai_files_problem()
            if problem:
                if action == "tpu":
                    die(problem)
                ai_note = "НЕ ЗАПУЩЕН: " + problem
            else:
                mode, missing = (None, "") if action == "cpu" else accelerator()
                if action == "tpu" and not mode:
                    die(f"ускоритель LinQ недоступен — не хватает: {missing}. Без него: python run.py cpu")
                ai_env = {**py_env, "LINQ_SITE_URL": f"http://127.0.0.1:{API_PORT}", "LINQ_INGEST_KEY": ingest_key}
                if mode == "cloud":  # .tpu-программы уже загружены на сервер в /auto/cache/<логин> (через Jupyter)
                    login = env_value("LINQ_LOGIN")
                    ai_env.update(LINQ_LOGIN=login, LINQ_REMOTE_CACHE=env_value("LINQ_REMOTE_CACHE") or f"/auto/cache/{login}")
                    for k in ("LINQ_BROKER",):
                        if env_value(k):
                            ai_env[k] = env_value(k)
                procs.append(Proc("ИИ", "ai", [VPY, "-m", "safetyvision", "bridge", "configs/site_bridge.yaml",
                                               "--backend", "tpu" if mode else "onnx"], cwd=ROOT / "ai", env=ai_env))
                save_state(procs, db_mode)
                ai_note = {"board": "ускоритель LinQ (плата в этом компьютере)",
                           "cloud": "ускоритель LinQ (удалённый, по VPN)"}.get(
                    mode, "процессор (ONNX)" + ("" if action == "cpu" else f" — ускоритель не найден: {missing}"))

        site = f"http://127.0.0.1:{WEB_PORT}"
        say(f"""
================================================================
 LinQ запущен.  Сайт: {site}
 Вход: it_linq_admin / linq123 (также mikhalyich_ot, disp_smena1, master_ceh1)
 API (Swagger): http://127.0.0.1:{API_PORT}/docs
 ИИ-модуль: {ai_note}
 {'ИИ-модулю нужна примерно минута на загрузку моделей — потом камеры на сайте выходят «в сеть».' if with_ai else ''}
 Остановить всё: Ctrl+C в этом окне. Логи: logs/
================================================================
""")
        if os.environ.get("LINQ_NO_BROWSER") != "1":
            webbrowser.open(site)

        core = {id(p) for p in procs if p.title in ("БД", "бэкенд", "сайт")}
        while True:
            time.sleep(1)
            for p in procs:
                if p.reported or p.p.poll() is None:
                    continue
                p.reported = True
                say(f"\n{p.title}: процесс завершился (код {p.p.returncode}). Последние строки ({p.log_path}):")
                p.dump_tail()
                if id(p) in core:
                    die("без него сайт не работает — останавливаю всё")
                say("Сайт продолжает работать без ИИ-модуля.")
    except KeyboardInterrupt:
        say("\nОстанавливаю…")
    finally:
        for p in reversed(procs):
            p.stop()
        if db_mode == "pg":
            stop_local_pg()
        elif db_mode == "docker" and docker_cmd():
            subprocess.run(docker_cmd() + ["stop"], cwd=ROOT, capture_output=True)
        if STATE.exists():
            STATE.unlink()
        say("Всё остановлено.")


if __name__ == "__main__":
    main()
