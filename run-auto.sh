#!/usr/bin/env bash
# WorkBuddy 每日自动签到启动器（本机定时任务入口）
# 设计要点：
#  - Python 解释器用 command -v 动态解析，绝不写死版本号
#  - 跳过 Microsoft Store 桩（WindowsApps 下的 python3 是“打开商店”重定向，非真解释器）
#  - 兜底：扫描 WorkBuddy 托管 Python 的 versions 目录（glob，不写死具体版本号）
#  - 本机与云端跑的是同一套 signin.py；本机靠客户端运行时解密 sym-v1 凭据
#  - auto = 签到 + 成长中心（派 Buddy / 领礼物 / 任务等），输出追加到本地日志
set -euo pipefail

PY=""

# 1) 系统 PATH 里的解释器（动态取），但跳过 Microsoft Store 桩
for c in python3 python; do
  p="$(command -v "$c" 2>/dev/null || true)"
  [ -z "$p" ] && continue
  case "$p" in
    *WindowsApps* | *Microsoft/WindowsApps* | *Microsoft\\WindowsApps*) continue ;;
  esac
  PY="$p"
  break
done

# 2) 兜底：WorkBuddy 托管的真实 Python（glob 版本目录，不写死版本号）
if [ -z "$PY" ]; then
  BASE="${USERPROFILE:-$HOME}/.workbuddy/binaries/python/versions"
  for d in "$BASE"/*/; do
    if [ -x "${d}python.exe" ]; then
      PY="${d}python.exe"
      break
    fi
  done
fi

if [ -z "$PY" ]; then
  echo "ERROR: 未找到可用的 Python 解释器（已排除 Microsoft Store 桩，且 $BASE 下也无 python.exe）" >&2
  exit 1
fi

# 脚本所在目录，无论从哪个工作目录调用都正确
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$DIR/signin.local.log"

exec "$PY" "$DIR/signin.py" auto >> "$LOG" 2>&1
