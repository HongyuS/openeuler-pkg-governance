import type { StreamDef } from "../types";

export function OEHeader(props: {
  ltsStreams: StreamDef[];
  innovStreams: StreamDef[];
  lts: string;
  innov: string;
  onLts: (v: string) => void;
  onInnov: (v: string) => void;
  onRefresh: () => void;
  loading: boolean;
}) {
  return (
    <header className="oe-header">
      <div className="oe-header-inner">
        <a className="oe-brand" href="/">
          <img className="oe-logo" src="/oe-logo.svg" alt="openEuler 包分级治理" />
        </a>
        <nav className="oe-nav">
          <a className="active" href="/">治理面板</a>
          <a href="/docs.html">文档</a>
        </nav>
        <div className="oe-header-right">
          <div className="stream-picker">
            <div className="stream-select">
              <label>LTS 版本</label>
              <select value={props.lts} onChange={(e) => props.onLts(e.target.value)}>
                <option value="">选择…</option>
                {props.ltsStreams.map((s) => (
                  <option key={s.id} value={s.id}>{s.label}</option>
                ))}
              </select>
            </div>
            <div className="stream-select">
              <label>创新版本</label>
              <select value={props.innov} onChange={(e) => props.onInnov(e.target.value)}>
                <option value="">选择…</option>
                {props.innovStreams.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <button className="btn" onClick={props.onRefresh} disabled={props.loading}>
            {props.loading ? "加载中…" : "刷新数据"}
          </button>
        </div>
      </div>
    </header>
  );
}
