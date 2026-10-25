#!/usr/bin/env python3
"""LinQ одной командой: БД, бэкенд, ИИ-модуль и сайт (Linux, macOS, Windows).

    python run.py          меню: где считать ИИ (процессор или ускоритель LinQ), проверка компьютера, остановка
    python run.py cpu      ИИ на процессоре (ONNX) — работает на любом компьютере
    python run.py tpu      ИИ на ускорителе LinQ (плата в компьютере или облако по VPN); если его нет — ошибка
    python run.py auto     ускоритель LinQ, если он доступен, иначе процессор
    python run.py noai     без ИИ-модуля (сайт и журнал работают, видео с разметкой нет)
    python run.py check    проверить, всё ли есть на компьютере для запуска (ничего не устанавливает)
    python run.py stop     остановить то, что осталось от прошлого запуска (если окно закрыли без Ctrl+C)

Ярлыки с теми же словами: run.bat (Windows, двойной щелчок), run.command (macOS, двойной щелчок в Finder),
./run.sh (Linux, macOS). Без слова показывается меню; Enter в нём — LINQ_AI=cpu | tpu | auto | noai из .env,
если задан, иначе прошлый выбор.
Нужны Python 3.10–3.14 (64-бит) и Node.js 20.19+ или 22.12+. Остальное ставится само при первом запуске:
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
import webbrowser
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WIN = os.name == "nt"
MAC = sys.platform == "darwin"
API_PORT, WEB_PORT, AI_PORT, DB_PORT = 8000, 5173, 8001, 5433
SERVICE_PORTS = [(API_PORT, "бэкенд"), (WEB_PORT, "сайт"), (AI_PORT, "ИИ-модуль")]
LOGS = ROOT / "logs"
STATE = LOGS / "run_state.json"
LAST_CHOICE = LOGS / "last_choice.txt"
VENV = ROOT / ".venv"
VPY = VENV / ("Scripts/python.exe" if WIN else "bin/python")
LOCALDB = ROOT / "localdb"
DEFAULT_DB_URL = f"postgresql://linq_user:linq_password@127.0.0.1:{DB_PORT}/linq_db"
PY_MIN, PY_MAX = (3, 10), (3, 14)  # для них есть готовые колёса onnxruntime, opencv и scipy (для 3.15 onnxruntime ещё нет)
PGLITE_PKG = {"name": "linq-localdb", "private": True,
              "dependencies": {"@electric-sql/pglite": "0.5.11", "@electric-sql/pglite-socket": "0.2.14"}}
PY_ENV = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
AI_MODES = ("cpu", "tpu", "auto", "noai")

# Свой сервер PGlite вместо готового server.js из pglite-socket: журнал пишется сразу (видно, даже если Node
# занят запросом), лимит подключений с запасом (pglite-socket не освобождает слот после обрыва связи —
# на Windows это частый случай, electric-sql/pglite#1155), а при остановке база закрывается аккуратно.
PGLITE_SERVER = """\
// Пишется run.py при каждом запуске. Аргумент — порт.
import { writeSync } from "node:fs";
import { PGlite } from "@electric-sql/pglite";
import { PGLiteSocketServer } from "@electric-sql/pglite-socket";

const log = (msg) => writeSync(1, msg + "\\n");
const port = Number(process.argv[2]);
const t0 = Date.now();
const db = await PGlite.create("./data");
const server = new PGLiteSocketServer({ db, port, host: "127.0.0.1", maxConnections: 100 });
server.addEventListener("connection", (e) => log(`подключение ${e.detail.clientAddress}:${e.detail.clientPort}`));
server.addEventListener("error", (e) => log(`ошибка: ${e.detail?.message ?? e.detail}`));
await server.start();
log(`PGlite готова за ${Date.now() - t0} мс: 127.0.0.1:${port}`);

