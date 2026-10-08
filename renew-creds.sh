#!/usr/bin/env bash
# 本地续期启动器：每 7 天刷新明文凭据并推送进 GitHub Secret
# 设计要点：
#  - 复用 export_creds.py 解密（不重写解密逻辑）；--write 才真正写出本地明文凭据
#  - 推送用 gh CLI（负责 Secret 加密），gh 须已登录（gh auth login --with-token）
#  - Python 解释器用 command -v 动态解析（含 Store 桩跳过 + 托管 Python 兜底）
set -euo pipefail

# 任务计划程序环境通常没有代理变量；本机走公司安全代理 127.0.0.1:25920 才能连 GitHub。
# 仅当环境未设置代理时才兜底填入，交互式运行（已带代理）不受影响。
if [ -z "${HTTPS_PROXY:-}" ] && [ -z "${HTTP_PROXY:-}" ]; then
  export HTTPS_PROXY="http://127.0.0.1:25920"
  export HTTP_PROXY="http://127.0.0.1:25920"
fi

PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  BASE="${USERPROFILE:-$HOME}/.workbuddy/binaries/python/versions"
  for d in "$BASE"/*/; do
    [ -x "${d}python.exe" ] && PY="${d}python.exe" && break
  done
fi
[ -z "$PY" ] && { echo "ERROR: 未找到 Python 解释器" >&2; exit 1; }

GH="$(command -v gh || echo 'C:/Users/huawei/.workbuddy/binaries/gh/bin/gh.exe')"

# 续期推送目标仓库（必须是你的 fork，不能推到上游 88lin）
REPO="liang007007/workbuddy-auto-signin"

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRET_FILE="${USERPROFILE:-$HOME}/.workbuddy/secrets/workbuddy-plaintext.info"
LOG="$DIR/renew.log"
exec >> "$LOG" 2>&1

# 1) 刷新本地明文凭据（复用项目解密；--write 才写文件）
#    WorkBuddy 客户端改写令牌文件时会短暂持排他锁，加重试（最多 ~2 分钟）避免偶发失败把整轮续期搞挂
for i in $(seq 1 20); do
  if "$PY" "$DIR/export_creds.py" --write; then
    break
  fi
  echo "[renew] export attempt $i 失败，6s 后重试..." >&2
  sleep 6
done

# 2) 推送进 GitHub Secret（gh 负责加密；gh 须已登录）
"$GH" auth status >/dev/null 2>&1 || {
  echo "ERROR: gh 未登录，无法推送 Secret（请先：gh auth login --with-token <PAT>）" >&2
  exit 1
}
"$GH" secret set WORKBUDDY_PLAIN_CREDS -R "$REPO" < "$SECRET_FILE"
echo "renew done: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
