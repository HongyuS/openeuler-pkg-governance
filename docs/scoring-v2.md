# 治理评分体系 v2 设计（活跃度 / 优先级 / P 分层）

v1 的三个问题经社区对标（Fedora / Debian / Ubuntu / SUSE）确认后，本设计给出修正及依据。
对标结论：**没有任何社区用 commit 量判定包的健康度**——Fedora 用构建失败 + 响应性（FTBFS 8 周无人认领即 orphan，6 周无主即 retire）、Debian 用 MIA 响应性（60 天无响应转 orphan）、SUSE 按产品模块生命周期管理；关键包集合则都以"动作清单 + 依赖闭包展开"维护（Fedora critical path comps 组、Ubuntu seeds）。

## D1 活跃度：线性刻度改对数刻度

**决策**：`idx = Σ w·log1p(min(window, ref_high)) / log1p(ref_high)`，`ref_high` 12（原为线性 `/8` 截断）；带宽改为 A≥0.45 / B≥0.30 / C≥0.15。

**Why**：发行版仓的健康常态是"版本同步 + CVE 补丁"，月均 0.5–2 活动单位。线性刻度下月均 1 单位即判 D，把大量健康基础包误判成濒死（ISO 保护和 reverse-dep 检查兜住了日落误判，但活跃度分布已失真）。对数刻度把低活动区分开、把 A 留给真正持续活跃的包：

| 月均活动量 | v1 线性 | v2 对数 |
| --- | --- | --- |
| 0.5 | D | C |
| 1 | D | C |
| 2 | C | B |
| 5 | A | A |
| 12+ | A | A（满格） |

**依据**：coreutils 上游 26 周才 65 commits、glibc 半年一发，发行版仓活动量只会更低——月均 1 commit 是常态而非异常。

## D2 活跃度：事件下限

**决策**：`last_commit` 距今 ≤180 天 → 指数不低于 B 带宽；≤365 天 → 不低于 C 带宽。

**Why**：对齐社区的"活着"信号（Debian MIA 看 60 天响应、Fedora 看 14 周 FTBFS 响应）。一年内还有提交的包不应被判 D；180 天内有提交的包至少是 B。下限值直接引用带宽配置，不另设参数。

## D3 fallback 指数标注改为 estimated

**决策**：无月度序列、仅靠 last_commit/backlog 点值启发式得出的指数，`activity_source` 标 `estimated`（v1 误标 `measured`）。

**Why**：provenance 必须诚实。模块 docstring 承诺"来源标注明确"，v1 代码却把点值估算混进实测；前端"已测活跃度"筛选会被污染。

## D4 落后基线：flat +2 改 lag_degree 分级

**决策**：按 openEuler 与最新下游基线的前导版本段差输出 `lag_degree ∈ {patch, minor, major}`，对应加分 0.5 / 1.5 / 2.5。

**Why**：patch 落后（1.2.3→1.2.4）与跨大版本落后风险完全不同级，flat +2 无法区分；同时慢节奏上游（半年/一年一发）在绝对版本差上天然更大，分级天然缓解了"落后即重罚"的系统性偏置。

## D5 backport 减免

**决策**：包在 update / EPOL 仓有更新（`in_update` / `in_epol`）→ lag 加分减半。

**Why**：SUSE/RHEL 稳定版明确走 backport 模型（回灌补丁、不升版本号），openEuler LTS 同理。`in_update`/`in_epol` 是已采集的事实，说明补丁回灌活跃——这是 LTS 落后属于"设计而非缺陷"的最直接证据。

## D6 优先级风险项去重

**决策**：sunset_candidate 的附加分从 +1 降为 +0.5（sunset 蕴含 D 级，D 已计 +1.5）。

**Why**：同一事实（无人维护）计两次分；去重后 sunset P2 包 5.0 分，仍显著高于普通 D 级包 2.5 分，排序意图不变。

## D7 P0 成员修正

**决策**：

- **加入** `rpm` / `dnf` / `yum` / `grub2`；
- **移出** `mariadb` / `postgresql` / `libvirt` / `podman` / `containerd` / `docker`（落入 P1）。

