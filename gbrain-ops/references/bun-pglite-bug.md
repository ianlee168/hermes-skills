# Bun compiled CLI + PGLite bunfs 死锁 — 完整事故 + 根因

## 现象

`gbrain` 二进制（`~/.hermes/skills/gbrain/bin/gbrain`, 164MB ELF）跑任何子命令都报：

```
PGLite failed to initialize its WASM runtime.
  This looks like a Bun vfs issue: `/$$bunfs/root` is read-only on
  your system, so PGLite cannot extract its pglite.data WASM payload.
  Fix: `bun upgrade` (newer Bun mounts the vfs writable). If that
  does not help, run via Node: `node src/cli.ts` or install gbrain
  using the Node-based path. See #1340 for details.
  Original error: ENOENT: no such file or directory, open '/$bunfs/root/pglite.data'
```

子命令复现：`doctor` / `list` / `embed` / `search` 全部踩。

## 根因

Bun 编译单文件二进制时把所有依赖（包括 PGLite 的 WASM blob `pglite.data`）打包进一个 read-only 的 bunfs 虚拟文件系统。运行时 PGLite 试图把这个 WASM 解到 `/$$bunfs/root` 写临时挂载点，但当前 Bun 版本下这个路径是 read-only，导致 ENOENT。

**这是 gbrain 0.38.2.0 + 当前 Bun 版本组合的已知问题**，上游 issue #1340。建议两条路：
1. `bun upgrade` 到把 bunfs mount 成可写的版本
2. 改用 `node src/cli.ts` 或 Bun 源码运行

实测：

| 跑法 | 结果 |
|---|---|
| `~/.hermes/skills/gbrain/bin/gbrain doctor` | ❌ bunfs 报 ENOENT |
| `gbrain doctor`（PATH 里能找到二进制时） | ❌ 同上 |
| `node src/cli.ts doctor` | ❌ Node 22 strip-only 不支持 TS parameter properties |
| **`cd ~/.hermes/skills/gbrain && bun src/cli.ts doctor`** | ✅ 工作 |

Node 22 单独跑也不行 — gbrain src/ 用了 `constructor(public code: ErrorCode, ...)` 这种 TS parameter properties 语法，Node 的 strip-only 模式拒绝：

```
SyntaxError [ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX]: TypeScript parameter property is not supported in strip-only mode
    at parseTypeScript (node:internal/modules/typescript:63:40)
```

## 临时方案（已采用）

写一个 shell alias，把 `gbrain` 命令重定向到 `bun src/cli.ts`：

```bash
# 加到 ~/.bashrc
alias gbrain='cd ~/.hermes/skills/gbrain && bun src/cli.ts'
```

或者不写 alias，临时跑：
```bash
cd ~/.hermes/skills/gbrain && bun src/cli.ts "$@"
```

非交互 shell（cron、hermes agent terminal tool）不 source `.bashrc`，所以 cron 里要用 `cd ~/.hermes/skills/gbrain && bun src/cli.ts embed --all` 这种完整写法。

## 永久修法

等 Bun 升级或者 gbrain 切换到 Node-based 安装路径。本机环境目前没自动升级机制，先用 alias。
