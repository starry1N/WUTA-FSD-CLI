#!/usr/bin/env bash
# Terminal display adapter; radio startup and single-instance ownership stay upstream.
set -uo pipefail
entry="$1"
mode="$2"
log_file="$3"
action="${4:-run}"
mkdir -p "$(dirname "$log_file")"
exec 9>"$(dirname "$log_file")/terminal.lock"
flock -n 9 || exit 0
if [[ "$action" == follow ]]; then
    printf '%s\n' '查看已有无线发送进程日志；关闭本窗口不会停止后台无线。'
    exec tail -n 80 -F -- "$log_file"
fi
printf '%s\n' 'FSD 无线发送 · Ctrl-C 停止无线；退出 CLI 不关闭本窗口。'
bash "$entry" --mode "$mode" 2>&1 | tee -a "$log_file"
radio_exit_code="${PIPESTATUS[0]}"
printf '\n无线发送程序已退出（退出码=%s）。日志：%s\n按 Enter 关闭窗口。\n' "$radio_exit_code" "$log_file"
read -r _ || true
exit "$radio_exit_code"
