import type { StreamDef } from "../types";
import { OSelect } from "./OSelect";

export function OEHeader(props: {
  ltsStreams: StreamDef[];
  innovStreams: StreamDef[];
  lts: string;
  innov: string;
  onLts: (v: string) => void;
  onInnov: (v: string) => void;
  onRefresh: () => void;
  onDocs: () => void;
  loading: boolean;
}) {
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
          </div>
          <button className="btn" onClick={props.onRefresh} disabled={props.loading}>
            {props.loading ? "加载中…" : "刷新数据"}
          </button>
        </div>
      </div>
    </header>
  );
}
