# openEuler RPM 包分级治理平台

> 活跃度统计 · AI 全量包画像 · P0/P1/P2 分层升级 · 版本对比 · 日落候选 · 人力估算

基于公开 API，把 openEuler **最新 LTS** 与 **最新创新版（26.09-DevStation）** 的全量软件包信息抓取下来，
与 Ubuntu（LTS + 前沿）逐包比对，标记核心包（P0/P1/P2）、长期未更新/无人维护（应日落）的包，
并用一个可交互的前后端界面完成生态兼容性治理。

页面顶部提供 **LTS / 创新版本切换器**：LTS 展示当前维护的全部 LTS（如 24.03 LTS / SP1–SP4），
创新版展示 **已发行创新版（24.09 / 25.03 / 25.09）** 与 **26.09-DevStation 的全部 RC / 每日构建**，
切换后版本列与“落后基线”实时重算。

![dashboard](docs/screenshot-dashboard.png)

---

## 它与 PPT 的对应关系

PPT（《RPM 包分级治理：月度活跃度 × AI 全量包画像 × 分层升级》）定义了四维治理流水线，本平台逐条落地：

| PPT 维度 | 平台实现 |
| --- | --- |
| ① 月度活跃度 | `engine/grading.py`：按月序列（提交·PR·Issue）做 1/3/6/12 月滚动加权 → A/B/C/D 分级；仓库待办（未闭环 Issue/PR） |
| ② AI 包画像 | `engine/importance.py`：活跃度 × 重要性 × 关键包（Python 依赖闭包）三维分类 → 核心/重要/普通 + P0/P1/P2；处置动作（升级优先/维持/合并/日落） |
| ③ 人力估算 | `engine/effort.py`：人日/包 = 升级(3–10 人日×年发布) + CVE(0.5–2 人日×年 CVE) + 例行维护 → 汇总为团队容量 |
| ④ HTML 输出 | `frontend/`：逐包画像、多维筛选排序、版本对比列、特殊包标识、活跃度趋势图 |
| 分层更新波次 | P0 最小关键集合（kernel/glibc/openssl/systemd/python+闭包）→ P1 网络/存储/工具链 → P2 上层应用 |
| 版本对比基准 | openEuler vs Ubuntu（LTS + 前沿 = interim），可选 SUSE（Tumbleweed / Leap·SLE）适配器 |
| 特殊包 | DevStation 谷歌浏览器等上游版本从网络获取、独立快速更新通道打标 |

---

## 数据来源（全部为公开 API，无需鉴权）

| 来源 | 用途 | 说明 |
| --- | --- | --- |
| `repo.openeuler.org` | openEuler 稳定镜像 | 解析 `repodata/primary.xml.zst` 得到该 release 的全部软件包/版本/反向依赖 |
| `dailybuild.openeuler.openatom.cn/dailybuild` | 创新版 / RC（DevStation） | 26.09-DevStation 尚未在稳定镜像发布时，自动解析最新每日构建 |
| `api.gitcode.com/api/v5` | 每个包的活跃度 | `commits`(≤2 页) + `pulls`/`issues`(open backlog) → 月度序列 + 待办 |
| `api.gitcode.com/orgs/{org}/repos` | 全量源码仓库最近提交 | 分页取得 1 万+ 仓库的 `pushed_at` 填 “最近提交” 列 |
| `archive.ubuntu.com/ubuntu` | Ubuntu LTS + 前沿基线 | 自动识别最新 LTS（26.04 resolute）与最新前沿（26.10 stonking）并解析 `Packages.gz` |
| `pypi.org/pypi/{project}/json` | `python-*` pip 模块上游画像 | 最新版本、最近发布、`Requires-Python`、是否停更 |
| `rules/governance_rules.yaml` | 治理规则 | P0/P1/P2、Python 依赖闭包、特殊包、版本滞后阈值、人力模型 |

> 采集是**可缓存、可恢复、限流友好**的：`build.py` 会把 repodata、Ubuntu、activity 分别缓存，
> 重复执行只补增量。生产环境可用 `ACTIVITY_TOKEN` 提高 GitCode 限流水位。

