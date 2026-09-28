import { useState } from "react";
import type { RefreshScope, RefreshStatus } from "../api";
import type { StreamDef } from "../types";
import { OSelect } from "./OSelect";

export function OEHeader(props: {
  ltsStreams: StreamDef[];
  innovStreams: StreamDef[];
  lts: string;
  innov: string;
  onLts: (v: string) => void;
  onInnov: (v: string) => void;
  onRefresh: (scope: RefreshScope) => void;
  onDocs: () => void;
  loading: boolean;
  refresh: RefreshStatus | null;
}) {
  const [scope, setScope] = useState<RefreshScope>("quick");
  const running = !!props.refresh?.running;
  const pct = props.refresh?.progress ?? 0;
  return (
    <header className="oe-header">
      <div className="oe-header-inner">
        <a className="oe-brand" href="/">
          <img className="oe-logo" src="/oe-logo.svg" alt="openEuler 包分级治理" />
        </a>
        <nav className="oe-nav">
          <button className="active" type="button">治理面板</button>
          <button type="button" onClick={props.onDocs}>文档</button>
        </nav>
        <div className="oe-header-right">
          <div className="stream-picker">
            <OSelect label="LTS 版本" value={props.lts} options={props.ltsStreams} onChange={props.onLts} />
            <OSelect label="创新版本" value={props.innov} options={props.innovStreams} onChange={props.onInnov} />
            <OSelect
              label="刷新范围"
              value={scope}
              options={[
                { id: "quick", label: "快速刷新（默认源+目录）" },
                { id: "full", label: "全量刷新（含活跃度/PyPI/npm）" },
              ]}
              onChange={(v) => setScope(v as RefreshScope)}
            />
          </div>
          <button className="btn" onClick={() => props.onRefresh(scope)} disabled={running || props.loading}>
            {running ? `刷新中 ${pct}%` : "刷新数据"}
          </button>
        </div>
      </div>
      {running ? (
        <div className="refresh-bar">
          <div className="refresh-fill" style={{ width: `${Math.max(3, pct)}%` }} />
          <span className="refresh-text">
            {props.refresh?.message || "正在从公开 API 重新采集…"}
          </span>
        </div>
      ) : null}
    </header>
  );
}
