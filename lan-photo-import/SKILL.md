---
name: lan-photo-import
description: Use when 两台 Windows 之间通过局域网搬照片/大文件（无云盘、无需装软件）。含现成服务与坑。
---

# 局域网照片/文件导入（Windows 互相搬）

零安装、浏览器直传：台式机跑接收端，笔记本/手机打开网页拖文件夹。已部署在 50.110：

- 程序：`D:\Tools\photolink\`（`server.py` + `app.html` + 启停 bat + README）
- 落盘：`D:\Photos_Import`
- 地址：`http://192.168.50.110:8787`

## 启动/停止

```
# 启动（脱离当前会话，最小化窗口常驻）
powershell -NoProfile -Command "Start-Process -FilePath 'D:\Tools\photolink\启动照片接收.bat' -WindowStyle Minimized"
# 停止
powershell -NoProfile -Command "& 'D:\Tools\photolink\停止照片接收.bat'"
```

## 验证（每次都要实测，别假设）

```
curl -s --max-time 5 http://127.0.0.1:8787/ping            # 本机
ssh <user>@192.168.50.161 "curl -s --max-time 6 http://192.168.50.110:8787/ping"   # 另一台真机验防火墙
```

## 踩过的坑

1. **防火墙按程序路径放行，不按端口**。必须用 `C:\Users\<user>\AppData\Local\Programs\Python\Python314\python.exe`（该路径在 Public 配置文件下有入站 Any 端口规则）。用 Hermes venv 的 python 或 `C:\python314` 会被拦。以太网网卡是 Public 配置文件，规则正好命中。
2. **`Get-NetTCPConnection -State Listen` 对 0.0.0.0 通配监听返回不稳**（会漏行），杀进程时按端口取所有连接再筛 `ProcessName -like 'python*'`，否则要么杀不掉、要么误杀 chrome 客户端连接。
3. **.bat 必须 CRLF**；写成 LF 时 `for /f`、`timeout` 这类会莫名报错。用 python 统一转 `\r\n`。
4. **MSYS bash 里 `cmd //c "中文名.bat"` 不执行**（只打印 cmd 横幅）。走 `powershell -NoProfile -Command "& 'D:\...\x.bat'"`。
5. **bat 里的 `timeout /t 2` 在 bash 派生的 PATH 下会命中 MSYS 的 `timeout`**，改用 `ping -n 2 127.0.0.1 >nul`。
6. **curl 的 `--data-binary @/d/...`**：原生 curl 不认 MSYS 路径，传 `D:/...`。
7. **上传端设计**：`POST /upload?path=<URL编码相对路径>` + 原始 body 流式写 `.part` 再 `os.replace`；先 `GET /api/has?path=&size=` 判重实现断点/跳过。前端用 XHR（要 upload.onprogress），并发 3。
8. **别把状态渲染成固定文案**：改「保存到子目录」会重渲染列表，renderList 必须按 `it.status` 还原状态，否则已完成项显示回「等待」。

## 替代方案（何时不用它）

- 需要像本地盘一样反复读写、或几百 GB RAW：直接 SMB 共享 + `robocopy /MT:16 /Z`。
- 跨 Mac/手机/无浏览器场景：LocalSend。