---

## 架构

```
pkg-governance/
├── backend/
│   ├── app/
│   │   ├── server.py            # FastAPI REST + 静态 SPA
│   │   ├── config.py            # 所有数据源/运行参数
│   │   ├── models.py            # Package / RepoSignals / Comparison / Governance
│   │   ├── utils.py             # 版本比较、日期、HTTP
│   │   ├── collectors/
│   │   │   ├── openeuler.py     # 发现 LTS/创新 + 解析 repodata
│   │   │   ├── repodata_parser.py# primary.xml(.zst/.gz) → 源包记录 + 反向依赖图
│   │   │   ├── ubuntu.py        # Ubuntu 基线（自动识别 LTS/前沿）
│   │   │   ├── gitcode.py       # 活跃度/待办采集（并发+缓存+恢复）
│   │   │   └── suse.py          # 可选：openSUSE 适配器（预留）
│   │   └── engine/
│   │       ├── grading.py       # A–D 活跃度分级
│   │       ├── importance.py    # 核心/重要/普通 + P0/P1/P2 + Python 闭包
│   │       ├── compare.py       # 跨发行版上游版本比较 → 落后标记
│   │       ├── disposal.py      # 升级/维持/合并/日落 + 无人维护检测
│   │       ├── effort.py        # 人日/人年估算
│   │       └── pipeline.py      # 组装全量包画像 + 治理优先级评分
│   └── data/
│       ├── rules/governance_rules.yaml
│       └── cache/               # 生成式缓存（gitignore）
├── frontend/                    # 交互式单页面板（Vite + React + TypeScript + ECharts，pnpm 管理）
├── scripts/
│   ├── build.py                 # 全量实时采集 → packages.json
│   └── seed.py                  # 无网确定性种子（优先复用本地缓存）
├── Makefile
└── .env.example
```

## 快速开始

```bash
# 1) 安装依赖（Python 3.10+）
make install

# 2) 构建前端（pnpm）
make ui

# 3) 实时采集全量数据（公开 API，约 1–4 分钟；含活跃度约 3–4 分钟）
make build            #  全量（含 GitCode 活跃度采集）
make build-quick      #  仅包+Ubuntu，快一些

# 4) 启动服务，打开 http://127.0.0.1:8000
make run
```

或用现成缓存快速重建数据集（建议在有 `make build` 产出后使用）：

```bash
make seed && make run
```

> 本仓库工作区已包含一次真实采集的 `data/cache/packages.json`，可直接 `make run` 查看效果。

## REST API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/meta` | 数据源/流/基线元信息 |
| GET | `/api/streams` | 可选流目录（全部 LTS + 已发行创新版 + DevStation RC/每日） |
| GET | `/api/summary` | 分布统计、工作量、Top 落后/日落 |
| GET | `/api/digest?lts=&innov=` | 轻量包列表 + 摘要（可按流切换） |
| GET | `/api/packages` | 分页 + 筛选（q/p_level/grade/importance/disposal/lagging/sunset/sort） |
| GET | `/api/packages/{name}?lts=&innov=` | 单个包完整画像（随所选流） |
| GET | `/api/packages/{name}/activity` | 该包月度活跃度序列 |
| GET | `/api/reload` | 重新加载数据集缓存 |

## 交互界面能力

- **版本切换器**：顶部下拉切换 LTS / 创新版流（含全部 RC 与每日构建），图表与表格实时重算。
- **摘要卡片**：总包数、P0/P1/P2、落后基线、日落候选、工作量（人日/人年）。
- **图表**：P 层分布、活跃度 A–D 分布、处置建议、最落后包 Top。
- **多维筛选/排序/搜索**：包名/摘要、P 层、活跃度、重要性、处置、落后、日落、已测活跃度。
- **逐包画像**：P/重要性/活跃度徽章、反向依赖、活跃度指数、年维护工作量、版本对比四基准线、
  治理处置与维护提示、关键依赖（Top 依赖）、月度活跃度趋势折线图。
