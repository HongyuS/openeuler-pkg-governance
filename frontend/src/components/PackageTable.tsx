import { useDeferredValue, useMemo, useRef, useState } from "react";
import type { Grade, PackageRow, PLvl } from "../types";
import { OSelect } from "./OSelect";

const gradeRank: Record<Grade, number> = { A: 4, B: 3, C: 2, D: 1, "N/A": 0 };
const pRank: Record<PLvl, number> = { P0: 3, P1: 2, P2: 1 };

type SortKey = "score" | "name" | "p_level" | "grade" | "last_commit";

/** 显示时去掉 RPM epoch 前缀（0:），完整版本放在 title 提示里 */
function ver(v: string | undefined) {
  return (v || "—").replace(/^0:/, "");
}

function prioCls(s: number) {
  return s >= 6.5 ? "hi" : s >= 4.5 ? "md" : "";
}

function pageCluster(page: number, pages: number) {
  const out: number[] = [];
  const add = (n: number) => { if (!out.includes(n) && n >= 1 && n <= pages) out.push(n); };
  add(1);
  for (let p = page - 1; p <= page + 1; p++) add(p);
  add(pages);
  out.sort((a, b) => a - b);
  const res: (number | "…")[] = [];
  for (let i = 0; i < out.length; i++) {
    if (i > 0 && out[i] - out[i - 1] > 1) res.push("…");
    res.push(out[i]);
  }
  return res;
}