let closing = false;
async function stop(sig) {
  if (closing) return;
  closing = true;
  log(`остановка (${sig})`);
  await server.stop().catch(() => {});
  await db.close().catch(() => {});
  process.exit(0);
}
// Ctrl+Break — так run.py останавливает её на Windows; SIGHUP — закрыли окно консоли
for (const sig of ["SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP"]) process.on(sig, () => stop(sig));
"""

try:  # кириллица и значки в логах ИИ-модуля не должны ронять вывод в старых консолях Windows
    sys.stdout.reconfigure(errors="replace")
except AttributeError:
    pass


def os_hint(win, mac, linux):
    return win if WIN else mac if MAC else linux


PY_FIX = os_hint(
    "поставьте Python 3.13 (64-bit) с https://www.python.org/downloads/windows/ — в установщике отметьте "
    "«Add python.exe to PATH», потом откройте это окно заново",
    "brew install python@3.13 или установщик с https://www.python.org/downloads/macos/",
    "sudo apt install python3 python3-venv (Ubuntu, Debian) или sudo dnf install python3 (Fedora)")
NODE_FIX = os_hint(
    "установщик LTS (.msi) с https://nodejs.org, потом откройте это окно заново",
    "brew install node@22 или установщик LTS с https://nodejs.org",
    "в apt Node.js обычно слишком старый: nvm install 22 (https://github.com/nvm-sh/nvm) или https://nodejs.org")
PG_FIX = os_hint(
    "надёжнее — PostgreSQL 16+ (https://www.postgresql.org/download/windows/) или Docker Desktop: run.py найдёт их сам",
    "brew install postgresql@17 или Docker Desktop — run.py найдёт их сам",
    "sudo apt install postgresql или Docker — run.py найдёт их сам")
VCREDIST = "https://aka.ms/vs/17/release/vc_redist.x64.exe"


def say(msg=""):
    try:
        print(msg, flush=True)
    except OSError:  # окно терминала уже закрыли — сервисы всё равно надо остановить
        pass


def die(msg):
    say(f"\nОшибка: {msg}")
    sys.exit(1)


def ask(prompt, default=""):
    try:
        return input(prompt).strip().lower() or default
    except EOFError:
        return default


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


def amqp_alive(host, port=5672, timeout=2.0):
    """Брокер отвечает по протоколу AMQP. Просто открытый порт не довод: VPN-клиенты и прокси принимают любое
    TCP-подключение сами, даже к несуществующему адресу."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall(b"AMQP\x00\x00\x09\x01")
            data = s.recv(8)
    except OSError:
        return False
    return data[:1] == b"\x01" or data.startswith(b"AMQP")  # Connection.Start или «поддерживаю другую версию»


def wait_port(port, name, sec, proc=None, others=(), hint="", ready=None):
    """Ждёт, пока сервис откроет порт (или ready() станет истинным); при неудаче — хвосты логов и выход с подсказкой."""
    start = time.time()
    note = start + 20
    while not (ready() if ready else port_open(port)):
        failed = None
        if proc is not None and proc.p.poll() is not None:
            failed = f"{name} не запустился (код {proc.p.returncode}), подробности — {proc.log_path}"
        elif time.time() > start + sec:
            failed = f"{name} не запустился за {sec} с (порт {port}), подробности — в logs/"
        if failed:
            for p in (proc, *others):
                if p is not None and p.tail:
                    say(f"\nПоследние строки {p.log_path.name}:")
                    p.dump_tail()
            die(failed + hint)
        if time.time() > note:
            say(f"  …{name.lower()} ещё запускается ({time.time() - start:.0f} с)")
            note += 20
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

    def __init__(self, title, slug, cmd, cwd, env=None, graceful=False, ready_line=None):
        self.title = title
        self.graceful = graceful
        self.ready_line = ready_line
        self.ready = threading.Event()  # в выводе появилась строка ready_line
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
            if self.ready_line and self.ready_line in line:
                self.ready.set()
            if line.strip():
                say(f"[{self.title}] {line}")

    def dump_tail(self):
        for line in self.tail:
            say(f"    {line}")

    def stop(self):
        if self.p.poll() is not None:
            return
        if WIN and self.graceful:  # taskkill /F не даёт PGlite дописать данные; Ctrl+Break она обрабатывает сама
            try:
                os.kill(self.p.pid, signal.CTRL_BREAK_EVENT)
                self.p.wait(10)
                return
            except (OSError, subprocess.TimeoutExpired):
                pass
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


# ------------------------------------------------------------------ проверка компьютера
OK, WARN, FAIL, INFO = "ок", "!", "нет", "·"


class Report:
    """Итог проверок: строки [ок] / [!] / [нет] с подсказкой, что сделать."""

    def __init__(self):
        self.items = []

    def add(self, level, text, fix=""):
        self.items.append((level, text, fix))

    def failed(self):
        return [i for i in self.items if i[0] == FAIL]

    def show(self, problems_only=False):
        for level, text, fix in self.items:
            if problems_only and level not in (WARN, FAIL):
                continue
            say(f"  [{level:^3}] {text}")
            if fix and (level in (WARN, FAIL) or not problems_only):
                say(f"         → {fix}")


PROBE = "import sys, struct; print(*sys.version_info[:3], struct.calcsize('P') * 8, sys.executable)"


