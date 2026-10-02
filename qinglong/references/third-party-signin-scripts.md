# 第三方多平台签到脚本库部署(ql-script-hub 类)

适用: 用户拿来一个 GitHub 脚本库(如 agluo/ql-script-hub——16 个平台各一个 py:夸克/恩山/什么值得买/NodeSeek/顺丰/阿里云盘/贴吧/NGA/ikuuu/天翼云盘…),要挑着装进青龙。

## 1. 先按"用户真有账号的平台"筛选,别整库拉

- 整库拉 = 一堆跑不了的任务,每个还要配凭据,维护负担大
- 做法: 把脚本清单整理成表(**平台 + 需要什么凭据**)发给用户,让他报编号/名字,只下载选中的那几个
- ⚠️ 需要**账号密码**的脚本(如天翼云盘 TY_USERNAME/TY_PASSWORD、ikuuu 邮箱密码)要明文存 env,风险高 → 提醒用户或跳过;cookie/token 类相对可控

## 2. 落地到子目录(不要摊在 scripts 根)

```bash
mkdir -p /mnt/user/appdata/qinglong/scripts/<hub名>   # 宿主机即容器 /ql/data/scripts
cd /mnt/user/appdata/qinglong/scripts/<hub名>
curl -sL -o <script>.py "https://raw.githubusercontent.com/<owner>/<repo>/master/<script>.py"
```
任务命令写 `task <hub名>/<script>.py`(相对 scripts 根)。
⚠️ 文件名以**仓库文件列表**为准,别信 README 目录结构里的旧名字(常对不上)。

## 3. ⚠️ 必须复制 notify.py 进子目录

子目录脚本 `from notify import send` 会静默失败,日志头出现 `⚠️ 未加载通知模块,跳过通知功能` —— **Python 的 sys.path[0] 是脚本所在目录**,找不到 scripts 根目录的 notify.py:

```bash
docker exec qinglong cp /ql/data/scripts/notify.py /ql/data/scripts/<hub名>/notify.py
```

复跑后日志头应显示 `✅ 已加载notify.py通知模块`。注意这是**副本**,青龙 notify.py 大版本更新时手动同步一次。

## 4. 逐脚本自检依赖 + 环境变量名

```bash
# 依赖(滤掉标准库后看剩下什么——剩下的才是要装的)
grep -E "^\s*(import|from) " <script>.py \
  | grep -vE "^(\s*)(import|from) (os|sys|json|time|re|random|datetime|hashlib|base64|urllib|typing|logging|traceback|uuid|math|collections)"
# 环境变量
grep -oE "os\.(environ\.get|getenv)\(['\"][A-Za-z_0-9]+['\"]" <script>.py
```

- 缺包: `docker exec qinglong pip3 install <pkg> -i https://pypi.tuna.tsinghua.edu.cn/simple`(实测 `curl_cffi` 是这类库的常见缺项)
- **变量名各脚本不统一**(同库里有 `QUARK_COOKIE` / `enshan_cookie` / `SMZDM_COOKIE` / `sfsyUrl` …),一律从脚本里 grep,**别按 README 猜**
- grep 不到时,变量名可能藏在常量里: 搜 `ENV_NAME =`(如顺丰脚本 `ENV_NAME = 'sfsyUrl'`)
- 库自带的随机化变量是共用的: `RANDOM_SIGNIN` / `MAX_RANDOM_DELAY`

## 5. 建任务:`POST /api/crons` 要单个对象

body 是**单个对象**,包数组会报 `"value" must be of type object`(与 `POST /api/envs` 要数组**刚好相反**)。多任务逐个 POST —— 用 python + urllib 循环最省事,顺带绕开中文名在 shell 里的编码坑:

```python
call("POST", "/api/crons",
     {"name": "夸克网盘签到", "command": "task qlhub/quark_signin.py", "schedule": "0 8 * * *"},
     token)
```
schedule 相互错开 5-10 分钟,别全挤同一个点。

## 6. 随机延迟的含义

库常带 `RANDOM_SIGNIN`(默认 true)+ `MAX_RANDOM_DELAY`(默认 3600 秒): 脚本启动后**随机等最多 1 小时**再签到,避免固定时间被平台盯上。**建议保留**;排查时要知道 "日志停在等待 X 分 Y 秒" 不是卡住。手动测速可临时 `RANDOM_SIGNIN=false`。

## 7. 验证顺序

1. 单跑一个(`PUT /api/crons/run` body `["<id>"]`)→ 看日志头: notify 已加载 + 脚本正常启动
2. 没配凭据时应提示"未获取到 XX 环境变量",而不是崩溃
3. 拿到用户凭据后: 建 env(`POST /api/envs` **包数组**)→ 单跑 → 看签到成功行

## 8. 凭据抓取(通用)

cookie 类平台的通用抓法,给用户时直接照抄: 浏览器登录该站 → F12 → Network → 刷新 → 任选请求 → Request Headers 里的完整 `Cookie` 整串复制。多账号按脚本说明的分隔符(cookie 类常见换行或 `&`;注意库内不统一,仍以脚本 grep 结果为准)。
