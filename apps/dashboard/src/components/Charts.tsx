import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_COLORS } from "../utils/format";

const tooltipStyle = {
  background: "#1a2238",
  border: "1px solid #334155",
  borderRadius: 8,
  fontSize: 13,
};

export function ReturnBarChart({
  data,
  dataKey = "value",
  nameKey = "name",
  height = 280,
  color = "#6366f1",
}: {
  data: { name: string; value: number; fill?: string }[];
  dataKey?: string;
  nameKey?: string;
  height?: number;
  color?: string;
}) {
  if (!data.length) return <p className="muted chart-empty">No data yet</p>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#24304d" vertical={false} />
        <XAxis dataKey={nameKey} tick={{ fill: "#94a3b8", fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={56} />
        <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
        <Tooltip
          contentStyle={tooltipStyle}
          formatter={(v: number) => [`${v.toFixed(1)}%`, "Est. return"]}
        />
        <Bar dataKey={dataKey} radius={[6, 6, 0, 0]}>
          {data.map((entry, i) => (
            <Cell key={entry.name} fill={entry.fill || CHART_COLORS[i % CHART_COLORS.length] || color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function HeatBarChart({
  data,
  height = 220,
}: {
  data: { name: string; heat: number }[];
  height?: number;
}) {
  if (!data.length) return <p className="muted chart-empty">No data yet</p>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#24304d" horizontal={false} />
        <XAxis type="number" domain={[0, 100]} tick={{ fill: "#94a3b8", fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
        <YAxis type="category" dataKey="name" width={120} tick={{ fill: "#cbd5e1", fontSize: 11 }} />
        <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [`${v.toFixed(0)}%`, "Theme heat"]} />
        <Bar dataKey="heat" fill="#22d3ee" radius={[0, 6, 6, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function TierPieChart({
  data,
  height = 200,
}: {
  data: { name: string; value: number }[];
  height?: number;
}) {
  if (!data.length) return null;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={45} outerRadius={70} paddingAngle={3}>
          {data.map((_, i) => (
            <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
          ))}
        </Pie>
        <Tooltip contentStyle={tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 12, color: "#94a3b8" }} />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function MiniSparkline({
  data,
  height = 48,
  color = "#6366f1",
}: {
  data: { v: number }[];
  height?: number;
  color?: string;
}) {
  if (!data.length) return null;
  const max = Math.max(...data.map((d) => d.v), 1);
  return (
    <svg className="sparkline" viewBox={`0 0 ${data.length * 8} ${height}`} height={height}>
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="2"
        points={data.map((d, i) => `${i * 8},${height - (d.v / max) * (height - 4) - 2}`).join(" ")}
      />
    </svg>
  );
}
