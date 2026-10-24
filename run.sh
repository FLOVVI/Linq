#!/bin/sh
# LinQ (Linux, macOS): ./run.sh — меню; или ./run.sh cpu | tpu | auto | noai | check | stop. Вся логика — в run.py
cd "$(dirname "$0")" || exit 1
for py in python3.12 python3.13 python3.11 python3.14 python3.10 python3 python; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 8))' 2>/dev/null; then
    exec "$py" run.py "$@"
  fi
done
echo "Не найден Python 3. Поставьте Python 3.13:" >&2
echo "  macOS:  brew install python@3.13   или установщик с https://www.python.org/downloads/macos/" >&2
echo "  Linux:  sudo apt install python3 python3-venv   (Ubuntu, Debian)" >&2
exit 1
