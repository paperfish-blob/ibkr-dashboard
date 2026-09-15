/**
 * Typed client for the FastAPI backend.
 *
 * Paths are relative, never absolute: Vite proxies /api to :9001 in dev and
 * FastAPI serves this build itself in production, so the same origin applies
 * in both and no CORS is involved.
 *
 * Every Decimal field below is typed `string`, NOT `number` -- pydantic
 * serialises Decimal as a JSON string ("7259.493481") to avoid float drift.
 * Typing them as number would type-check fine and then silently concatenate
 * at runtime, so callers must pass them through Number() (see lib/format.ts).
 */

/** "YYYY-MM-DD" */
export type IsoDate = string;
/** ISO 8601 timestamp */
export type IsoDateTime = string;
/** A pydantic Decimal, serialised as a string. Convert with Number(). */
export type DecimalString = string;

export type TodaySource = "gateway" | "flex" | "none";

/** One execution from a Flex Activity statement -- opening or closing. */
export interface RealizedTrade {
  symbol: string;
  trade_date: IsoDate;
  /** fifoPnlRealized exactly as Flex reports it -- gross, before commission. */
  realized_pnl: DecimalString;
  commission: DecimalString;
  currency: string;
  asset_category: string;
  quantity: DecimalString;
  buy_sell: string;
  /** "HH:MM:SS", or "" when the Flex Query omits Date/Time. */
  trade_time: string;
  trade_price: DecimalString | null;
  trade_money: DecimalString | null;
  order_type: string;
  notes_codes: string;
  exchange: string;
  /** realized_pnl + commission. Available, but not what the dashboard shows. */
  net_pnl: DecimalString;
  /** False for a trade that only opened or added to a position. */
  is_realizing: boolean;
}

export interface GatewayState {
  connected: boolean;
  realized_pnl: DecimalString | null;
  unrealized_pnl: DecimalString | null;
  daily_pnl: DecimalString | null;
  account: string;
  updated_at: IsoDateTime | null;
  error: string;
}

export interface CumulativePoint {
  date: IsoDate;
  realized_pnl: DecimalString;
  cumulative: DecimalString;
}

export interface DayGroup {
  date: IsoDate;
  total_pnl: DecimalString;
  trades: RealizedTrade[];
}

export interface PnLResponse {
  headline: DecimalString;
  today: DecimalString;
  currency: string;
  today_source: TodaySource;
  series: CumulativePoint[];
  trade_count: number;
  gateway: GatewayState;
  flex_ok: boolean;
  flex_error: string;
  flex_fetched_at: IsoDateTime | null;
  account_id: string;
  currency_warning: string;
  period: string;
  /** Which years this figure actually covers -- "all" merges only the years
   *  already downloaded, so a partial total must never look complete. */
  years_covered: number[];
}

export interface TransactionsResponse {
  total_realized: DecimalString;
  trade_count: number;
  from_date: IsoDate | null;
  to_date: IsoDate | null;
  /** Newest day first. */
  days: DayGroup[];
  flex_ok: boolean;
  flex_error: string;
  flex_fetched_at: IsoDateTime | null;
  account_id: string;
  period: string;
  years_covered: number[];
}

export type YearState = "missing" | "downloading" | "stored" | "error";

export interface YearStatus {
  year: number;
  state: YearState;
  trade_count: number;
  realizing_count: number;
  realized_pnl: DecimalString;
  currency: string;
  downloaded_at: IsoDateTime | null;
  error: string;
  is_current: boolean;
  /** A closed, settled year: downloaded once, never re-fetched. */
  immutable: boolean;
  started_at: IsoDateTime | null;
}

export interface HistoryStatus {
  years: YearStatus[];
  /** The year currently downloading, if any. Only one runs at a time. */
  downloading: number | null;
}

const BASE = "";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "POST" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json() as Promise<T>;
}

/** `period` is "all" or a four-digit year. The Flex token is rate limited
 *  (1 req/s, 10/min), so the backend caches aggressively and refuses
 *  concurrent downloads -- see downloadYear's `started` flag. */
export const api = {
  pnl: (period = "all"): Promise<PnLResponse> =>
    get<PnLResponse>(`/api/pnl?period=${encodeURIComponent(period)}`),
  transactions: (period = "all"): Promise<TransactionsResponse> =>
    get<TransactionsResponse>(`/api/transactions?period=${encodeURIComponent(period)}`),
  history: (): Promise<HistoryStatus> => get<HistoryStatus>("/api/history"),
  /** `started` is false when a download is already running -- only one runs
   *  at a time, and the message says which year holds the slot. */
  downloadYear: (year: number): Promise<{ started: boolean; message: string }> =>
    post<{ started: boolean; message: string }>(`/api/history/${year}`),
};
