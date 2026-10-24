# Запуск всего сайта одной командой: БД, бэкенд, фронтенд и ИИ-модуль.
#   run.bat        - запустить всё; ИИ на ускорителе LinQ (плата здесь или удалённая по VPN), если он найден, иначе на процессоре (ONNX)
#   run.bat tpu    - запустить всё, ИИ обязательно на ускорителе LinQ (если его нет - ошибка)
#   run.bat cpu    - запустить всё, ИИ на процессоре
#   run.bat stop   - остановить всё
param([string]$Action = 'start')
$ErrorActionPreference = 'Stop'
if ($Action -notin 'start', 'tpu', 'cpu', 'stop') { throw "Неизвестная команда '$Action'. Доступно: start (по умолчанию), tpu, cpu, stop" }
$Root = $PSScriptRoot
$DbPort = 5433; $ApiPort = 8000; $WebPort = 5173; $AiPort = 8001

function Test-Port($p) { [bool](Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue) }

function Test-Docker {   # Docker установлен И запущен (иначе docker info пишет в stderr и ломает скрипт)
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { return $false }
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    docker info *> $null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $old
    return $ok
}

function Get-EnvValue($name) {   # переменная окружения или строка NAME=значение из .env
    $v = [Environment]::GetEnvironmentVariable($name)
    if ($v) { return $v }
    if (Test-Path "$Root\.env") {
        foreach ($l in Get-Content "$Root\.env" -Encoding UTF8) {
            if ($l.Trim() -match "^$name=(.*)$") { return $Matches[1].Trim().Trim('"', "'") }
        }
    }
}

function Get-Accelerator {   # Mode: 'board' - плата LinQ в этом компьютере (pytpu); 'cloud' - плата хакатона по VPN; иначе $null и Missing - чего не хватает
    Push-Location "$Root\ai"   # tpu_pycloud_format лежит в ai/, поэтому проверяем оттуда (без -I, чтобы текущая папка была в пути поиска)
    $mods = (python -c "import importlib.util as u; print(' '.join(m for m in ('pytpu', 'pika', 'tpu_pycloud_format', 'google.protobuf') if u.find_spec(m)))") -split ' '
    Pop-Location
    if ($mods -contains 'pytpu') { return @{ Mode = 'board' } }
    $missing = @()
    if (-not (Get-EnvValue 'LINQ_LOGIN')) { $missing += 'LINQ_LOGIN в .env' }
    foreach ($m in 'pika', 'tpu_pycloud_format', 'google.protobuf') { if ($mods -notcontains $m) { $missing += "библиотека $m" } }
    $broker = Get-EnvValue 'LINQ_BROKER'; if (-not $broker) { $broker = '10.0.114.30' }
    if (-not (Test-NetConnection $broker -Port 5672 -InformationLevel Quiet -WarningAction SilentlyContinue)) { $missing += "брокер $broker недоступен (включите VPN)" }
    if ($missing) { return @{ Mode = $null; Missing = $missing -join '; ' } }
    return @{ Mode = 'cloud' }
}

function Wait-Port($p, $name, $sec = 120) {
    $end = (Get-Date).AddSeconds($sec)
    while (-not (Test-Port $p)) {
        if ((Get-Date) -gt $end) { throw "$name не запустился за $sec с (порт $p). Смотрите его окно." }
        Start-Sleep -Milliseconds 500
    }
}

function Start-Window($title, $dir, $cmd) {
    $script = "`$Host.UI.RawUI.WindowTitle = '$title'; Set-Location -LiteralPath '$dir'; $cmd"
    $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($script))
    Start-Process powershell -ArgumentList '-NoExit', '-NoProfile', '-EncodedCommand', $enc | Out-Null
}

if ($Action -eq 'stop') {
    foreach ($p in $DbPort, $ApiPort, $WebPort, $AiPort) {
        Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue | ForEach-Object {
            taskkill /PID $_.OwningProcess /T /F | Out-Null
        }
    }
    Get-Process powershell -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like 'LinQ *' } | Stop-Process -Force
    if (Test-Docker) { Push-Location $Root; docker compose stop *> $null; Pop-Location }
    'Всё остановлено.'
    return
}

