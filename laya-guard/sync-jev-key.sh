#!/usr/bin/env bash
# 从脑里同步 TypeSafe Jev API key 到 600 文件（供 laya-guard 服务读）。
# 为什么这么做：key 的权威副本在脑里（concepts/typesafe-jev-api-key），
# 服务不能每次调用都起 bun（太慢），也不能让 key 出现在 agent 上下文里。
# 本脚本只把 key 从脑 → 600 文件，全程不打印内容。
set -uo pipefail

HERMES_DIR="${HERMES_HOME:-$HOME/.hermes}"
SECRETS="$HERMES_DIR/secrets"
OUT="$SECRETS/typesafe-jev.key"
GBRAIN_DIR="${GBRAIN_DIR:-$HOME/.hermes/skills/gbrain}"
SLUG="concepts/typesafe-jev-api-key"

# systemd / cron 的环境里 PATH 很干净，bun 常找不到 —— 显式补齐常见位置
PATH="$HOME/.bun/bin:$HOME/.hermes/node/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin${PATH:+:$PATH}"
export PATH
BUN="$(command -v bun 2>/dev/null || true)"
if [ -z "$BUN" ]; then
  for c in "$HOME/.bun/bin/bun" "$HOME/.hermes/node/bin/bun" /usr/local/bin/bun /usr/bin/bun; do
    [ -x "$c" ] && BUN="$c" && break
  done
fi
if [ -z "$BUN" ]; then
  echo "skip: 本机找不到 bun（脑是 TS 源码跑的，没 bun 读不了）" >&2
  exit 1
fi

mkdir -p "$SECRETS" && chmod 700 "$SECRETS"

if [ ! -d "$GBRAIN_DIR" ]; then
  echo "skip: 找不到脑目录 $GBRAIN_DIR" >&2
  exit 1
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp" "$tmp.out" "$tmp.err"' EXIT
if ! (cd "$GBRAIN_DIR" && timeout 240 "$BUN" src/cli.ts get "$SLUG" >"$tmp" 2>"$tmp.err"); then
  echo "error: 从脑里读 $SLUG 失败；bun=$BUN 目录=$GBRAIN_DIR" >&2
  head -3 "$tmp.err" >&2 || true
  exit 1
fi

grep -oE 'apikey_[0-9a-f]+_[0-9a-f]+' "$tmp" | head -1 > "$tmp.raw"
# 规范字节形态：**不带尾部换行**（sha256 = 54d7fd29f7c5a121…，跨机对账时唯一形态）。
# 注意不要写成"尾换行会 401" —— 实测：客户端会先报错（Python urllib 直接 ValueError），
# curl 真把 \n 塞进头是 422；**401 的真因是截断/掩码副本**（实测把 key 砍一半 → 401）。
# 之所以还要规范化，只为对账不歧义（带换行 sha256 会变成 dd6de919…）。
printf '%s' "$(cat "$tmp.raw")" > "$tmp.out"
rm -f "$tmp.raw"
if [ -s "$tmp.out" ]; then
  install -m 600 "$tmp.out" "$OUT"
  echo "synced $(wc -c < "$OUT") bytes -> $OUT (sha256 $(sha256sum "$OUT" | cut -c1-16)…)"
else
  echo "error: 脑里那条 page 没有 apikey_ 字段" >&2
  exit 1
fi
