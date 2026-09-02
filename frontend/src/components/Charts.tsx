import type { ReactNode } from "react";
import { useEChart } from "../hooks";
import type { PackageRow, SummaryDist } from "../types";

function Card(props: { title: string; children: ReactNode }) {
  return (
    <div className="chart">
      <h3>{props.title}</h3>
      <div className="cb">{props.children}</div>
    </div>
  );
}

export function Charts(props: { dist: SummaryDist; topLagging: PackageRow[] }) {
  const { dist, topLagging } = props;

  const pChart = useEChart(
    {
      tooltip: { trigger: "item" },
      legend: { bottom: 0, textStyle: { color: "#4b5563" }, itemWidth: 12, itemHeight: 12 },
      series: [{
        type: "pie", radius: ["42%", "68%"], center: ["50%", "44%"], label: { show: false },
        data: [
          { name: "P0 关键", value: dist.p_level.P0 || 0, itemStyle: { color: "#f3524d" } },
          { name: "P1 基础", value: dist.p_level.P1 || 0, itemStyle: { color: "#fa7305" } },
          { name: "P2 应用", value: dist.p_level.P2 || 0, itemStyle: { color: "#3385ff" } },
        ],
      }],
    },
    [dist.p_level.P0, dist.p_level.P1, dist.p_level.P2]
  );

  const gChart = useEChart(
    {
      tooltip: { trigger: "item" },
      legend: { bottom: 0, textStyle: { color: "#4b5563" }, itemWidth: 12, itemHeight: 12 },
      series: [{
        type: "pie", radius: ["42%", "68%"], center: ["50%", "44%"], label: { show: false },
        data: [
          { name: "A", value: dist.activity_grade.A || 0, itemStyle: { color: "#0bb151" } },
          { name: "B", value: dist.activity_grade.B || 0, itemStyle: { color: "#3385ff" } },
          { name: "C", value: dist.activity_grade.C || 0, itemStyle: { color: "#f7ba2a" } },
          { name: "D", value: dist.activity_grade.D || 0, itemStyle: { color: "#f3524d" } },
          { name: "待采集", value: dist.activity_grade["N/A"] || 0, itemStyle: { color: "#d1d5db" } },
        ],
      }],
    },
    [dist.activity_grade.A, dist.activity_grade.B, dist.activity_grade.C, dist.activity_grade.D, dist.activity_grade["N/A"]]
  );

  const dChart = useEChart(
    {
      tooltip: { trigger: "axis" },
      grid: { left: 8, right: 8, top: 16, bottom: 6, containLabel: true },
      xAxis: { type: "category", data: ["升级", "维持", "日落"], axisLabel: { color: "#94a3b8" } },
      yAxis: { type: "value", axisLabel: { color: "#94a3b8" } },
      series: [{
        type: "bar", data: [dist.disposal.upgrade || 0, dist.disposal.maintain || 0, dist.disposal.sunset || 0],
        itemStyle: { color: "#002FA7" }, barWidth: "45%",
      }],
    },
    [dist.disposal.upgrade, dist.disposal.maintain, dist.disposal.sunset]
  );

  const lag = topLagging.slice(0, 8).slice().reverse();
  const lChart = useEChart(
    {
      tooltip: { trigger: "axis" },
      grid: { left: 8, right: 40, top: 8, bottom: 8, containLabel: true },
      xAxis: { type: "value", axisLabel: { color: "#94a3b8" } },
      yAxis: { type: "category", data: lag.map((p) => p.name), axisLabel: { color: "#94a3b8" }, inverse: true },
      series: [{ type: "bar", data: lag.map((p) => p.score), itemStyle: { color: "#fa7305" }, barWidth: "48%" }],
    },
    [lag.map((p) => p.name).join(","), lag.map((p) => p.score).join(",")]
  );

  return (
    <div className="charts">
      <Card title="P0 / P1 / P2 分层"><div ref={pChart} style={{ height: "100%" }} /></Card>
      <Card title="活跃度等级（A–D）"><div ref={gChart} style={{ height: "100%" }} /></Card>
      <Card title="治理建议"><div ref={dChart} style={{ height: "100%" }} /></Card>
      <Card title="基线滞后最严重的包"><div ref={lChart} style={{ height: "100%" }} /></Card>
    </div>
  );
}
