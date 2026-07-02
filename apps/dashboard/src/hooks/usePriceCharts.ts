import { useEffect, useState } from "react";
import { apiFetch } from "../api";
import { PricePoint, TrendInfo } from "./PriceChart";

type Key = string;

interface ChartBundle {
  prices: PricePoint[];
  trend?: TrendInfo;
}

export function usePriceCharts(requests: { ticker: string; market: string }[]) {
  const [charts, setCharts] = useState<Record<Key, ChartBundle>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!requests.length) {
      setCharts({});
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);

    async function load() {
      try {
        const data = await apiFetch<{ items: { ticker: string; market: string; prices: PricePoint[]; trend: TrendInfo }[] }>(
          "/market/price-history/batch",
          {
            method: "POST",
            body: JSON.stringify({ items: requests.slice(0, 36) }),
          },
        );
        if (cancelled) return;
        const map: Record<Key, ChartBundle> = {};
        for (const item of data.items) {
          map[`${item.market}:${item.ticker}`] = { prices: item.prices, trend: item.trend };
        }
        setCharts(map);
      } catch (e) {
        console.error(e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [JSON.stringify(requests.map((r) => `${r.market}:${r.ticker}`).sort())]);

  function get(ticker: string, market: string) {
    return charts[`${market}:${ticker}`];
  }

  return { get, loading };
}
