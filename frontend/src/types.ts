export type PLvl = "P0" | "P1" | "P2";
export type Grade = "A" | "B" | "C" | "D" | "N/A";
export type Importance = "core" | "important" | "ordinary";
export type Disposal = "upgrade" | "maintain" | "sunset";

export interface StreamDef {
  id: string;
  label: string;
  kind: "LTS" | "innovation";
  source: "mirror" | "dailybuild";
  date: string;
  rc: boolean;
  release: string;
}

export interface PackageRow {
  name: string;
  summary: string;
  p_level: PLvl;
  grade: Grade;
  importance: Importance;
  disposal: Disposal;
  lagging: boolean;
  lag_behind_ubuntu_lts: boolean;
  lag_behind_ubuntu_interim: boolean;
  sunset_candidate: boolean;
  special: boolean;
  reverse_deps: number;
  score: number;
  effort_pd: number;
  effort_py: number;
  has_source: boolean;
  has_debug: boolean;
  in_epol: boolean;
  in_update: boolean;
  latest_repo: string;
  python: {
    kind: string;
    pypi_name: string;
    pypi_latest: string;
    pypi_stale: boolean;
    compat_ok: boolean;
    system_python: string;
  };
  npm: {
    kind: string;
    npm_name: string;
    npm_latest: string;
    npm_stale: boolean;
    npm_deprecated: boolean;
  };
  versions: Record<string, string>;
  last_commit: string;
  open_backlog: number;
}

export interface SummaryDist {
  total: number;
  p_level: Partial<Record<PLvl, number>>;
  importance: Partial<Record<Importance, number>>;
  activity_grade: Partial<Record<Grade, number>>;
  disposal: Partial<Record<Disposal, number>>;
  outdated: number;
  sunset_candidate: number;
  special: number;
}

export interface Digest {
  meta: {
    streams: StreamDef[];
    default: Record<string, string>;
    baselines: Record<string, string>;
    data_date: string;
  };
  summary: { distributions: SummaryDist; selected: Record<string, string> };
  packages: PackageRow[];
}

export interface VersionRow {
  distro: string;
  stream: string;
  version: string;
  release_date: string;
  present: boolean;
  source: string;
}

export interface PackageDetail {
  name: string;
  summary: string;
  summary_full?: string;
  license: string;
  arches: string[];
  activity: {
    monthly: Record<string, { commits: number; prs: number; issues: number }>;
    last_commit: string;
    open_issues: number;
    open_prs: number;
    closed_prs: number;
    closed_issues: number;
    source: string;
  };
  governance: {
    p_level: PLvl;
    importance: Importance;
    activity_grade: Grade;
    activity_scores: Record<string, number | null>;
    disposal: Disposal;
    sunset_candidate: boolean;
    reverse_deps: number;
    dependents: string[];
    effort_person_days: number;
    effort_person_years: number;
    maintenance_notes: string[];
    score: number;
  };
  comparison: {
    baselines: VersionRow[];
    lagging: boolean;
    latest_upstream: string;
    latest_upstream_source: string;
    lag_notes: string[];
  };
  special: boolean;
  special_note: string;
  has_source: boolean;
  has_debug: boolean;
  in_epol: boolean;
  in_update: boolean;
  latest_repo: string;
  python: {
    kind: string;
    pypi_name: string;
    pypi_latest: string;
    pypi_last_release: string;
    pypi_stale: boolean;
    pypi_requires_python: string;
    compat_ok: boolean;
    system_python: string;
    notes?: string[];
  };
  npm: {
    kind: string;
    npm_name: string;
    npm_latest: string;
    npm_last_release: string;
    npm_stale: boolean;
    npm_deprecated: boolean;
    notes?: string[];
  };
}
