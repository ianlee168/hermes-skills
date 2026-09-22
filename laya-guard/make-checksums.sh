#!/usr/bin/env bash
# 生成"跨机对账清单"：文件名 + sha256（LF 规范内容），供任意机器在无 SSH 的情况下核对副本。
#
# 用法: ./make-checksums.sh [输出路径]      # 默认打到 stdout
# 要点:
#   ① 指纹一律按 **LF 内容** 计算（不受 Windows 检出时的 CRLF 转换影响）
#   ② 不写任何绝对路径、不写任何 secret 原文
#   ③ 仓库里已加 .gitattributes（laya-guard/** text eol=lf），Windows 检出也会是 LF
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-/dev/stdout}"
HERMES_HOME_DIR="${HERMES_HOME:-$HOME/.hermes}"
KEYFILE="$HERMES_HOME_DIR/secrets/typesafe-jev.key"

lf_sha() {  # 把 CRLF 视作 LF 来算指纹
  python3 - "$1" <<'PY'
import hashlib, sys, pathlib
b = pathlib.Path(sys.argv[1]).read_bytes().replace(b"\r\n", b"\n")
print(hashlib.sha256(b).hexdigest())
PY
}

{
  echo "# 对账清单（跨机核对副本一致性用）"
  echo "# 生成: $(hostname) $(date '+%F %T %Z')"
  echo "# 取法: 见仓库 INSTALL.md；指纹一律按 LF 规范内容计算（Windows 检出是 CRLF，请用下面的命令自算）"
  echo "#   git cat-file -p HEAD:<path> | sha256sum     ← 不受工作区换行转换影响"
  echo "#   python3 -c \"import hashlib,pathlib,sys;b=pathlib.Path(sys.argv[1]).read_bytes().replace(b'\\\\r\\\\n',b'\\\\n');print(hashlib.sha256(b).hexdigest())\" <file>"
  echo
  if [ -f "$KEYFILE" ]; then
    echo "## 云端 key（规范字节形态：无尾部换行；sha256 不可逆，公开校验和不构成泄露）"
    echo "$(lf_sha "$KEYFILE")  $(basename "$KEYFILE")"
    echo
  fi
  echo "## 包内容（LF 规范内容）"
  (cd "$HERE" && find . -type f ! -path "./.git/*" ! -name "*.pyc" ! -path "*__pycache__*" \
      | sort | while read -r f; do echo "$(lf_sha "$HERE/${f#./}")  ${f#./}"; done)
} > "$OUT"

[ "$OUT" = "/dev/stdout" ] || echo "写到 $OUT（$(grep -c '^[0-9a-f]\{64\}' "$OUT") 条指纹）" >&2