**Why**：Fedora critical path 按动作定义，明确覆盖"引导"与"获取更新"——包管理栈与引导栈是动作的直接承载者，v1 清单缺失。数据库/虚拟化/容器在 Debian 中是 optional、不在 Fedora critical path，属产品交付组件而非系统最小集；其交付保护已由 `iso_baseline`（oemaker comps）承担，不需要 P0 重复背书。

**回滚**：纯 yaml 单点改动。

## D8 P1 成员：手工清单改派生

**决策**：`is_base = P1_base 手工清单 ∪ iso_baseline（oemaker comps 基础 ISO 组）∪（reverse_deps ≥ p75 兜底）`。

**Why**：Ubuntu seeds 与 Fedora comps 的共同点是"手工维护动作/种子清单，成员靠依赖闭包自动展开"。我们已采集 oemaker comps 数据（`iso_baseline` 字段），基础安装 ISO 的成员天然就是"必须维护的基础包"，把手工清单降级为补丁，消除双份清单的维护成本。

## D9 移除未用的 version_lag 配置

**决策**：删除 `version_lag.stale_days` / `critical_days`，代之以 `lag_bonus`（D4/D5 的参数）。

**Why**：全仓无消费方；日期维度的滞后判定已由版本段分级（D4）替代，保留死配置会误导后续维护者。

## D10 依赖图拆成运行时 + 构建两套

**决策**：除二进制仓 `Requires` 的运行时反依赖外，再从 source / update-source 仓 `arch="src"` 包的
`rpm:requires`（SRPM 头的 spec 级 requires = 各子包 `Requires` ∪ `BuildRequires`）减去同一源包的运行时
capability，得到纯构建依赖边。P 分级的 p75 兜底改用 `max(运行时, 构建)`，P0 `core` 判定仍只看运行时
（构建扇入说明"很多人需要编译它"，不等于"装好的系统依赖它"）；日落保护取两者并集
（`disposal` 的 `sunset_eligible` 要求两个计数都为 0）。

**Why**：只看运行时依赖会系统性误杀构建工具链——实测 24.03-LTS-SP4 有 619 个"D 级 + 无运行时反依赖"
的包其实被别的 spec `BuildRequires`（`python-hatch-vcs` 63、`nodejs-tape` 55、`help2man` 40…），
`make` 的运行时反依赖只有 17 而构建反依赖 798。构建依赖被删会直接让构建根不可用，必须参与保护。

**落地文件**：`collectors/repodata_parser.py`（`parse_source_primary`）、`collectors/openeuler.py`
（source 仓 full 解析 + capability 相减）、`engine/importance.py`（`build_build_graph` +
`build_reverse_deps`/`build_dependents`）、`engine/disposal.py`、`engine/python_gov.py`、
`engine/nodejs_gov.py`、`models.py`、`utils.py::cap_key`。

## 公式汇总

```text
活跃度指数 = Σ(窗口权重 × log1p(min(窗口得分, 12)) / log1p(12))
            事件下限：last_commit ≤180d → ≥0.30；≤365d → ≥0.15
等级：A≥0.45  B≥0.30  C≥0.15  D≥0

治理优先级（满分 10） = P 级基础分（P0=4 / P1=2.5 / P2=1）
                     + lag_bonus[lag_degree]（patch 0.5 / minor 1.5 / major 2.5；
                       backport 减免 ×0.5）
                     + 活跃度风险（D +1.5 / C +0.75）+ 日落候选 +0.5
```

## 影响

- `packages.json` 需重建（`make build`；验证用 `make seed` 复用缓存即可重算全部分数）。
- 前端无需结构性改动：`lagging` 布尔保留，`lag_degree` 仅入库待后续展示；仅同步表格里的公式提示文案。
- 落地文件：`grading.py`（D1–D3）、`compare.py` + `models.py`（D4）、`pipeline.py`（D5/D6/D8）、`governance_rules.yaml`（D1/D2/D4/D5/D7/D9）。
