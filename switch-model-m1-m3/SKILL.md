---
name: switch-model-m1-m3
category: devops
description: 一键切换 Hermes 模型：M1=Minimax（中国站），M3=DeepSeek。用户只要说 M1 或 M3 就自动切换并重启 gateway。
version: 1.0.0
author: ianlee168
platforms: [linux]
tags: [hermes, model-switch, minimax, deepseek, m1, m3]
---

# switch-model-m1-m3 — 一键切换 Hermes 模型（含 Telegram + 微信）

用户只要说 **M1** 或 **M3** 就自动切换模型并重启 gateway。

- **M1** = MiniMax-M3（中国站），走 Telegram + 微信
- **M3** = DeepSeek，走 Telegram + 微信

一键切换后 gateway 会重启（包含所有消息平台），telegram 和微信都会随 gateway 一起自动重连，不需要额外操作。

## 快速命令

在终端执行以下命令即可切换（不需要重启 VM / Docker）：

### M1 → MiniMax-M3（中国站）

```bash
cd ~/.hermes/hermes-agent && \
venv/bin/python3 -m hermes_cli.main --profile webui-hermes config set model.default MiniMax-M3 && \
venv/bin/python3 -m hermes_cli.main --profile webui-hermes config set model.provider minimax-cn && \
venv/bin/python3 -m hermes_cli.main --profile webui-hermes config set model.base_url https://api.minimaxi.com/anthropic && \
pkill -f 'hermes_cli.*gateway'; sleep 3; \
venv/bin/python3 -m hermes_cli.main --profile webui-hermes gateway run --replace &
```

### M3 → DeepSeek

```bash
cd ~/.hermes/hermes-agent && \
venv/bin/python3 -m hermes_cli.main --profile webui-hermes config set model.default deepseek-chat && \
venv/bin/python3 -m hermes_cli.main --profile webui-hermes config set model.provider deepseek && \
venv/bin/python3 -m hermes_cli.main --profile webui-hermes config set model.base_url https://api.deepseek.com/v1 && \
pkill -f 'hermes_cli.*gateway'; sleep 3; \
venv/bin/python3 -m hermes_cli.main --profile webui-hermes gateway run --replace &
```

## 当前配置

| 配置 | M1（MiniMax-M3） | M3（DeepSeek） |
|------|-----------------|----------------|
| model.default | `MiniMax-M3` | `deepseek-chat` |
| model.provider | `minimax-cn` | `deepseek` |
| model.base_url | `https://api.minimaxi.com/anthropic` | `https://api.deepseek.com/v1` |
| api_mode | anthropic_messages | chat_completions |
| env key | `MINIMAX_CN_API_KEY`（中国站） | `DEEPSEEK_API_KEY` |

## 注意事项

- `minimax-cn` provider 使用 **Anthropic 协议**（api_mode=anthropic_messages），base_url 是 `https://api.minimaxi.com/anthropic`
- `deepseek` provider 使用 **OpenAI 协议**（chat_completions），base_url 是 `https://api.deepseek.com/v1`
- 切换后 gateway 会自动重启，大约需要 10-15 秒
- 如果切换后 telegram 无响应，检查 `~/.hermes/profiles/webui-hermes/logs/gateway.log` 和 `agent.log`

## 验证

```bash
# 查看当前运行的模型
grep -A3 '^model:' ~/.hermes/profiles/webui-hermes/config.yaml

# 检查 gateway 状态
ps aux | grep 'hermes_cli.*gateway' | grep -v grep
```
