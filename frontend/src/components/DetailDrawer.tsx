import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { PackageDetail } from "../types";

export function DetailDrawer(props: { detail: PackageDetail | null; loading: boolean; onClose: () => void }) {
  const trendRef = useRef<HTMLDivElement | null>(null);
  const series = props.detail ? props.detail.activity.monthly || {} : {};
  const open = props.loading || !!props.detail;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") props.onClose(); };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, props.onClose]);

  useEffect(() => {
    if (!trendRef.current || !props.detail) return;
    const months = Object.keys(series).sort();
    const chart = echarts.init(trendRef.current);
    chart.setOption({
      tooltip: { trigger: "axis" },
      legend: { data: ["提交", "PR", "Issue"], textStyle: { color: "#4b5563" }, top: 0 },
      grid: { left: 8, right: 8, top: 26, bottom: 6, containLabel: true },
      xAxis: { type: "category", data: months, axisLabel: { color: "#94a3b8", rotate: 30, fontSize: 10 } },
      yAxis: { type: "value", axisLabel: { color: "#94a3b8" } },
      series: ["commits", "prs", "issues"].map((k) => ({
        name: { commits: "提交", prs: "PR", issues: "Issue" }[k],
        type: "line", smooth: true, showSymbol: false,
        data: months.map((m) => (series[m] || {})[k as keyof typeof series[string]] || 0),
      })),
    });
    return () => chart.dispose();
  }, [props.detail, JSON.stringify(series)]);

  if (!open) return null;
  if (!props.detail) {
    return (
      <>
        <div className="mask" onClick={props.onClose} />
        <aside className="drawer">
          <div className="close" onClick={props.onClose}>✕</div>
          <div className="spin" />
        </aside>
      </>
    );
  }
  const d = props.detail;
  const g = d.governance;
  const idx = g.activity_scores.index;

  return (
    <>
      <div className="mask" onClick={props.onClose} />
      <aside className="drawer">
      <div className="close" onClick={props.onClose}>✕</div>
      <h2>{d.name}</h2>
      <div className="sub">{d.summary || "—"}</div>
      <div>
        <span className={`badge b-${g.p_level}`}>{g.p_level}</span>{" "}
        <span className={`badge b-${g.importance}`}>{g.importance}</span>{" "}
        <span className={`badge b-${g.activity_grade}`}>活跃度 {g.activity_grade}</span>
        {d.special ? <span className="tag">DevStation 特殊包</span> : ""}
        {g.sunset_candidate ? <span className="tag">日落候选</span> : ""}
        {d.in_iso ? <span className="tag" title="基础安装 ISO 内置：官方交付组件，退出需走 release-management 变更流程">ISO 内置</span> : ""}
        {d.iso_baseline ? <span className="tag" title="oemaker comps 组明确纳入（mandatory/default）">ISO 精选</span> : ""}
        {d.iso_excluded ? <span className="tag" title="oemaker rpmlist 明确排除出基础 ISO">ISO 排除</span> : ""}
      </div>
      <div className="grid">
        <div className="cell"><div className="k">反向依赖</div><div className="v">{g.reverse_deps}</div></div>
        <div className="cell"><div className="k">活跃度指数</div><div className="v">{idx != null ? idx : "—"}</div></div>
        <div className="cell"><div className="k">开放待办 (Issue+PR)</div><div className="v">{d.activity.open_issues + d.activity.open_prs}</div></div>
      </div>
      <div className="box">
        <h4>版本对比</h4>
        <table>
          {d.comparison.baselines.map((r) => (
            <tr key={r.stream}><td style={{ color: "#94a3b8" }}>{r.stream}</td><td className="mono">{r.version || "—"}</td></tr>
          ))}
        </table>
      </div>
      {d.comparison.lag_notes.length ? (
        <div className="box"><h4>版本滞后说明</h4><ul>{d.comparison.lag_notes.map((n, i) => <li key={i}>{n}</li>)}</ul></div>
      ) : null}
      <div className="box">
        <h4>仓库可用性</h4>
        <div className="muted">
          版本来源：{d.latest_repo || "—"}
          {d.in_iso ? " · 基础 ISO 内置" : ""}
          {d.has_source ? " · 源码(source)" : ""}
          {d.has_debug ? " · 调试(debuginfo)" : ""}
          {d.in_epol ? " · EPOL" : ""}
          {d.in_update ? " · update" : ""}
        </div>
      </div>
      {d.python?.kind === "pip_module" ? (
        <div className="box">
          <h4>Python / pip 包</h4>
          <div className="muted">
            PyPI 上游：{d.python.pypi_name}（最新 {d.python.pypi_latest || "—"}）
            <br />
            Requires-Python：{d.python.pypi_requires_python || "不限"}
            {" · "}系统 Python：{d.python.system_python || "—"}
            {" · "}
            {d.python.pypi_stale
              ? <span className="flag sunset">PyPI 停更 &gt;2 年</span>
              : <span className="flag good">上游在维护</span>}
            {" · "}
            {d.python.compat_ok
              ? <span className="flag good">Python 兼容</span>
              : <span className="flag lag">Python 版本屏障</span>}
          </div>
          {d.python.notes?.length ? (
            <ul>{(d.python.notes as string[]).map((n, i) => <li key={i}>{n}</li>)}</ul>
          ) : null}
        </div>
      ) : null}
      {d.npm?.kind === "npm_module" ? (
        <div className="box">
          <h4>Node.js / npm 包</h4>
          <div className="muted">
            npm 上游：{d.npm.npm_name}（最新 {d.npm.npm_latest || "—"}）
            {" · "}
            {d.npm.npm_stale
              ? <span className="flag sunset">npm 停更 &gt;2 年</span>
              : <span className="flag good">上游在维护</span>}
            {d.npm.npm_deprecated
              ? <>{" · "}<span className="flag sunset">已废弃 deprecated</span></>
              : null}
          </div>
          {d.npm.notes?.length ? (
            <ul>{(d.npm.notes as string[]).map((n, i) => <li key={i}>{n}</li>)}</ul>
          ) : null}
        </div>
      ) : null}
      <div className="box">
        <h4>治理建议</h4>
        <div>建议：{d.comparison.lagging ? <span className="flag lag">需升级</span> : <span className="flag good">同步</span>} {dispBadge(g.disposal)}</div>
        <ul>{g.maintenance_notes.length ? g.maintenance_notes.map((n, i) => <li key={i}>{n}</li>) : <li>无特别提示</li>}</ul>
      </div>
      <div className="box">
        <h4>关键依赖包（反向依赖 Top）</h4>
        <div className="muted">{g.dependents.slice(0, 14).join(", ") || "无"}</div>
      </div>
      <div ref={trendRef} id="trend" />
      <p className="muted" style={{ fontSize: 11 }}>
        活跃度来源：{d.activity.source === "measured" ? "GitCode 实测" : "待采集"} · 最后提交 {d.activity.last_commit || "—"}
      </p>
      </aside>
    </>
  );
}

function dispBadge(d: string) {
  if (d === "sunset") return <span className="badge b-D">日落</span>;
  if (d === "maintain") return <span className="badge b-important">维持</span>;
  return <span className="badge b-B">升级</span>;
}
