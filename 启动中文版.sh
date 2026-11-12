#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
app_root="${SQUARELINE_APP_DIR:-$task_root}"
cd -- "$app_root"
# Use Chinese GTK dialogs even when launched from a C.UTF-8 terminal.
# Numeric parsing remains controlled by the application's existing culture setup.
exec env -u LC_ALL LANG=zh_CN.UTF-8 LANGUAGE=zh_CN:zh LC_MESSAGES=zh_CN.UTF-8 \
  "$app_root/SquareLine_Studio.x86_64" "$@"