foreach ($p in @{ 'БД' = $DbPort; 'бэкенд' = $ApiPort; 'фронтенд' = $WebPort; 'ИИ-модуль' = $AiPort }.GetEnumerator()) {
    if (Test-Port $p.Value) { throw "Порт $($p.Value) ($($p.Key)) уже занят. Сначала остановите старые процессы: run.bat stop" }
}

$accel = if ($Action -eq 'cpu') { @{ Mode = $null } } else { Get-Accelerator }
$mode = $accel.Mode
if ($Action -eq 'tpu' -and -not $mode) {
    throw "Ускоритель LinQ недоступен. Не хватает: $($accel.Missing). (Либо pytpu, если плата в этом компьютере.) Без ускорителя: run.bat cpu"
}
$login = Get-EnvValue 'LINQ_LOGIN'
$backend = if ($mode) { '--backend tpu' } else { '--backend onnx' }
# удалённая плата: .tpu-программы уже загружены на сервер в /auto/cache/<логин> (через Jupyter), копировать их не нужно
$aiEnv = if ($mode -eq 'cloud') { "`$env:LINQ_LOGIN = '$login'; `$env:LINQ_REMOTE_CACHE = '/auto/cache/$login'; " } else { '' }
if ($mode -eq 'board') { 'ИИ: ускоритель LinQ (плата в этом компьютере)' }
elseif ($mode -eq 'cloud') { 'ИИ: ускоритель LinQ (удалённый, по VPN)' }
elseif ($Action -eq 'cpu') { 'ИИ: процессор (ONNX), по запросу' }
else { "ИИ: процессор (ONNX). Ускоритель не найден, не хватает: $($accel.Missing)" }

# 1. База данных: Docker, если он есть и запущен, иначе PGlite (Postgres на Node.js, данные в localdb/data)
if (Test-Docker) {
    'БД: docker compose up -d'
    Push-Location $Root; docker compose up -d; Pop-Location
} else {
    'БД: PGlite (Docker не найден)'
    if (-not (Test-Path "$Root\localdb\node_modules")) {
        Push-Location "$Root\localdb"; npm install --no-audit --no-fund; Pop-Location
    }
    Start-Window 'LinQ БД' "$Root\localdb" "node node_modules/@electric-sql/pglite-socket/dist/scripts/server.js --db=./data --port $DbPort --host 127.0.0.1 --max-connections 5"
}
Wait-Port $DbPort 'БД' 60

# 2. Бэкенд (схему и демо-данные создаёт сам при первом запуске)
'Бэкенд: установка зависимостей...'
python -m pip install -q -r "$Root\requirements.txt"
Start-Window 'LinQ бэкенд' $Root "python -m uvicorn main:app --port $ApiPort --reload"
Wait-Port $ApiPort 'Бэкенд' 60

# 3. Фронтенд
if (-not (Test-Path "$Root\frontend\node_modules")) {
    'Фронтенд: npm install (первый раз, около минуты)...'
    Push-Location "$Root\frontend"; npm install --no-audit --no-fund; Pop-Location
}
Start-Window 'LinQ фронтенд' "$Root\frontend" "npm run dev -- --host 127.0.0.1 --port $WebPort"
Wait-Port $WebPort 'Фронтенд' 60

# 4. ИИ-модуль: берёт с сайта камеры и правила, присылает нарушения, отдаёт видео с разметкой на :8001
Start-Window 'LinQ ИИ' "$Root\ai" "${aiEnv}python -m safetyvision bridge configs/site_bridge.yaml $backend"

Start-Process "http://127.0.0.1:$WebPort"
@"

Готово. Сайт:  http://127.0.0.1:$WebPort
Вход:          it_linq_admin / linq123  (или mikhalyich_ot, disp_smena1, master_ceh1)
Swagger API:   http://127.0.0.1:$ApiPort/docs
ИИ-модулю нужна минута на загрузку моделей; пока он не готов, камеры в сайте "не в сети".
Остановить:    run.bat stop
"@
