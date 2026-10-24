# LinQ одной командой (Windows PowerShell): .\run.ps1 [cpu|tpu|noai|stop]. Вся логика — в run.py
if (Get-Command py -ErrorAction SilentlyContinue) { py -3 "$PSScriptRoot\run.py" @args }
else { python "$PSScriptRoot\run.py" @args }
