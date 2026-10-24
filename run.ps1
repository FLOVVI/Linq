# LinQ (Windows PowerShell): .\run.ps1 — меню; или .\run.ps1 cpu | tpu | auto | noai | check | stop. Вся логика — в run.py
if (Get-Command py -ErrorAction SilentlyContinue) { py -3 "$PSScriptRoot\run.py" @args }
elseif (Get-Command python -ErrorAction SilentlyContinue) { python "$PSScriptRoot\run.py" @args }
else { Write-Host "Не найден Python. Поставьте Python 3.13 (64-bit) с https://www.python.org/downloads/windows/ — в установщике отметьте «Add python.exe to PATH»." }
