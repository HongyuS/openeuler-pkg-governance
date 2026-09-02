import type { SummaryDist } from "../types";

export function SummaryCards(props: { dist: SummaryDist }) {
  const { dist } = props;
  const cards: [string, number | string, string][] = [
    ["总包数", dist.total, "mut"],
    ["P0 关键", dist.p_level.P0 || 0, "c0"],
    ["P1 基础", dist.p_level.P1 || 0, "c1"],
    ["P2 应用", dist.p_level.P2 || 0, "c2"],
    ["基线滞后", dist.outdated, dist.outdated > 400 ? "bad" : "warnc"],
    ["日落候选", dist.sunset_candidate, dist.sunset_candidate > 0 ? "bad" : "good"],
    ["特殊包", dist.special || 0, "mut"],
  ];
  return (
    <div className="cards">
      {cards.map(([label, num, cls]) => (
        <div className="card" key={label}>
          <div className={`num ${cls}`}>{num}</div>
          <div className="label">{label}</div>
        </div>
      ))}
    </div>
  );
}
