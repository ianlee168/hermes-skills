# 2026-05-25 日常维护记录

## BBS 重装 (2026-05-25)

### 原因
之前装的容器版本混用（nodebb_build + nodebb_install + 官方 latest 混在一起），配置冲突，500 错误无法进入。

### 操作
1. 删除所有 nodebb 相关容器 + 卷 + 网络：
```bash
docker stop nodebb nodebb-install nodebb-build nodebb-redis nodebb-mongo 2>/dev/null
docker rm nodebb nodebb-install nodebb-build nodebb-redis nodebb-mongo 2>/dev/null
docker volume rm nodebb_app nodebb_nodebb nodebb_nodebb_build nodebb_nodebb_data 2>/dev/null
docker network rm nodebb_net nodebb_nodebb-net root_nodebb-net 2>/dev/null
```

2. 重建：
```bash
docker network create nodebb_net
docker run -d --name nodebb-redis --network nodebb_net \
  -v /mnt/user/appdata/nodebb-redis:/data --restart always redis:7-alpine
docker pull ghcr.io/nodebb/nodebb:4.11.3
docker run -d --name nodebb --network nodebb_net \
  -p 4567:4567 \
  -v /mnt/user/appdata/nodebb:/data \
  -v /mnt/user/appdata/nodebb/config:/opt/config:rw \
  -e 'NODEBB_URL=http://192.168.50.1:4567' \
  --restart always ghcr.io/nodebb/nodebb:4.11.3
```

3. 预写 config.json（关键！必须挂载 /opt/config 为可写）：
```bash
cat > /mnt/user/appdata/nodebb/config/config.json << 'EOF'
{
  "url": "http://192.168.50.1:4567",
  "secret": "a55a2f1eb9427de80ce69f95b2aad8011c9051fd8273feaa",
  "database": "redis",
  "redis": {
    "host": "nodebb-redis",
    "port": 6379,
    "password": "",
    "database": 0
  }
}
EOF
```

4. 重启让配置生效：
```bash
docker restart nodebb && sleep 5
```

5. 通过浏览器完成安装向导（http://192.168.50.1:4567/install）

### 当前状态 (2026-05-25 17:00)
- 4.11.3 镜像已拉好
- Redis 连接正常
- NodeBB 启动成功
- **但有 webpack bug**：`topicThumbs.js` require('composer') 找不到模块，所有页面 500
- 需要 `./nodebb build` 重建资源，但需要先停 NodeBB

### Redis 数据（重建后）
```bash
docker exec nodebb-redis redis-cli DBSIZE   # 0（空库，需重新走安装向导）
```

## Cron 清理
- 移除了 x-nonmutuals.py cron（xurl PATH 问题已修复到脚本内，但 DNS 解析 api.x.com 超时，任务本身暂停）
- 其他 cron（backup、gbrain-backup、daily_news、frigate 等）保持正常

## gbrain 状态
- v0.38.2.0，schema v85
- ZEROENTROPY_API_KEY 未配置（语义嵌入需要）
- 健康分 55/100