- **日落候选 / 无人维护**：D 级 + 无反向依赖 + 非关键 → 建议日落；D 级但仍有依赖 → 维持并上报风险；
  超过 180 天无提交且有未闭环 Issue/PR → 标记“长期未更新/疑似无人维护”。

## 关键设计说明

- **版本比较**：用上游版本（去掉 `.oe`/`.el`/`.fc`/`-0ubuntu` 等发行后缀）做跨发行版比较，避免
  “openEuler 2.38-1.oe 与 Ubuntu 2.38-0ubuntu 被误判为不等”。`source_aliases` 处理改名包（如 kernel↔linux）。
- **默认源聚合**：同一 `src-openeuler` 包在 `OS/everything/EPOL/debuginfo/source/update/update-source` 分散存在。
  采集按源聚合：version 取二进制源（OS/everything/EPOL/update）中的**最新**（`latest_repo` 标记来源），并打
  `has_source`/`has_debug`/`in_epol`/`in_update` 标记（见 `collectors/openeuler.collect_stream_inventory`）。
- **Python/pip 治理**：`python-*` 分为 系统 Python 运行时（`python3*`/`libpython`，P0 不日落）与 **pip 模块**
  （`python-requests` 等，对应 PyPI）。对 pip 模块采集 PyPI 画像，判定 ① 上游是否停更（>730 天）、
  ② `Requires-Python` 是否被系统 Python（如 3.11）满足（不满足=“Python 版本屏障”，不能盲目升级）、
  ③ 反向依赖压力；仅当 **PyPI 停更 + 无反向依赖 + 非核心** 才建议日落（见 `engine/python_gov.py`）。
- **反向依赖**：从 `primary.xml` 的 `provides/requires` 建图，得到“有多少其它源包依赖我”，用于重要性判定；
  用**百分位**而非原始阈值，避免基础库把直方图吞掉。
- **活跃度分级**：月度序列（提交 + PR + Issue）指数衰减加权，1/3/6/12 月滚动 → A/B/C/D；
  无实测数据不武断给 D，标记为“N/A（待采集）”。
- **日落严格化**：仅当 D + 无反向依赖 + 非关键/非 Python 关键才建议日落，避免误杀有依赖的包。
- **表格列**：保持原始列序（包名/分级/活跃度 → 4 个版本列 → 落后/处置/人日/反依赖/最近提交）；4 个版本列**横向滚动**，左右治理列**冻结**；去掉“重要性”与“P”的重复，只保留“分级”。
- **数据完备**：`最近提交` 来自真实 commits 深扫；版本对比不再出现全空（多源聚合后）。

## 局限与后续

- 活跃度采集默认全量深扫（每包一次 commits 查询，活跃包另取 PR/issue；`ACTIVITY_SAMPLE_LIMIT=0`），依赖 GitCode 公共 API 限速，首轮为长任务，`activity.json` 缓存使重跑增量续传；休眠仓（一年无提交）直接评 D。
- 源码包名与仓库名不一致时按规则解析（大小写、`java-X-openjdk`→`openjdk-X`、`rust-`/`python-` 前缀、`c++`→`cpp`、下划线转连字符），仍无法映射的包（约 1%）在 GitCode 上无可发现的同名仓，活跃度显示 N/A。
- “AI 包画像”采用确定性规则模拟（重要性、P 层、关键包），可无缝替换/叠加真实 LLM 评分（见 `engine/importance.py`）。
- SUSE 基线为预留适配器（`collectors/suse.py` 骨架），按需开启。
- 创新版 26.09-DevStation 在稳定镜像发布后，会自动切换为 `repo.openeuler.org`（无需改配置）。
- **前端**：Vite + React + TypeScript + ECharts，`pnpm` 管理；视觉复刻 openEuler 官网，并**直接使用 openEuler 官方 Logo**（`frontend/public/oe-logo.svg`，取自 openeuler.org 品牌页）。刷新数据按钮采用 React 渲染与 ECharts 生命周期管理，不会出现残留空框。
- Python/pip 画像默认采集全部 pip 模块（约 1200+），可从 `make build -- --no-pypi` 跳过。

## License

Mulan PSL v2（示例数据来源于各公开发布源，版权归各自方所有）。
