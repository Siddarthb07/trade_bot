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

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
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
  source_url?: string;
  tier?: string;
  historical_win_rate?: number;
  n_trades?: number;
  scorer_version?: string;
  calibrated_probability?: number;
  return_distribution?: Record<string, number | null>;
  theme?: {
    slug?: string;
    name?: string;
    demand_driver?: string;
    company_name?: string;
    theme_heat?: number;
    alignment_score?: number;
  };
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
  signal_id?: string | null;
  has_bulk_deal: boolean;
  sell_horizon_label?: string;
}

export interface ThemeSummary {
  slug: string;
  name: string;
  demand_driver: string;
  world_context: string;
  proxy_ticker: string;
  theme_heat: number;
  proxy_return_3m?: number;
  top_picks: LiveThemePick[];
}