def probe_python(cmd):
    """(версия, разрядность, путь) интерпретатора или None, если он не запускается."""
    try:
        r = subprocess.run([str(c) for c in cmd] + ["-c", PROBE], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    parts = r.stdout.strip().split(" ", 4)
    if r.returncode or len(parts) < 5:
        return None
    return tuple(int(x) for x in parts[:3]), int(parts[3]), parts[4]


def py_ok(info):
    return info is not None and PY_MIN <= info[0][:2] <= PY_MAX and info[1] == 64


def py_name(info):
    return f"Python {'.'.join(map(str, info[0]))} ({info[1]}-бит)"


def find_python():
    """Python для .venv: 3.12 → 3.13 → 3.11 → 3.14 → 3.10, только 64-бит. (подходящий или None, все найденные)."""
    cands = []
    for v in ("3.12", "3.13", "3.11", "3.14", "3.10"):
        if WIN and shutil.which("py"):
            cands.append(["py", f"-{v}"])
        exe = shutil.which(f"python{v}")
        if exe:
            cands.append([exe])
    cands += [[sys.executable]] + [[exe] for exe in (shutil.which("python3"), shutil.which("python")) if exe]
    seen = []
    for c in cands:
        info = probe_python(c)
        if info and info[2] not in [s[2] for s in seen]:
            seen.append(info)
        if py_ok(info):
            return info, seen
    return None, seen


def check_python(rep):
    """Python для .venv; возвращает путь к базовому интерпретатору (None — .venv уже готова или Python нет)."""
    venv = probe_python([VPY]) if VPY.exists() else None
    if py_ok(venv):
        rep.add(OK, f"{py_name(venv)} в .venv")
        return None
    info, seen = find_python()
    if not info:
        have = ", ".join(py_name(s) for s in seen) or "нет"
        why = " — 3.15 и новее пока не подходят: для них нет onnxruntime" if any(s[0][:2] > PY_MAX for s in seen) else ""
        rep.add(FAIL, f"нужен Python 3.10–3.14, 64-бит (найдено: {have}){why}", PY_FIX)
        return None
    rep.add(OK, py_name(info) + (" — .venv будет создана заново" if VPY.exists() else ""))
    if not WIN and subprocess.run([info[2], "-c", "import venv, ensurepip"], capture_output=True).returncode:
        v = "%d.%d" % info[0][:2]
        rep.add(FAIL, f"в Python {v} нет модуля venv", f"sudo apt install python{v}-venv (Ubuntu, Debian)")
    return info[2]


def node_info():
    node, npm = shutil.which("node"), (WIN and shutil.which("npm.cmd")) or shutil.which("npm")
    ver = None
    if node:
        try:
            out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=30).stdout
        except (OSError, subprocess.TimeoutExpired):
            out = ""
        nums = re.findall(r"\d+", out)[:3]
        ver = tuple(int(x) for x in nums) if len(nums) == 3 else None
    return node, npm, ver


def check_node(rep):
    node, npm, ver = node_info()
    if not node or not ver:
        rep.add(FAIL, "нужен Node.js 20.19+ или 22.12+ (LTS) — на нём работает сайт", NODE_FIX)
    elif ver[:2] < (20, 19) or (21, 0) <= ver[:2] < (22, 12):
        rep.add(FAIL, f"Node.js {'.'.join(map(str, ver))} слишком старый: нужен 20.19+ или 22.12+", NODE_FIX)
    elif not npm:
        rep.add(FAIL, "Node.js есть, а npm не найден", "переустановите Node.js (LTS) с https://nodejs.org")
    else:
        rep.add(OK, f"Node.js {'.'.join(map(str, ver))} и npm")


def deps_installed():
    return (VENV / ".linq-requirements").exists() and (ROOT / "frontend/node_modules/.linq-installed").exists()


def check_disk(rep):
    need = 0.5 if deps_installed() else 3
    free = shutil.disk_usage(ROOT).free / 2 ** 30
    if free < need:
        rep.add(FAIL, f"на диске свободно {free:.1f} ГБ, нужно хотя бы {need:g} ГБ (библиотеки, база, клипы)",
                "освободите место на диске с проектом")
    else:
        rep.add(OK, f"на диске свободно {free:.0f} ГБ")


def ram_gb():
    try:
        if WIN:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                    (n, ctypes.c_ulonglong) for n in ("total", "avail", "pf", "pf_avail", "vm", "vm_avail", "ext")]
            st = MemoryStatus()
            st.length = ctypes.sizeof(st)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return st.total / 2 ** 30
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30
    except (OSError, ValueError, AttributeError):
        return None


