import { useCallback, useMemo, useState } from "react";
import { fetchPackage } from "./api";
import { Charts } from "./components/Charts";
import { DetailDrawer } from "./components/DetailDrawer";
import { OEHeader } from "./components/Header";
import { PackageTable } from "./components/PackageTable";
import { SummaryCards } from "./components/SummaryCards";
import { useDashboard } from "./hooks";
import type { PackageDetail } from "./types";

export default function App() {
  const d = useDashboard();
  const [detail, setDetail] = useState<PackageDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const openDetail = useCallback(async (name: string) => {
    setDetail(null);
    setDetailLoading(true);
    try {
      const pkg = await fetchPackage(name, d.lts, d.innov);
      setDetail(pkg);
    } finally {
      setDetailLoading(false);
    }
  }, [d.lts, d.innov]);

  const selectedLabel = useMemo(() => {
    const find = (id: string) => d.catalog.find((s) => s.id === id)?.label || id;
    return `LTS: ${find(d.lts)} · 创新: ${find(d.innov)}`;
  }, [d.catalog, d.lts, d.innov]);

  const dataDate = d.digest?.meta.data_date || "";
  const baselines = d.digest?.meta.baselines || {};

  return (
    <>
      <OEHeader
        ltsStreams={d.ltsStreams}
        innovStreams={d.innovStreams}
        lts={d.lts}
        innov={d.innov}
        onLts={d.setLts}
        onInnov={d.setInnov}
        onRefresh={d.refresh}
        loading={d.loading}
      />
      <div className="banner">
        <div className="banner-inner">
          <h1>openEuler RPM 包分级治理</h1>
          <p className="desc">活跃度 × AI 全量包画像 × P0/P1/P2 分层升级 · 版本对比 · 日落候选</p>
          <div className="meta">
            <span className="chip">当前：{selectedLabel}</span>
            <span className="chip">数据日期：{dataDate || "—"}</span>
            <span className="chip">Ubuntu 基线：LTS {baselines.ubuntu_LTS || "—"} / 前沿 {baselines.ubuntu_interim || "—"}</span>
          </div>
        </div>
      </div>
      <main className="container">
        {d.error ? <div className="panel" style={{ padding: 14, color: "#f3524d" }}>加载失败：{d.error}</div> : null}
        {d.loading && !d.digest ? <div className="spin" /> : null}

        {d.digest ? (
          <>
            <SummaryCards dist={d.digest.summary.distributions} />
            <Charts
              dist={d.digest.summary.distributions}
              topLagging={d.digest.packages.filter((p) => p.lagging).sort((a, b) => b.score - a.score)}
            />
            <PackageTable packages={d.digest.packages} loading={d.loading} onOpen={openDetail} />
          </>
        ) : null}

        <DetailDrawer detail={detail} loading={detailLoading} onClose={() => setDetail(null)} />

        <footer className="footer">
          数据来源：openEuler 稳定镜像 / 每日构建 · GitCode / AtomGit API · Ubuntu Linux archive ·{" "}
          <a href="/docs.html" target="_blank">项目文档</a>
        </footer>
      </main>
    </>
  );
}
