# AGENTS.md — pkg-governance 仓库规范

面向在本仓库工作的所有 Agent / 协作者。目标是让工程能力（lint、typecheck、dev server、端口管理）与数据流水线有统一入口，禁止绕过。

## 项目速览

openEuler RPM 包分级治理平台：FastAPI 后端（`backend/app`，含 collectors/engine）+ Vite/React/TS 前端（`frontend/`）+ 数据构建脚本（`scripts/`）。数据集在 `backend/data/cache/`（gitignore），治理规则在 `backend/data/rules/governance_rules.yaml`。

## 命令入口（一律走 make）

| 任务 | 命令 | 说明 |
| --- | --- | --- |
| 初始化 | `make install` | venv + 后端依赖 + dev 工具（ruff/mypy） |
| 前端构建 | `make ui` | pnpm install + build → `frontend/dist` |
| 质量门 | `make check` | ruff check + ruff format --check + eslint + mypy + tsc |
| 自动修复 | `make format` | ruff format + autofix（不改语义） |
| 类型检查 | `make typecheck` | mypy（backend/app + scripts）+ tsc --noEmit |
| 启动服务 | `make dev` | 带实例发现/端口管理，幂等；Ctrl-C 停止 |
| 停止/状态/重启 | `make stop` / `make status` / `make restart` | 进程管理 |
| 全量数据 | `make build` | 真实采集，3–4 分钟，缓存增量可续传 |
| 快速/离线数据 | `make build-quick` / `make seed` | seed 会**覆盖** packages.json |

## 硬性流程

1. **改完代码必须 `make check` 全绿再提交**；类型/lint 不通过不算完成。
2. **启动服务只用 `make dev`**（内部是 `scripts/dev.py`）：禁止裸起 `uvicorn` 绕过实例发现与端口管理。
   - 端口被外部进程占用：脚本会报错并列出占用者；`--any-port` 自动右移；`--restart` 换掉旧实例。
   - 脚本自带 `/api/health` 健康检查，30s 未 healthy 会自动退出并保留日志。
3. **提交遵循 Conventional Commits**（历史风格）：`feat(collector): …` / `fix(frontend): …` / `chore: …`，正文说明 why。
4. 数据构建后如需刷新页面数据，调用 `/api/reload` 或重启服务。

## 代码风格

- Python：ruff 规则 `E,F,W,I,UP,B`，行宽 100，target py310；mypy `check_untyped_defs` 起步。新代码必须带类型标注与简短 docstring；中文注释 OK，注释说 why 不说 what。
- 前端：TypeScript strict；组件放 `frontend/src/components/`，类型集中在 `types.ts`。
- 正则已匹配的流名再取 group 时用 `openeuler._match()` 帮助函数（mypy union-attr）。

## 领域陷阱（改 engine/collectors 前必读）

- **capability 归一化禁止 `split("(")`**：`python3dist(x)`/`npm(x)`/`perl(x)` 必须完整匹配命名空间参数；按 `(` 截断会让整个语言生态塌缩成伪超级节点。见 `engine/importance.py::_cap_key`。
- **Python 闭包 BFS 只沿 python 命名空间边**（`python*`、`/usr/bin/python*`），否则经 glibc/kernel 等真实但无关的边溢出半个发行版。
- 反向依赖用**百分位**而非原始阈值；SONAME 剥版本保留 `(64bit)` 架构后缀。
- DevStation 每个 RC 按 kernel 变体（6.6 基线 / 6.18 试验）展开成独立流，基线（最低版本）排最前；默认创新版取最新 RC 的基线变体。

## 环境注意事项

- `PORT`（默认 8000）/`HOST` 见 `.env.example`；8000 常被 OrbStack 等占用，冲突时优先 `--any-port`。
- `make seed` 优先复用真实 `inventory.json` 缓存生成快照（meta 带 `seed: true`），会覆盖 `packages.json`；需要真实画像时跑 `make build`。
- 编辑器对同一文件的多次修改必须**串行**执行，写入后回读校验，防止回写覆盖。
