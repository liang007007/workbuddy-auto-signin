#!/usr/bin/env python3
# export_creds.py - 把本机加密凭据解密为“明文凭据文件”，供云端无客户端环境使用
#
# 安全约束（来自需求）：
#  - 默认只做“检查模式”(dry-run)：不写出任何文件，只报告将要写什么
#  - 加 --write 才真正写出文件（需人工确认后才会用到）
#  - 绝不以任何形式打印 / 记录 / 转发 accessToken 明文
#  - 写出文件权限 600，且必须落在 git 仓库之外（默认 USERPROFILE/.workbuddy/secrets/）
#  - 解密严格复用 signin.py 的 resolve_session（含 sym-v1 客户端运行时解密），不重写解密逻辑
#
# 云端那份凭据只需三个字段：auth.accessToken / auth.endpoint / account.uid
import os
import sys
import json
import base64
import argparse
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import signin  # noqa: E402


def _mask(s, keep=4):
    if not s:
        return "<empty>"
    return s[:keep] + "…(len=%d)" % len(s)


def _try_jwt_exp(token):
    # 本工具用的 accessToken 不含 '.'（见 signin._valid_token 字符集），通常不是 JWT；
    # 这里仅做尽力解析，解析失败返回 None（表示无法从 token 读到期时间）。
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        pad = "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
        exp = payload.get("exp")
        if isinstance(exp, (int, float)):
            return exp
    except Exception:
        return None
    return None


def _is_outside_git(path):
    d = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.isdir(os.path.join(d, ".git")):
            return False
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return True


def _harden_perms(path):
    # 先按需求设置 600
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    # Windows 上再尽力用 icacls 收掉继承并仅授予当前用户，确保真正“仅本人可读写”
    if sys.platform.startswith("win"):
        try:
            import subprocess
            subprocess.run(
                ["icacls", path, "/inheritance:r", "/grant:r",
                 "%s:(R,W)" % os.environ.get("USERNAME", "BUILTIN\\Users")],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description="导出 WorkBuddy 明文凭据（默认检查模式）")
    ap.add_argument("--write", action="store_true", help="真正写出明文凭据文件（默认仅检查模式）")
    ap.add_argument("--out", default=None, help="输出路径（默认 USERPROFILE/.workbuddy/secrets/workbuddy-plaintext.info）")
    args = ap.parse_args()

    auth_file, looked_in = signin.find_auth_file()
    if not auth_file or not os.path.exists(auth_file):
        print(json.dumps({"result": "NO_AUTH", "looked_in": looked_in, "needs_attention": True},
                         ensure_ascii=False))
        return 2

    try:
        session = signin.load_session_retry(auth_file)
        kind = signin._token_format(session["auth"]["accessToken"])
        resolved = signin.resolve_session(session)  # 复用项目解密，得到明文 accessToken
    except signin.AuthError as e:
        print(json.dumps({"result": "AUTH_ERROR", "report": str(e), "needs_attention": True},
                         ensure_ascii=False))
        return 1

    token = resolved["auth"]["accessToken"]
    endpoint = (resolved.get("auth") or {}).get("endpoint")
    uid = (resolved.get("account") or {}).get("uid")

    out_path = args.out or os.path.join(
        os.environ.get("USERPROFILE", os.path.expanduser("~")),
        ".workbuddy", "secrets", "workbuddy-plaintext.info")

    exp = _try_jwt_exp(token)
    summary = {
        "result": "EXPORT_READY",
        "credential_format": kind,
        "endpoint": endpoint,
        "uid_masked": _mask(uid, 4) if uid else None,
        "token_len": len(token),
        "token_is_jwt": exp is not None,
        "expires_at": (datetime.datetime.fromtimestamp(exp, datetime.timezone.utc).isoformat() if exp else None),
        "out_path": out_path,
        "outside_git_repo": _is_outside_git(out_path),
        "mode": "WRITE" if args.write else "CHECK(dry-run)",
        "needs_attention": False,
    }
    # 关键：summary 中绝不出现 accessToken 明文
    print(json.dumps(summary, ensure_ascii=False))

    if not args.write:
        print("[检查模式] 未写出任何文件。确认无误后加 --write 才会真正生成（并请在授权后再用于云端）。",
              file=sys.stderr)
        return 0

    # WRITE 模式：仅写出云端所需的最小字段，避免携带无关敏感字段
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plaintext_creds = {
        "auth": {"accessToken": token, "endpoint": endpoint},
        "account": {"uid": uid},
    }
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(plaintext_creds, f, ensure_ascii=False)
    _harden_perms(tmp)
    os.replace(tmp, out_path)  # 原子替换，避免半截文件
    _harden_perms(out_path)
    print("[已写出] %s (权限 600, git 仓库外=%s)" % (out_path, _is_outside_git(out_path)),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
