---
name: crawl4ai
description: Use when crawling pages for LLM or asked about crawl4ai.
version: 1.0.0
author: Hermes Agent (50.110)
platforms: [linux, macos, windows]
tags: [crawler, scraper, llm, markdown, rag, playwright, web-scraping]
metadata:
  hermes:
    triggers: ["crawl4ai", "爬虫", "scraper", "web crawl", "LLM-ready markdown",
               "抓网页喂 LLM", "RAG 数据抓取", "页面转 markdown"]
    related_skills: [blocked-page-recovery]
---

# Crawl4AI — LLM-friendly Web Crawler & Scraper

## 是什么(2026-09 评估)

开源(Apache-2.0)Python 爬虫库,定位 = **把网页转成干净、LLM-ready 的
Markdown 或结构化 JSON 喂给 RAG/Agent/数据管线**。GitHub 81.4k+ stars、
8.4k forks,是 star 最高的开源爬虫;Firecrawl 的"不花钱版"替代品。
底层 = Playwright(+ Patchright 隐身补丁)驱动真实浏览器渲染 JS,再清洗
输出。自带 CLI(`crwl`)、Docker API 服务(监控面板/playground)、MCP server。

选型判断:静态页/纯 API 页面别用它(httpx/requests + selectolax 快一个
量级);要跑 JS 渲染 + 干净 markdown 喂 AI → 它同类最省事;高反爬商业
抓取 → 考虑托管服务(Scrapfly 等)或自备住宅代理。

## 安装

```bash
pip install -U crawl4ai
crawl4ai-setup        # 装 Chromium 等
crawl4ai-doctor       # 验证(会真爬一次,~15s)
# 手动兜底: python -m playwright install --with-deps chromium
```

## 快速上手

```python
import asyncio
from crawl4ai import *

async def main():
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url="https://example.com")
        print(result.markdown)   # 干净 markdown

asyncio.run(main())
```

CLI:`crwl <url> -o markdown` / `--deep-crawl bfs --max-pages 10` /
`-q "Extract all prices"`(LLM 抽取,需 API key)。

## 核心概念

- `AsyncWebCrawler` — 引擎;`BrowserConfig` 配浏览器(代理/stealth/headless);
  `CrawlerRunConfig` 配单次运行(wait_for、缓存、hooks、会话)
- 输出字段:markdown / cleaned_html / structured(抽取结果)/ links /
  metadata / screenshots / downloaded_files
- **抽取策略**:CSS selector、XPath、LXML、正则、LLM(OpenAI/Anthropic/
  Ollama/任意 LiteLLM 兼容端,配 Pydantic schema)、Cosine。静态策略快而
  省,LLM 策略贵但能啃无结构页。
- **深爬**:BFS/DFS/Best-First + 自适应(信息够了就停)+ 链接相关性打分;
  `prefetch=True` 提速 5-10x;崩溃恢复 `resume_state`/`on_state_change`。
- **规模化**:异步浏览器池、内存自适应调度器、流式结果,单任务可上万页;
  缓存、session 保持、cookies、hooks、代理、stealth、截图、PDF 解析。

## 铁打的实话(评估结论,先读)

1. **反爬不是它的强项**。公开页很好用;受保护站点(Cloudflare 硬墙等)
   独立基准成功率仅 ~33%,和 Firecrawl 同档 —— 成功率 = 你自己代理池
   的质量,它不带解锁服务。别当反爬神器用。
2. **schema 手写且静态**。CSS/XPath 规则要自己写,目标站改版就断,没有
   自愈能力。所谓 "adaptive" 只针对深爬路径选择,不修选择器。
3. **很重**。真浏览器 + Chromium,装完体积大、吃 CPU/内存,不适合瘦
   容器/低配机器。
4. **自托管运维全在你**。升级/缩放/监控自己管。
5. **安全**:Docker 版 v0.9.x 连发安全修复(之前爆过 RCE/SSRF/auth
   bypass/硬编码 JWT);v0.9.3 是纯安全版无新功能。**用 Docker 版必须
   保持最新 + 开认证 + 绑 loopback**;别把爬到的网页 HTML 当可信内容
   渲染/回填 innerHTML(历史上出过存储型 XSS 类问题)。
6. 部分评测把许可证写成 MIT,实际是 **Apache-2.0**(以仓库为准)。

## 避坑

- 用户问"这个爬虫好用吗"→ 先给定位结论(LLM 喂料神器 / 反爬银弹 ✗),
  再按上节"铁打的实话"逐条给,别只吹 star 数。
- LLM 抽取路径要 API key,别默认它有;无 key 用 CSS/XPath/正则。
- 爬到的文件(CSV/PDF/JSON 等)会落盘到 downloads 目录并给路径
  (`downloaded_files`),二进制型 PDF/图片的 html 字段为空 —— 别从 html
  里找二进制内容。
- `result.markdown` 是主产物;要结构化先想清楚用静态选择器还是 LLM。
