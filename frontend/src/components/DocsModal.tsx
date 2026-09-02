import { useEffect } from "react";

/** 项目文档弹窗：ESC / 点击遮罩关闭，打开时锁定页面滚动 */
export function DocsModal(props: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") props.onClose(); };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [props.onClose]);

  return (
    <>
      <div className="mask" onClick={props.onClose} />
      <div className="modal" role="dialog" aria-modal="true" aria-label="项目文档">
        <div className="modal-head">
          <h3>项目文档</h3>
          <span className="close" onClick={props.onClose}>✕</span>
        </div>
        <div className="modal-body">
          <h4>设计目标</h4>
          <p>
            基于公开 API，获取 openEuler <b>最新 LTS</b> 与 <b>最新创新版</b> 的可选流（含全部 DevStation RC/每日构建）的全量软件包信息；
            与 Ubuntu（LTS + 前沿）逐包对比，标记哪些包过旧；标记核心包（P0/P1/P2）；标记长期未更新、无人维护（应日落）的包；
            在交互式界面中完成生态兼容性治理。
          </p>

          <h4>治理维度</h4>
          <ol>
            <li><b>月度活跃度</b>：近 1/3/6/12 月滚动加权 → A/B/C/D；仓库待办（未闭环 Issue/PR）。</li>
            <li><b>AI 全量包画像</b>：活跃度 × 重要性 × 关键包（Python 依赖闭包）→ 核心/重要/普通 + P0/P1/P2。</li>
            <li><b>交互式输出</b>：逐包画像、多维筛选排序、版本对比列、特殊包标识、活跃度趋势。</li>
          </ol>

          <h4>分层更新波次</h4>
          <p>
            <span className="badge b-p0">P0</span> 最小关键集合（kernel/glibc/openssl/systemd/python+闭包）优先对齐最新 release；
            <span className="badge b-p1">P1</span> 网络/存储/工具链；
            <span className="badge b-p2">P2</span> 上层应用最后。
          </p>

          <h4>可选的创新 / LTS 流</h4>
          <p>
            页面顶部可切换：<b>LTS</b> 展示当前维护的全部 LTS（如 24.03 LTS、SP1–SP4）；
            <b>创新版</b> 展示已发行创新版（24.09/25.03/25.09）与 26.09-DevStation 的全部 RC / 每日构建，
            切换后版本列与"基线对比"实时重算。
          </p>

          <h4>数据来源（公开 API）</h4>
          <table>
            <tbody>
              <tr><th>来源</th><th>用途</th></tr>
              <tr><td>repo.openeuler.org</td><td>LTS / 已发行创新版 repodata/primary.xml.zst</td></tr>
              <tr><td>dailybuild.openeuler.openatom.cn</td><td>26.09-DevStation RC / 每日构建</td></tr>
              <tr><td>api.gitcode.com/api/v5</td><td>每包 commits/pulls/issues 活跃度 + 待办</td></tr>
              <tr><td>archive.ubuntu.com</td><td>Ubuntu LTS(26.04) + 前沿(26.10) 版本基线</td></tr>
              <tr><td>pypi.org/pypi/{"{project}"}/json</td><td>python-* pip 模块上游最新版本 / 停更 / Requires-Python</td></tr>
              <tr><td>backend/data/rules/governance_rules.yaml</td><td>P0/P1/P2、Python 闭包、特殊包、滞后阈值、人力模型</td></tr>
            </tbody>
          </table>

          <h4>默认源聚合</h4>
          <p>
            同一 <code>src-openeuler</code> 包的二进制最新版可能在 <code>update</code>，源码在 <code>source/update-source</code>，
            调试符号在 <code>debuginfo</code>，扩展在 <code>EPOL/main</code>，基础在 <code>OS</code>。采集按源聚合，
            version 取 /OS / everything / EPOL / update 的最新，并标记 <code>has_source</code>/<code>has_debug</code>/<code>in_epol</code>/<code>in_update</code>。
          </p>

          <h4>Python/pip 包治理</h4>
          <p>
            <code>python-*</code> 分为 系统 Python 运行时（<code>python3*</code>/<code>libpython</code>，P0 不日落）与
            <b>pip 模块</b>（对应 PyPI 上游）。对 pip 模块采集 PyPI 画像：上游是否停更（&gt;730 天）、
            <code>Requires-Python</code> 是否被系统 Python 满足（不满足即"Python 版本屏障"）、反向依赖压力；
            仅在 <b>PyPI 停更 + 无反向依赖 + 非核心</b> 时建议日落，其余给出明确处置提示。
          </p>

          <h4>运行</h4>
          <pre>{`make install
make build        # 实时全量采集（含多流版本矩阵）
make run          # http://127.0.0.1:8000`}</pre>
          <p className="muted">架构、REST API 详见仓库根目录 README.md。</p>
        </div>
      </div>
    </>
  );
}
