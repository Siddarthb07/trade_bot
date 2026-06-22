import {
  Area,
  AreaChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fmtPct } from "../utils/format";

export interface PricePoint {
  date: string;
  close: number;
  volume?: number;
}

export interface TrendInfo {
  return_1m?: number | null;
  return_3m?: number | null;
  above_ma50?: boolean | null;
  momentum?: string | null;
  ma50?: number | null;
  current_price?: number | null;
}

function withMa50(prices: PricePoint[]) {
  return prices.map((p, i, arr) => {
    const slice = arr.slice(Math.max(0, i - 49), i + 1);
    const ma50 = slice.reduce((s, x) => s + x.close, 0) / slice.length;
    return { ...p, ma50: slice.length >= 20 ? ma50 : undefined };
  });
}

const tipStyle = {
  background: "#0f1524",
  border: "1px solid #2a3550",
  borderRadius: 8,
  fontSize: 12,
};

/** Compact per-stock chart for list rows */
export function MiniPriceChart({
  prices,
  trend,
  height = 88,
  color = "#4f7cff",
}: {
  prices: PricePoint[];
  trend?: TrendInfo;
  height?: number;
  color?: string;
}) {
  if (!prices.length) {
    return <div className="chart-placeholder" style={{ height }}>No price data</div>;
  }
  const data = withMa50(prices.slice(-90));
  const up = (trend?.return_1m ?? 0) >= 0;
  const stroke = up ? "#4ade80" : "#f87171";

  return (
    <div className="mini-chart-wrap" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={`g-${color}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area type="monotone" dataKey="close" stroke={stroke} strokeWidth={1.5} fill={`url(#g-${color})`} dot={false} />
          <Line type="monotone" dataKey="ma50" stroke="#94a3b8" strokeWidth={1} dot={false} strokeDasharray="3 3" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Full detail chart with volume + MA50 */
export function DetailPriceChart({
  prices,
  trend,
  height = 300,
}: {
  prices: PricePoint[];
  trend?: TrendInfo;
  height?: number;
}) {
  if (!prices.length) {
    return <p className="warn">Price history unavailable</p>;
  }
  const data = withMa50(prices);
  const up = (trend?.return_3m ?? trend?.return_1m ?? 0) >= 0;
  const stroke = up ? "#4ade80" : "#f87171";

  return (
    <>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
          <defs>
            <linearGradient id="detailFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.25} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 10 }} interval="preserveStartEnd" />
          <YAxis yAxisId="price" tick={{ fill: "#64748b", fontSize: 10 }} domain={["auto", "auto"]} width={52} />
          <YAxis yAxisId="vol" orientation="right" hide />
          <Tooltip
            contentStyle={tipStyle}
            labelStyle={{ color: "#94a3b8" }}
            formatter={(v: number, name: string) => [
              name === "volume" ? v.toLocaleString() : v.toFixed(2),
              name === "close" ? "Price" : name === "ma50" ? "MA50" : "Volume",
            ]}
          />
          <Area yAxisId="price" type="monotone" dataKey="close" stroke={stroke} strokeWidth={2} fill="url(#detailFill)" dot={false} />
          <Line yAxisId="price" type="monotone" dataKey="ma50" stroke="#94a3b8" strokeWidth={1.5} dot={false} />
          <Area yAxisId="vol" type="monotone" dataKey="volume" fill="#334155" stroke="none" fillOpacity={0.4} />
        </ComposedChart>
      </ResponsiveContainer>
      {trend && (
        <div className="chart-stats">
          <span>1mo {fmtPct(trend.return_1m, 1)}</span>
          <span>3mo {fmtPct(trend.return_3m, 1)}</span>
          <span>{trend.above_ma50 ? "Above MA50" : "Below MA50"}</span>
          <span className={`mom-${trend.momentum}`}>{trend.momentum} momentum</span>
        </div>
      )}
    </>
  );
}
