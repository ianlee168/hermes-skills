#!/bin/bash
# HA 更新/还原就绪监视器: /api 返回 401 = 实例带着原用户账户就绪(还原完成)。
# 用法: 后台跑 + notify_on_complete=true,退出时收通知;不用人盯。
#   terminal(background=true, notify_on_complete=true): bash ha-ready-watch.sh [host]
# 状态语义: 307 = 更新/还原页;000 = 核心切换窗口;401 = 就绪。
HOST="${1:-192.168.50.206}"
for i in $(seq 1 200); do
  c=$(curl -s -o /dev/null -w "%{http_code}" -m 8 "http://${HOST}:8123/api/" 2>/dev/null)
  echo "t=$((i*30))s /api -> ${c:-000}"
  if [ "$c" = "401" ]; then echo "HA_READY_AT_T=$((i*30))s"; exit 0; fi
  sleep 30
done
echo "HA_NOT_READY_TIMEOUT_100min"; exit 1