export function PackageTable(props: {
  packages: PackageRow[];
  loading: boolean;
  onOpen: (name: string) => void;
}) {
  const [q, setQ] = useState("");
  const [p, setP] = useState("");
  const [grade, setGrade] = useState("");
  const [disposal, setDisposal] = useState("");
  const [lag, setLag] = useState(false);
  const [sunset, setSunset] = useState(false);
  const [measured, setMeasured] = useState(false);
  const [sort, setSort] = useState<SortKey>("score");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const [per, setPer] = useState(100);
  const deferredQ = useDeferredValue(q);
  const panelRef = useRef<HTMLDivElement>(null);

  /** 翻页后滚回表格顶部（避开吸顶的 header） */
  const goPage = (n: number) => {
    setPage(n);
    if (panelRef.current) {
      const top = panelRef.current.getBoundingClientRect().top + window.scrollY - 88;
      if (window.scrollY > top) window.scrollTo({ top, behavior: "smooth" });
    }
  };

  const filtered = useMemo(() => {
    const query = deferredQ.trim().toLowerCase();
    let rows = props.packages.slice();
    if (query) rows = rows.filter((r) => r.name.toLowerCase().includes(query) || r.summary.toLowerCase().includes(query));
    if (p) rows = rows.filter((r) => r.p_level === p);
    if (grade) rows = rows.filter((r) => r.grade === grade);
    if (disposal) rows = rows.filter((r) => r.disposal === disposal);
    if (lag) rows = rows.filter((r) => r.lagging);
    if (sunset) rows = rows.filter((r) => r.sunset_candidate);
    if (measured) rows = rows.filter((r) => r.grade !== "N/A");
    const dir = order === "asc" ? 1 : -1;
    rows.sort((a, b) => {
      switch (sort) {
        case "name": return a.name.localeCompare(b.name) * dir;
        case "grade": return (gradeRank[a.grade] - gradeRank[b.grade]) * dir;
        case "p_level": return (pRank[a.p_level] - pRank[b.p_level]) * dir;
        case "last_commit": {
          const x = a.last_commit || "", y = b.last_commit || "";
          return (x < y ? -1 : x > y ? 1 : 0) * dir;
        }
        default: return (a.score - b.score) * dir;
      }
    });
    return rows;
  }, [props.packages, deferredQ, p, grade, disposal, lag, sunset, measured, sort, order]);

  const pages = Math.max(1, Math.ceil(filtered.length / per));
  const cur = Math.min(page, pages);
  const slice = filtered.slice((cur - 1) * per, cur * per);

  const toggleSort = (k: SortKey) => {
    if (sort === k) setOrder(order === "asc" ? "desc" : "asc");
    else { setSort(k); setOrder(k === "name" ? "asc" : "desc"); }
    setPage(1);
  };

  const sTh = (label: string, key: SortKey, center = false, title?: string) => (
    <th key={label} className={`sortable${center ? " center" : ""}`} title={title} onClick={() => toggleSort(key)}>
      {label}{sort === key ? (order === "asc" ? " ↑" : " ↓") : ""}
    </th>
  );

  return (
    <div className="panel" ref={panelRef}>
      <div className="filters">
        <span className="search-box">
          <input type="search" placeholder="搜索包名 / 摘要…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          {q ? <button className="clear" title="清除" onClick={() => { setQ(""); setPage(1); }}>✕</button> : null}
        </span>
        <OSelect value={p} minWidth={124} onChange={(v) => { setP(v); setPage(1); }}
          options={[{ id: "", label: "分级（全部）" }, { id: "P0", label: "P0" }, { id: "P1", label: "P1" }, { id: "P2", label: "P2" }]} />
        <OSelect value={grade} minWidth={136} onChange={(v) => { setGrade(v); setPage(1); }}
          options={[{ id: "", label: "活跃度（全部）" }, { id: "A", label: "A" }, { id: "B", label: "B" }, { id: "C", label: "C" }, { id: "D", label: "D" }, { id: "N/A", label: "N/A" }]} />
        <OSelect value={disposal} minWidth={124} onChange={(v) => { setDisposal(v); setPage(1); }}
          options={[{ id: "", label: "建议（全部）" }, { id: "upgrade", label: "升级" }, { id: "maintain", label: "维持" }, { id: "sunset", label: "日落" }]} />
        <label className="ck"><input type="checkbox" checked={lag} onChange={(e) => { setLag(e.target.checked); setPage(1); }} /> 基线滞后</label>
        <label className="ck"><input type="checkbox" checked={sunset} onChange={(e) => { setSunset(e.target.checked); setPage(1); }} /> 日落候选</label>
        <label className="ck"><input type="checkbox" checked={measured} onChange={(e) => { setMeasured(e.target.checked); setPage(1); }} /> 已测活跃度</label>
        <span className="total-inline">共 {filtered.length.toLocaleString()} 条</span>
      </div>

      <div className="table-wrap">
        <table className="pkg-table">
          <colgroup>
            <col />
            <col style={{ width: 64 }} />
            <col style={{ width: 72 }} />
            <col style={{ width: 64 }} />
            <col style={{ width: 165 }} />
            <col style={{ width: 165 }} />
            <col style={{ width: 165 }} />
            <col style={{ width: 165 }} />
            <col style={{ width: 64 }} />
            <col style={{ width: 72 }} />
            <col style={{ width: 112 }} />
          </colgroup>
          <thead>
            <tr>
              {sTh("包名", "name")}
              {sTh("分级", "p_level", true)}
              {sTh("活跃度", "grade", true)}
              {sTh("优先级", "score", true)}
              <th>openEuler LTS</th>
              <th>openEuler 创新</th>
              <th>Ubuntu LTS</th>
              <th>Ubuntu 前沿</th>
              <th className="center" title="openEuler 版本与 Ubuntu 基线的对比结果">基线对比</th>
              <th className="center">建议</th>
              {sTh("最近提交", "last_commit")}
            </tr>
          </thead>
          <tbody>
            {slice.map((r) => (
              <tr key={r.name} onClick={() => props.onOpen(r.name)}>
                <td className="pkg-cell">
                  <strong className="pkg-name" title={r.name}>{r.name}</strong>
                  <div className="pkg-summary" title={r.summary}>{r.summary}</div>
                  <RepoTag row={r} />
                </td>
                <td className="center"><span className={`badge b-${r.p_level}`}>{r.p_level}</span></td>
                <td className="center"><span className={`badge b-${r.grade}`}>{r.grade}</span></td>
                <td className="center">
                  <span className={`prio ${prioCls(r.score)}`} title="治理优先级 = P级基础分(P0=4/P1=2.5/P2=1) + 落后基线+2 + 活跃度D+1.5/C+0.75 + 日落候选+1，满分 10">
                    {r.score.toFixed(1)}
                  </span>
                </td>
                <td className="mono ver" title={r.versions.openEuler_LTS || ""}>{ver(r.versions.openEuler_LTS)}</td>
                <td className="mono ver" title={r.versions.openEuler_innovation || ""}>{ver(r.versions.openEuler_innovation)}</td>
                <td className="mono ver" title={r.versions.ubuntu_LTS || ""}>{ver(r.versions.ubuntu_LTS)}</td>
                <td className="mono ver" title={r.versions.ubuntu_interim || ""}>{ver(r.versions.ubuntu_interim)}</td>
                <td className="center">{r.lagging ? <span className="flag lag">滞后</span> : <span className="flag good">同步</span>}</td>
                <td className="center">{dispBadge(r.disposal)}</td>
                <td className="mono">{(r.last_commit || "—").slice(0, 10)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {slice.length === 0 ? <div className="empty">没有符合条件的包</div> : null}
      </div>

      <div className="table-foot">
        <span className="total">共 {filtered.length.toLocaleString()} 条</span>
        <div className="pager">
          <span className="size-select">
            <OSelect value={String(per)} minWidth={76} onChange={(v) => { setPer(+v); goPage(1); }}
              options={["25", "50", "100", "200"].map((n) => ({ id: n, label: n }))} />
            条/页
          </span>
          <button className="page pg-nav" disabled={cur <= 1} onClick={() => goPage(cur - 1)}>‹ 上一页</button>
          <div className="pages">
            {pageCluster(cur, pages).map((n, i) =>
              n === "…"
                ? <span key={i} style={{ padding: "0 2px", color: "#94a3b8" }}>…</span>
                : <button key={i} className={`page ${n === cur ? "active" : ""}`} onClick={() => goPage(n)}>{n}</button>
            )}
          </div>
          <button className="page pg-nav" disabled={cur >= pages} onClick={() => goPage(cur + 1)}>下一页 ›</button>
        </div>
      </div>

      {props.loading ? <div className="table-loading"><div className="spin" /></div> : null}
    </div>
  );
}

function RepoTag(props: { row: PackageRow }) {
  const r = props.row;
  const py = r.python?.kind === "pip_module";
  const tags: string[] = [];
  if (py) tags.push("pip");
  if (r.in_update) tags.push("update");
  if (r.in_epol) tags.push("EPOL");
  if (r.has_debug) tags.push("debug");
  if (r.has_source) tags.push("src");
  if (!tags.length) return null;
  return (
    <span className="pkg-tags">
      {tags.map((t) => (
        <span key={t} className="tag">{t}</span>
      ))}
    </span>
  );
}

function dispBadge(d: string) {
  if (d === "sunset") return <span className="badge b-D">日落</span>;
  if (d === "maintain") return <span className="badge b-important">维持</span>;
  return <span className="badge b-B">升级</span>;
}