def check_memory(rep):
    gb, cores = ram_gb(), os.cpu_count() or 0
    if gb is not None and gb < 7.5:
        rep.add(WARN, f"оперативной памяти {gb:.0f} ГБ — для ИИ на процессоре мало, видео может идти рывками",
                "запускайте без ИИ (noai) или на ускорителе LinQ (tpu)")
    else:
        rep.add(OK, (f"память {gb:.0f} ГБ, " if gb else "") + f"ядер процессора: {cores}")


def check_folder(rep):
    try:
        LOGS.mkdir(exist_ok=True)
        probe = LOGS / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        rep.add(FAIL, f"нет прав на запись в папку проекта {ROOT}",
                os_hint("распакуйте проект в свою папку, например C:\\LinQ (не в Program Files)",
                        "переложите проект в свою папку, например ~/LinQ", "переложите проект в свою папку, например ~/LinQ"))
        return
    path = str(ROOT)
    if WIN and not path.isascii():
        rep.add(WARN, f"в пути к проекту есть русские буквы или другие не латинские символы: {path}",
                "OpenCV на Windows не открывает видео по такому пути — переложите папку, например, в C:\\LinQ")
    if "onedrive" in path.lower():
        rep.add(WARN, "проект лежит в OneDrive: синхронизация тормозит установку и блокирует файлы",
                "переложите папку, например, в C:\\LinQ")


def check_vcredist(rep):
    if not WIN:
        return
    sysdir = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    missing = [d for d in ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll") if not (sysdir / d).exists()]
    if missing:
        rep.add(WARN, f"нет Microsoft Visual C++ Redistributable ({', '.join(missing)}) — без него не загрузится ИИ",
                f"поставьте его: {VCREDIST}")
    else:
        rep.add(OK, "Microsoft Visual C++ Redistributable")


def check_ports(rep, with_ai):
    ports = [(p, n) for p, n in SERVICE_PORTS if with_ai or p != AI_PORT]
    busy = [f"{p} ({n})" for p, n in ports if port_open(p)]
    if busy:
        rep.add(FAIL, f"заняты порты: {', '.join(busy)}",
                "закройте программу, которая их держит, или выполните: python run.py stop")
    else:
        rep.add(OK, f"порты {', '.join(str(p) for p, _ in ports)} свободны")


def check_internet(rep):
    """Интернет нужен только для первой установки библиотек."""
    if deps_installed():
        return
    bad = [h for h in ("pypi.org", "registry.npmjs.org") if not port_open(443, h, timeout=3)]
    proxy = any(os.environ.get(k) for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "PIP_INDEX_URL"))
    if not bad:
        rep.add(OK, "интернет для первой установки библиотек (pypi.org, registry.npmjs.org)")
    elif proxy:
        rep.add(INFO, f"{', '.join(bad)} напрямую недоступны — установка пойдёт через прокси из окружения")
    else:
        rep.add(WARN, f"нет доступа к {', '.join(bad)} — первая установка библиотек не пройдёт",
                "подключите интернет на время первого запуска (если включён VPN хакатона — проверьте, что сайты открываются)")


def preflight(with_ai):
    """Быстрые проверки перед запуском: (отчёт, базовый Python для .venv)."""
    rep = Report()
    base = check_python(rep)
    check_node(rep)
    check_folder(rep)
    check_disk(rep)
    check_ports(rep, with_ai)
    check_internet(rep)
    if with_ai:
        check_memory(rep)
        check_vcredist(rep)
    return rep, base


# ------------------------------------------------------------------ Python и Node.js
def ensure_venv(base):
    if py_ok(probe_python([VPY]) if VPY.exists() else None):
        return
    # плата LinQ в этом компьютере: её pytpu и numpy 1.x стоят в системе — .venv видит их, а numpy не обновляет
    r = subprocess.run([base, "-c", "import pytpu, numpy; print(numpy.__version__)"], capture_output=True, text=True)
    board = r.returncode == 0
    redo = VENV.exists()  # собрана другим Python или принесена с другого компьютера
    say(f"Python: {'пересоздаю' if redo else 'создаю'} .venv ({base}{', с системной средой платы LinQ' if board else ''})…")
    run([base, "-m", "venv", *(["--clear"] if redo else []), *(["--system-site-packages"] if board else []), VENV])
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
    pip = [VPY, "-m", "pip", "--disable-pip-version-check"]
    run(pip + ["install", "-q", "--upgrade", "pip"])
    # раньше ставился opencv-python (ему на Linux нужен libGL), теперь headless; оба пишут в одну папку cv2 —
    # старый убираем вместе с headless, и тот ставится начисто
    if not cons.exists() and subprocess.run(pip + ["show", "opencv-python"], capture_output=True).returncode == 0:
        run(pip + ["uninstall", "-y", "-q", "opencv-python", "opencv-python-headless"])
    run(pip + ["install", "-r", req, *(["-c", cons] if cons.exists() else [])])
    stamp.write_text(want)


