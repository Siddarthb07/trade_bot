const API_BASE = import.meta.env.VITE_API_URL || "/api";
const SHARE_KEY = "share_token";

/** Capture ?k= from WhatsApp links so phone opens signal without login. */
export function captureShareTokenFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const k = params.get("k");
  if (k) sessionStorage.setItem(SHARE_KEY, k);
}

function getAuthHeader(): string {
  const creds = sessionStorage.getItem("auth");
  if (!creds) return "";
  return `Basic ${creds}`;
}

function getShareToken(): string {
  return sessionStorage.getItem(SHARE_KEY) || "";
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const share = getShareToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> || {}),
  };
  if (share) {
    headers["X-Share-Token"] = share;
  } else {
    const auth = getAuthHeader();
    if (auth) headers.Authorization = auth;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 90_000);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timeout);
    if (err instanceof Error && err.name === "AbortError") {
      throw new Error("API timeout — server may be fetching market data. Wait and retry.");
    }
    throw err;
  }
  clearTimeout(timeout);
  if (response.status === 401) {
    sessionStorage.removeItem("auth");
    if (!share) window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!response.ok) {
    throw new Error(`API error ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function setAuth(username: string, password: string) {
  sessionStorage.setItem("auth", btoa(`${username}:${password}`));
}

export function isAuthed(): boolean {
  return !!sessionStorage.getItem("auth") || !!sessionStorage.getItem(SHARE_KEY);
}

export interface BulkInvestorRow {
  entity: string;
  total_value: number;
  deal_count?: number;
  latest_at?: string;
  action?: string;
  qty?: number | null;
  implied_price?: number;
  source?: string;
  win_rate?: number | null;
  median_return?: number | null;
  n_trades?: number;
}

export interface BulkInvestorBacking {
  investors: BulkInvestorRow[];
  total_value: number;
  investor_count: number;
  deal_count: number;
  window_days: number;
  aggregate_win_rate?: number | null;
  aggregate_median_return?: number | null;
  tracked_past_trades?: number;
}

export interface DataMaturityInfo {
  status: "too_new" | "maturing" | "labeled" | "partial";
  label: string;
  detail: string;
  age_days: number;
  days_until_label: number;
  label_window: string;
  readiness_pct: number;
  forward_return_3mo?: number | null;
}

export interface BulkPredictionMeta {
  method: "ml" | "rules";
  scorer_version: string;
  lead_investor_win_rate?: number | null;
  lead_investor_median_return?: number | null;
  lead_investor_n_trades?: number | null;
  backing_win_rate?: number | null;
  backing_median_return?: number | null;
  tracked_past_trades?: number;
  data_maturity?: DataMaturityInfo;
}

export interface SignalItem {
  id: string;
  source: string;
  market: string;
  entity: string;
  ticker: string;
  action: string;
  qty?: number;
  value?: number;
  disclosed_at: string;
  disclosed_date_label?: string;
  disclosed_date_full?: string;
  source_url?: string;
  tier?: string;
  historical_win_rate?: number;
  n_trades?: number;
  scorer_version?: string;
  calibrated_probability?: number;
  return_distribution?: Record<string, number | null | boolean>;
  bulk_deal_count?: number;
  bulk_deal_count_week?: number;
  investor_backing?: BulkInvestorBacking;
  prediction?: BulkPredictionMeta;
  theme?: {
    slug?: string;
    name?: string;
    demand_driver?: string;
    company_name?: string;
    theme_heat?: number;
    alignment_score?: number;
  };
}

export interface Fundamentals {
  trailing_pe?: number | null;
  forward_pe?: number | null;
  profit_margin?: number | null;
  ebitda_margin?: number | null;
  operating_margin?: number | null;
  return_on_equity?: number | null;
  revenue_growth?: number | null;
  earnings_growth?: number | null;
  debt_to_equity?: number | null;
  ev_to_ebitda?: number | null;
  ebitda?: number | null;
  revenue?: number | null;
  sector?: string | null;
  industry?: string | null;
}

export interface ReturnBreakdown {
  momentum_pct?: number;
  theme_pct?: number;
  alignment_pct?: number;
  fundamentals_pct?: number;
  volatility_penalty_pct?: number;
  relative_strength_3m?: number;
  fundamentals_score?: number;
  investor_history_pct?: number;
  cluster_pct?: number;
}

export interface LiveThemePick {
  theme_slug: string;
  theme_name: string;
  demand_driver?: string;
  ticker: string;
  market: string;
  company_name: string;
  theme_heat: number;
  alignment_score: number;
  calibrated_probability: number;
  expected_return_pct: number;
  tier: string;
  composite_score?: number;
  signal_id?: string | null;
  signal_date?: string | null;
  has_bulk_deal: boolean;
  bulk_confirmed?: boolean;
  bulk_deal_count?: number;
  bulk_backed?: boolean;
  investor_backing?: BulkInvestorBacking;
  prediction?: BulkPredictionMeta;
  sell_horizon_label?: string;
  hold_days?: number;
  hold_label_long?: string;
  hold_label_short?: string;
  entry_date?: string;
  entry_date_label?: string;
  entry_date_full?: string;
  exit_date_label?: string;
  exit_date_full?: string;
  exit_window_label?: string;
  review_date_label?: string;
  countdown_label?: string;
  hold_status?: string;
  timeframe_tier?: string;
  days_remaining?: number;
  fundamentals?: Fundamentals;
  return_breakdown?: ReturnBreakdown;
  return_rationale?: string;
  rank_index?: number;
}

export interface RankedSharePick {
  rank_index: number;
  kind: string;
  ticker: string;
  market: string;
  tier?: string;
  expected_return_pct?: number;
  calibrated_probability?: number;
  theme_name?: string | null;
  bulk_deal_count_week?: number;
  signal_id: string;
  share_url: string;
  hold_label_long?: string;
  exit_date_label?: string;
  investor_backing?: BulkInvestorBacking;
}

export interface ThemeSummary {
  slug: string;
  name: string;
  demand_driver: string;
  world_context: string;
  proxy_ticker: string;
  theme_heat: number;
  proxy_return_3m?: number;
  proxy_prices?: { date: string; close: number; volume?: number }[];
  top_picks: LiveThemePick[];
}
