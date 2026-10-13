# Shell 引号嵌套截断 & 安全远程执行

## 问题

通过 SSH 执行 Docker 容器内命令时，3 层以上引号嵌套（SSH → bash → docker → node）频繁导致 bash 截断字符串：

```bash
ssh root@nas 'docker exec nodebb sh -c "node -e \"console.log(1)\""' 
#   ^SSH^    ^docker         ^sh    ^node        ^node code
# 3层嵌套，很容易写错
```

常见症状：命令报 `unexpected EOF while looking for matching`、`Invalid or unexpected token`、API Key 截断。

## 解决方案：写文件 → 管道执行（0 层嵌套）

### 方式 1：write_file + cat 管道（推荐）

```python
from hermes_tools import write_file, terminal

# 1. 在本地写好脚本
write_file("/tmp/script.js", """内容""")

# 2. cat 到 SSH 管道（不需要任何嵌套引号）
terminal("cat /tmp/script.js | ssh root@nas 'docker exec -i nodebb node'")
```

对于多行内容或需要精确二进制数据的场景：

```bash
# 先传文件到 NAS
scp /tmp/script.js root@nas:/tmp/
# 然后在 NAS 上读文件
ssh root@nas 'cat /tmp/script.js | docker exec -i nodebb node'
```

### 方式 2：execute_code 里用 terminal()（自动处理转义）

```python
from hermes_tools import terminal
script = """const x = 1; console.log(x);"""
terminal(f"echo '{script}' | ssh ...", ...)
```

### 方式 3：printf 避免变量替换

```bash
printf '%s' 'SG.API...KEY' | docker exec -i nodebb-redis redis-cli -x HSET config "key"
```

### 方式 4：echo 管道（适合不含特殊字符的短数据）

```bash
echo 'simple string' | docker exec -i container command
```

## 避免设密码时截断

```bash
# ❌ 危险！可能被 bash 截断
docker exec nodebb-redis redis-cli HSET config 'pass' 'SG.xxx...xxx'

# ✅ 安全！通过文件管道传入
echo 'SG.xxx...xxx' | docker exec -i nodebb-redis redis-cli -x HSET config 'pass'
```

## 总结

写文件 → cat 管道 = 0 层嵌套，绝对不会截断。