def find_node():
    node, npm, _ = node_info()
    rep = Report()
    check_node(rep)
    if rep.failed():
        rep.show()
        die("без Node.js сайт не запустится")
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
def ipv4(url):
    """localhost → 127.0.0.1: на Windows localhost сначала пробуется по IPv6 (::1), а локальная БД слушает только IPv4."""
    return re.sub(r"(@|//)localhost(?=[:/])", r"\g<1>127.0.0.1", url, count=1)


def parse_db_url(url):
    m = re.match(r"postgres(?:ql)?://(?:([^:@/]+)(?::([^@/]*))?@)?([^:/?]+)(?::(\d+))?/([^?]+)", url)
    if not m:
        die(f"не понял DATABASE_URL: {url}")
    user, pw, host, port, db = m.groups()
    return {"user": user or "postgres", "password": pw or "", "host": host, "port": int(port or 5432), "db": db}


def db_ready(url):
    code = "import sys, psycopg\nwith psycopg.connect(sys.argv[1], connect_timeout=3) as c: c.execute('SELECT 1')"
    return subprocess.run([VPY, "-c", code, url], capture_output=True).returncode == 0


def wait_db(url, sec):
    end = time.time() + sec
    while not db_ready(url):
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
    elif MAC:
        pats = ["/opt/homebrew/opt/postgresql*/bin", "/usr/local/opt/postgresql*/bin",
                "/Applications/Postgres.app/Contents/Versions/*/bin"]
    else:
        pats = ["/usr/lib/postgresql/*/bin", "/usr/pgsql-*/bin"]
    for pat in pats:
        for d in sorted(glob.glob(pat), key=lambda p: [int(x) for x in re.findall(r"\d+", p)] or [0], reverse=True):
            if (Path(d) / f"pg_ctl{exe}").exists() and (Path(d) / f"initdb{exe}").exists():
                return Path(d)
    return None


