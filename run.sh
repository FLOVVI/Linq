#!/bin/sh
# LinQ одной командой (Linux, macOS): ./run.sh [cpu|tpu|noai|stop] — вся логика в run.py
cd "$(dirname "$0")" || exit 1
for py in python3.12 python3.11 python3.13 python3.10 python3 python; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
    exec "$py" run.py "$@"
  fi
done
echo "Нужен Python 3.10+: https://www.python.org/downloads/" >&2
exit 1
