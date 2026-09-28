import type { Digest, PackageDetail, StreamDef } from "./types";

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

export function fetchStreams(): Promise<{ streams: StreamDef[]; default: Record<string, string> }> {
  return get("/api/streams");
}

export function fetchDigest(lts: string, innov: string): Promise<Digest> {
  const q = new URLSearchParams({ lts, innov });
  return get(`/api/digest?${q.toString()}`);
}

export function fetchPackage(name: string, lts: string, innov: string): Promise<PackageDetail> {
  const q = new URLSearchParams({ lts, innov });
  return get(`/api/packages/${encodeURIComponent(name)}?${q.toString()}`);
}

export type RefreshScope = "quick" | "full";

export interface RefreshStatus {
  running: boolean;
  scope: string;
  step: string;
  progress: number;
  message: string;
  started_at: string;
  finished_at: string;
  error: string;
  result: Record<string, unknown>;
}

export async function startRefresh(scope: RefreshScope): Promise<{ started: boolean; status: RefreshStatus }> {
  const r = await fetch(`/api/refresh?scope=${scope}`, { method: "POST" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export function fetchRefreshStatus(): Promise<RefreshStatus> {
  return get("/api/refresh/status");
}
