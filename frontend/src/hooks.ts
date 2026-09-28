import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";
import {
  fetchDigest,
  fetchRefreshStatus,
  fetchStreams,
  startRefresh,
  type RefreshScope,
  type RefreshStatus,
} from "./api";
import type { Digest, StreamDef } from "./types";

/**
 * Owns the selected LTS/innovation streams, loads the stream catalogue and the
 * (stream-scoped) digest, and supports explicit refresh. The selected pair is
 * sent as query params so every package's version columns + lag flags update.
 */
export function useDashboard() {
  const [catalog, setCatalog] = useState<StreamDef[]>([]);
  const [defaultPair, setDefaultPair] = useState<Record<string, string>>({});
  const [lts, setLts] = useState("");
  const [innov, setInnov] = useState("");
  const [digest, setDigest] = useState<Digest | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState<RefreshStatus | null>(null);

  const loadStreams = useCallback(async () => {
    const data = await fetchStreams();
    setCatalog(data.streams);
    setDefaultPair(data.default);
    setLts((prev) => prev || data.default?.openEuler_LTS || "");
    setInnov((prev) => prev || data.default?.openEuler_innovation || "");
  }, []);

  const loadDigest = useCallback(
    async (l: string, i: string) => {
      if (!l || !i) return;
      setLoading(true);
      setError("");
      try {
        setDigest(await fetchDigest(l, i));
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    loadStreams();
  }, [loadStreams]);

  useEffect(() => {
    if (lts && innov) void loadDigest(lts, innov);
  }, [lts, innov, loadDigest]);

  /** Trigger a real online re-collection and follow it to completion. */
  const refreshOnline = useCallback(
    async (scope: RefreshScope = "quick") => {
      try {
        await startRefresh(scope);
      } catch (e) {
        setError(String(e));
        return;
      }
      // Poll until the background job finishes, then reload everything.
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500));
        let st: RefreshStatus;
        try {
          st = await fetchRefreshStatus();
        } catch {
          continue;
        }
        setRefresh(st);
        if (!st.running) {
          if (st.error) setError(st.error);
          await loadStreams();
          await loadDigest(lts, innov);
          break;
        }
      }
    },
    [lts, innov, loadDigest, loadStreams]
  );

  // Resume progress display if a refresh was already running when we loaded.
  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const st = await fetchRefreshStatus();
        if (!stop) setRefresh(st);
      } catch {
        /* ignore */
      }
    };
    void tick();
    const id = window.setInterval(tick, 5000);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, []);

  const ltsStreams = useMemo(() => catalog.filter((s) => s.kind === "LTS"), [catalog]);
  const innovStreams = useMemo(
    () => catalog.filter((s) => s.kind === "innovation"),
    [catalog]
  );

  return {
    catalog, defaultPair, lts, innov, setLts, setInnov,
    digest, loading, error, refresh, refreshOnline, ltsStreams, innovStreams,
  };
}

/** Mount an ECharts instance into a div, dispose on unmount, resize on update. */
export function useEChart(option: echarts.EChartsOption, deps: unknown[] = []) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    chartRef.current?.dispose();
    chartRef.current = echarts.init(ref.current);
    const onResize = () => chartRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  const lastOption = useRef(option);
  lastOption.current = option;
  useEffect(() => {
    if (chartRef.current) chartRef.current.setOption(lastOption.current, true);
  }, deps);

  return ref;
}
