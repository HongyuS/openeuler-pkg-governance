---
name: "pkg-gov-dev"
description: "pkg-governance dev workflow: quality gate (ruff/mypy/eslint/tsc), dev server with port management, data build. Invoke when starting the server, running lint/typecheck, building datasets, or before committing in this repo."
---

# pkg-gov-dev — 开发工作流

本仓库工程能力的流程化入口。改动任何 backend/frontend/scripts 代码后，按下述顺序执行。

## 1. 质量门（提交前必过）

```bash
make check        # = ruff check + ruff format --check + eslint + mypy + tsc --noEmit
```

- Python lint/format：ruff（规则 `E,F,W,I,UP,B`，行宽 100）。语义无关的修复用 `make format` 自动处理。
- 类型：mypy 覆盖 `backend/app` 与 `scripts`（配置在 `pyproject.toml [tool.mypy]`）；前端 `tsc --noEmit`。
- 任一失败：先 `make format`，剩余手工修复；不要加 `# noqa` / `# type: ignore` 逃避，确需豁免须注明原因。

## 2. 启动 / 管理服务

```bash
make dev          # 启动（幂等：已在跑则健康检查后直接退出）
make status       # 查看实例（跨端口发现所有 uvicorn app.server:app 进程）
make stop         # SIGTERM → 5s 后 SIGKILL
make restart      # stop + start
```

`scripts/dev.py` 行为约定：

- 实例发现 = `lsof`（谁监听端口）+ `pgrep -f "uvicorn app.server:app"`（哪些是我们的进程），双信号交叉。
- 端口冲突分三种处置：我们自己的旧实例 → 幂等返回 0；外部进程 → 报错退出 1（除非 `--any-port` 右移）；`--restart` 显式替换。
- 启动后自动等待 `/api/health` 200；`frontend/dist` 缺失会先 `pnpm build`。
- 默认 `HOST=127.0.0.1`、`PORT=8000`（读环境变量）；8000 被 OrbStack 等占用时用 `make dev` 的 `--any-port` 变体：`.venv/bin/python scripts/dev.py --any-port`。

## 3. 数据构建

```bash
make build        # 全量真实采集（可 --no-activity / --no-pypi / --no-npm 跳段），缓存增量续传
make build-quick  # 跳过 GitCode 活跃度深扫
make seed         # 离线快照：优先复用真实 inventory 缓存，会覆盖 packages.json
```

- 构建后调用 `POST /api/reload` 或重启服务刷新内存数据集。
- `activity.json` / `pypi.json` / `npm.json` / `stream_versions.json` 均为增量缓存，删除即重采。

## 4. 提交

Conventional Commits（见 `git log`）：`feat(scope):` / `fix(scope):` / `chore:`；正文写 why，一逻辑一提交。提交前 `make check` 全绿 + `make status` 确认没有把 dev server 留在异常状态。
