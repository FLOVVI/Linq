#!/bin/sh
# macOS: двойной щелчок в Finder — откроется Терминал с меню запуска LinQ (то же, что ./run.sh)
cd "$(dirname "$0")" || exit 1
sh ./run.sh "$@"
code=$?
printf '\nНажмите Enter, чтобы закрыть окно…'
read -r _
exit $code