def pick_db(db):
    """Какую БД возьмёт запуск: (способ, описание). Способ: running | docker | pg | pglite."""
    local = db["host"] in ("localhost", "127.0.0.1", "::1")
    force = (env_value("LINQ_DB") or "").lower()
    if force not in ("", "docker", "pg", "pglite"):
        die(f"LINQ_DB={force}: допустимо docker, pg или pglite")
    if port_open(db["port"], "127.0.0.1" if local else db["host"]) or not local:
        return "running", f"уже запущена ({db['host']}:{db['port']})"
    if force in ("", "docker") and docker_cmd():
        return "docker", "Docker (docker compose)"
    if force == "docker":
        die("LINQ_DB=docker, но Docker не установлен или не запущен")
    bindir = find_pg_bin() if force in ("", "pg") else None
    if bindir:
        return "pg", f"PostgreSQL ({bindir}), своя база в localdb/pg"
    if force == "pg":
        die("LINQ_DB=pg, но PostgreSQL (pg_ctl, initdb) не найден")
    return "pglite", "PGlite (PostgreSQL на Node.js), данные в localdb/pglite — ставить ничего не нужно"


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
    code = ("import sys, psycopg\nc = psycopg.connect(sys.argv[1], autocommit=True, connect_timeout=10)\n"
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
    for name, text in (("package.json", json.dumps(PGLITE_PKG, indent=2)), ("linq-server.mjs", PGLITE_SERVER)):
        f = folder / name
        if not f.exists() or f.read_text(encoding="utf-8") != text:
            f.write_text(text, encoding="utf-8")
    ensure_node_deps(npm, folder, "БД (PGlite)")
    say(f"БД: PGlite (PostgreSQL на Node.js, данные в {(folder / 'data').relative_to(ROOT)}) на порту {cfg['port']}")
    return Proc("БД", "db", [node, "linq-server.mjs", cfg["port"]], cwd=folder, graceful=True, ready_line="PGlite готова")


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


def ai_libs_problem(onnx):
    """Загружаются ли библиотеки ИИ из .venv; при ошибке — (ошибка, что сделать)."""
    mods = "numpy, cv2, yaml, scipy" + (", onnxruntime" if onnx else "")
    try:  # первый импорт на Windows с антивирусом бывает долгим — заодно прогреваем кэш для ИИ-модуля
        r = subprocess.run([VPY, "-c", "import " + mods], cwd=ROOT / "ai", capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env={**os.environ, **PY_ENV}, timeout=180)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode == 0:
        return None
    err = (r.stderr.strip().splitlines() or ["ошибка импорта"])[-1]
    if "DLL load failed" in err:
        fix = f"поставьте Microsoft Visual C++ Redistributable ({VCREDIST}) и запустите снова"
    elif re.search(r"libGL|libgthread|libglib", err):
        fix = "sudo apt install libgl1 libglib2.0-0"
    else:
        fix = "удалите папку .venv и запустите снова — библиотеки поставятся заново"
    return err, fix


def accelerator(libs=True):
    """('board' | 'cloud' | None, чего не хватает для ускорителя). libs=False — библиотеки ещё не поставлены, их не проверяем."""
    code = ("import importlib.util as u\n"
            "print(' '.join(m for m in ('pytpu', 'pika', 'google.protobuf', 'tpu_pycloud_format') if u.find_spec(m)))")
    py = VPY if VPY.exists() else sys.executable
    mods = set(subprocess.run([str(py), "-c", code], cwd=ROOT / "ai", capture_output=True, text=True).stdout.split())
    if "pytpu" in mods:
        return "board", ""
    missing = []
    if not env_value("LINQ_LOGIN"):
        missing.append("LINQ_LOGIN=<логин Jupyter> в .env")
    if libs:
        missing += [f"библиотека {m}" for m in ("pika", "google.protobuf", "tpu_pycloud_format") if m not in mods]
    broker = env_value("LINQ_BROKER") or "10.0.114.30"
    if not amqp_alive(broker):
        missing.append(f"брокер {broker}:5672 недоступен (включите VPN хакатона)")
    return (None, "; ".join(missing)) if missing else ("cloud", "")


def plan_ai(action, interactive):
    """Как запускать ИИ: (--backend для safetyvision или None, режим ускорителя, строка для итогов)."""
    if action == "noai":
        return None, None, "выключен (без ИИ)"
    problem = ai_files_problem()
    if problem:
        if action == "tpu":
            die(problem)
        return None, None, "НЕ ЗАПУЩЕН: " + problem
    mode, missing = (None, "") if action == "cpu" else accelerator()
    if action == "tpu" and not mode:
        msg = f"ускоритель LinQ недоступен — не хватает: {missing}"
        if not interactive:
            die(msg + ". Без него: python run.py cpu")
        say(f"\n{msg}.")
        if ask("Запустить ИИ на процессоре? [Enter — да, n — выйти]: ") in ("n", "т", "no", "нет"):
            sys.exit(1)
        action = "cpu"
    lib = ai_libs_problem(onnx=not mode)
    if lib:
        if action == "tpu":
            die(f"библиотеки ИИ не загружаются: {lib[0]}\n  → {lib[1]}")
        say(f"\nИИ-модуль не запустится — библиотеки не загружаются: {lib[0]}\n  → {lib[1]}\n")
        return None, None, f"НЕ ЗАПУЩЕН: {lib[0]} → {lib[1]}"
    note = {"board": "ускоритель LinQ (плата в этом компьютере)", "cloud": "ускоритель LinQ (удалённый, по VPN)"}.get(
        mode, "процессор (ONNX)" + ("" if action == "cpu" else f" — ускоритель не найден: {missing}"))
    return ("tpu" if mode else "onnx"), mode, note


# ------------------------------------------------------------------ меню и полная проверка
MENU = [("1", "cpu", "ИИ на процессоре (CPU)", "работает на любом компьютере"),
        ("2", "tpu", "ИИ на ускорителе LinQ (TPU)", "плата в компьютере или облако по VPN"),
        ("3", "auto", "Авто", "ускоритель, если доступен, иначе процессор"),
        ("4", "noai", "Без ИИ", "только сайт, журнал и карта"),
        ("5", "check", "Проверить компьютер", "ничего не устанавливает"),
        ("6", "stop", "Остановить прошлый запуск", "если окно закрыли без Ctrl+C"),
        ("0", "exit", "Выход", "")]


def menu():
    last = LAST_CHOICE.read_text(encoding="utf-8").strip() if LAST_CHOICE.exists() else ""
    default = next(m for m in ((env_value("LINQ_AI") or "").lower(), last, "cpu") if m in AI_MODES)
    while True:
        say("\n  LinQ — что запустить?\n")
        for key, act, title, note in MENU:
            say(f"   {key}  {title:<29} {note}{'   ← Enter' if act == default else ''}")
        ans = ask("\n  Номер и Enter: ", default)
        act = next((m[1] for m in MENU if ans in (m[0], m[1])), None)
        if act is None:
            say(f"  Нет пункта «{ans}».")
        elif act == "check":
            full_check()
        elif act == "stop":
            stop_previous(verbose=True)
        elif act == "exit":
            sys.exit(0)
        else:
            LAST_CHOICE.write_text(act, encoding="utf-8")
            return act


def full_check():
    say("\nПроверка компьютера для LinQ (ничего не устанавливается)\n")
    rep = Report()
    rep.add(INFO, f"система: {platform.system()} {platform.release()} ({platform.machine()})")
    check_python(rep)
    check_node(rep)
    check_folder(rep)
    check_disk(rep)
    check_memory(rep)
    check_vcredist(rep)
    check_ports(rep, with_ai=True)
    check_internet(rep)
    db_mode, db_desc = pick_db(parse_db_url(ipv4(env_value("DATABASE_URL") or DEFAULT_DB_URL)))
    rep.add(OK, "база данных: " + db_desc, PG_FIX if WIN and db_mode == "pglite" else "")

    installed = deps_installed() and VPY.exists()
    files = ai_files_problem()
    libs = ai_libs_problem(onnx=True) if installed and not files else None
    if files:
        rep.add(WARN, "ИИ не запустится: " + files)
    elif libs:
        rep.add(FAIL, f"библиотеки ИИ не загружаются: {libs[0]}", libs[1])
    else:
        rep.add(OK, "модели и демо-видео ИИ на месте" + ("" if installed else "; библиотеки поставятся при первом запуске"))
    mode, missing = accelerator(libs=installed)
    accel = {"board": "плата в этом компьютере", "cloud": "облако LinQ по VPN"}.get(mode)
    rep.add(OK if accel else INFO, f"ускоритель LinQ: {accel or 'недоступен'}",
            "" if accel else f"для tpu не хватает: {missing}")
    rep.show()

    cpu = "нельзя — см. пункты выше" if files or libs else "можно"
    say(f"\n  ИИ на процессоре (cpu): {cpu}")
    say(f"  ИИ на ускорителе LinQ (tpu): {'можно — ' + accel if accel else 'нельзя сейчас'}")
    if rep.failed():
        say("\nИтог: сначала исправьте пункты с отметкой [нет], затем запускайте.")
    else:
        say("\nИтог: можно запускать — " + os_hint("run.bat", "run.command или ./run.sh", "./run.sh") + ".")


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


def graceful_exit(signum, frame):
    raise KeyboardInterrupt  # SIGTERM, закрытое окно терминала, Ctrl+Break — останавливаем всё так же, как по Ctrl+C


def main():
    for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), graceful_exit)
    args = [a.lower().lstrip("-/") for a in sys.argv[1:]]
    action = {"start": "auto"}.get(args[0], args[0]) if args else None
    if action in ("h", "help", "?"):
        say(__doc__)
        return
    if action not in (None, "check", "stop") + AI_MODES:
        die(f"неизвестная команда «{action}». Доступно: cpu, tpu, auto, noai, check, stop (или без слова — меню)")
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    try:
        LOGS.mkdir(exist_ok=True)
    except OSError:
        die(f"нет прав на запись в папку проекта {ROOT} — переложите проект в свою папку")
    if action is None:
        action = menu() if interactive else (env_value("LINQ_AI") or "auto").lower()
        if action not in AI_MODES:
            die(f"LINQ_AI={action}: допустимо {', '.join(AI_MODES)}")
    if action == "check":
        full_check()
        return
    if action == "stop":
        stop_previous(verbose=True)
        return
    start(action, interactive)


