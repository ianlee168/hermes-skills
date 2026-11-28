# 本地核心补丁参考（现路径版，取代 161 上那份旧路径文档）

旧文档：`161:~/.hermes/profiles/webui-hermes/skills/.archive/hermes-webui-ops/references/local-core-patches.md`
（2026-11-28 副本已拉回本机核对）。其中 `gateway/platforms/weixin.py`、
`tools/cronjob_prompt_scan.py` 两条路径已不存在，本文用当前路径重写。

## 补丁 1：weixin channel_prompts + 会话过期 5 秒

文件 `plugins/platforms/weixin/adapter.py`

```python
from gateway.platforms.base import (
    _IMAGE_EXTS, _VIDEO_EXTS, gateway_trust_env, BasePlatformAdapter, SendResult, describe_proxy_error, env_proxy_for_redaction,
    cache_audio_from_bytes_async, cache_document_from_bytes_async, cache_image_from_bytes_async,
    resolve_channel_prompt,
)
```

inbound 事件（`_process_message`，`MessageEvent(` 约 918 行）：

```python
            message_id=message_id or None, media_urls=media_paths, media_types=media_types, timestamp=datetime.now(),
            channel_prompt=resolve_channel_prompt(self.config.extra, effective_chat_id, None))
```

会话过期分支（`_poll_loop`，约 833 行）：

```python
                        logger.error("[%s] Session expired; pausing for 5 seconds", self.name)
                        await asyncio.sleep(5)
```

## 补丁 2：cron strict 扫描先剥 Markdown 代码

文件 `cron/prompt_scan.py`（上游把扫描器从 `tools/cronjob_tools.py` 重构到了这里）

```python
_FENCED_CODE_RE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def _strip_doc_code_blocks(prompt: str) -> str:
    """Drop markdown fenced/inline code so pasted docs don't trip the strict prompt scan."""
    return _INLINE_CODE_RE.sub(" ", _FENCED_CODE_RE.sub(" ", prompt))
```

并且在 `_scan_cron_prompt()` 的最后一行调用：

```python
    return _first_pattern_error(_strip_doc_code_blocks(prompt), _CRON_THREAT_PATTERNS, _CRON_EXFIL_COMMAND_PATTERNS)
```

注意 invisible-unicode 检查仍用**原始** prompt（不要剥，否则 \u200b 藏在代码块里就漏检）。

## 历史教训（保留）

- 2026-05-25：autostash 后补丁丢 4 个月没人发现 → 现在必须用行为探针验，不看 `git status` 就结账。
- 2026-09-14：上游真改了 `weixin/adapter.py`，cron 里裸 `git pull --ff-only` 撞脏树 → `set -e`
  在写日志前退出，08:00/12:04 两轮 auto-update 静默全挂。用 `hermes update`（内部 autostash →
  pull → 恢复改动）才安全。
- 2026-11-25：update 后补丁再次全丢，2026-11-28 按新路径重打并落了本 skill + 自动探针脚本。