def start(action, interactive):
    if STATE.exists():
        st = json.loads(STATE.read_text(encoding="utf-8"))
        if any(pid_alive(p) for p in st.get("pids", [])):
            die("LinQ уже запущен в другом окне. Остановите его (Ctrl+C там) или: python run.py stop")
        stop_previous(verbose=False)  # окно прошлого запуска закрыли без Ctrl+C — убираем остатки
    with_ai = action != "noai"
    rep, base = preflight(with_ai)
    if rep.failed() or any(i[0] == WARN for i in rep.items):
        say("Проверка компьютера:")
        rep.show(problems_only=True)
    if rep.failed():
        die("исправьте пункты с отметкой [нет] и запустите снова. Полный отчёт: python run.py check")

    if not (ROOT / ".env").exists():
        (ROOT / ".env").write_text(f"DATABASE_URL={DEFAULT_DB_URL}\n", encoding="utf-8")
        say("Создан .env с адресом БД. Для ИИ на ускорителе LinQ по VPN добавьте в него строку LINQ_LOGIN=<логин Jupyter>")
    db_url = ipv4(env_value("DATABASE_URL") or DEFAULT_DB_URL)
    db = parse_db_url(db_url)
    node, npm = find_node()
    ensure_venv(base)
    ensure_python_deps()
    ensure_node_deps(npm, ROOT / "frontend", "Сайт")
    ai_backend, ai_mode, ai_note = plan_ai(action, interactive)

    procs, db_mode = [], None
    py_env = {**os.environ, **PY_ENV, "DATABASE_URL": db_url}
    ingest_key = env_value("INGEST_KEY") or "dev-ingest-key"
    try:
        # 1. База данных
        db_mode, db_desc = pick_db(db)
        db_proc = None
        if db_mode == "running":
            say(f"БД: {db_desc}")
        elif db_mode == "docker":
            say("БД: Docker (docker compose up -d)")
            run(docker_cmd() + ["up", "-d"], cwd=ROOT)
        elif db_mode == "pg":
            save_state(procs, db_mode)
            start_local_pg(find_pg_bin(), db, db_url)
        else:
            db_proc = start_pglite(node, npm, db)
            procs.append(db_proc)
        save_state(procs, db_mode)
        if db_proc:  # ждём строку «PGlite готова»: лишние пробные подключения ей ни к чему
            wait_port(db["port"], "БД (PGlite)", 90, db_proc, ready=db_proc.ready.is_set)
        else:
            wait_db(db_url, 90)

        # 2. Бэкенд: схему и демо-данные создаёт сам при первом запуске
        api = Proc("бэкенд", "backend", [VPY, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", API_PORT,
                                          "--no-access-log"], cwd=ROOT, env={**py_env, "INGEST_KEY": ingest_key})
        procs.append(api)
        save_state(procs, db_mode)
        hint = "\nПроверить компьютер: python run.py check" + (f"\nЕсли бэкенд ждёт базу PGlite — {PG_FIX}" if db_proc else "")
        wait_port(API_PORT, "Бэкенд", 120, api, others=[db_proc] if db_proc else [], hint=hint)

        # 3. Сайт (Vite; /api и /uploads проксируются на бэкенд)
        web = Proc("сайт", "frontend", [node, "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", WEB_PORT,
                                         "--strictPort"], cwd=ROOT / "frontend")
        procs.append(web)
        save_state(procs, db_mode)
        wait_port(WEB_PORT, "Сайт", 90, web)

        # 4. ИИ-модуль: камеры, правила и зоны берёт с сайта, присылает нарушения, видео с разметкой — на :8001
        if ai_backend:
            ai_env = {**py_env, "LINQ_SITE_URL": f"http://127.0.0.1:{API_PORT}", "LINQ_INGEST_KEY": ingest_key}
            if ai_mode == "cloud":  # .tpu-программы уже загружены на сервер в /auto/cache/<логин> (через Jupyter)
                login = env_value("LINQ_LOGIN")
                ai_env.update(LINQ_LOGIN=login, LINQ_REMOTE_CACHE=env_value("LINQ_REMOTE_CACHE") or f"/auto/cache/{login}")
                if env_value("LINQ_BROKER"):
                    ai_env["LINQ_BROKER"] = env_value("LINQ_BROKER")
            procs.append(Proc("ИИ", "ai", [VPY, "-m", "safetyvision", "bridge", "configs/site_bridge.yaml",
                                           "--backend", ai_backend], cwd=ROOT / "ai", env=ai_env))
            save_state(procs, db_mode)

        site = f"http://127.0.0.1:{WEB_PORT}"
        say(f"""
================================================================
 LinQ запущен.  Сайт: {site}
 Вход: it_linq_admin / linq123 (также mikhalyich_ot, disp_smena1, master_ceh1)
 API (Swagger): http://127.0.0.1:{API_PORT}/docs
 База данных: {db_desc}
 ИИ-модуль: {ai_note}
 {'ИИ-модулю нужна примерно минута на загрузку моделей — потом камеры на сайте выходят «в сеть».' if ai_backend else ''}
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
    try:
        main()
    except KeyboardInterrupt:  # Ctrl+C в меню или во время установки
        say("\nПрервано.")
        sys.exit(130)
