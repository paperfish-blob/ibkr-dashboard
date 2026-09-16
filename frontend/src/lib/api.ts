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
  /** Shared by every execution that filled the same order; "" when the Flex
   *  Query omits IB Order ID. */
  ib_order_id: string;
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

/** One order's contribution to a position -- entry (added to it) or exit
 *  (reduced it). Already collapsed across that order's partial fills.
 *  quantity is always a positive magnitude; direction lives on Position. */
export interface PositionLeg {
  trade_date: IsoDate;
  trade_time: string;
  buy_sell: string;
  price: DecimalString | null;
  quantity: DecimalString;
  fill_count: number;
  realized_pnl: DecimalString;
  commission: DecimalString;
  /** "" when every fill shares one order, or the Flex Query omits IB Order ID. */
  ib_order_id: string;
  /** Share of the position's total size this exit accounts for. Exit legs
   *  only -- null on entry legs. */
  pct_of_position: DecimalString | null;
}

/** One round trip: a symbol's net quantity moving away from zero and
 *  (usually) back. */
export interface Position {
  symbol: string;
  asset_category: string;
  currency: string;
  direction: "long" | "short";
  is_open: boolean;
  /** The very first trade we see for this symbol already closes something --
   *  its opening trade happened before the fetched date range, so
   *  open_date/open_time/entry_price are unknown rather than guessed. */
  is_carry_in: boolean;
  open_date: IsoDate | null;
  open_time: string;
  entry_price: DecimalString | null;
  quantity: DecimalString;
  exit_date: IsoDate | null;
  exit_count: number;
  /** null while open with nothing realized yet. */
  realized_pnl: DecimalString | null;
  /** Summed across every entry and exit leg. */
  commission: DecimalString;
  entry_legs: PositionLeg[];
  exit_legs: PositionLeg[];
}

/** Position has no id of its own; these fields together identify one well
 *  enough in practice, and are what the detail page's URL carries. */
export function positionDetailParams(p: Position): URLSearchParams {
  return new URLSearchParams({
    symbol: p.symbol,
    open: p.open_date ?? "",
    openTime: p.open_time,
    exit: p.exit_date ?? "",
    dir: p.direction,
  });
}

/** The inverse of positionDetailParams -- resolves the detail page's query
 *  string back to the position it names. */
export function findPositionByParams(
  positions: Position[],
  params: URLSearchParams,
): Position | undefined {
  return positions.find(
    (p) =>
      p.symbol === params.get("symbol") &&
      (p.open_date ?? "") === (params.get("open") ?? "") &&
      p.open_time === (params.get("openTime") ?? "") &&
      (p.exit_date ?? "") === (params.get("exit") ?? "") &&
      p.direction === params.get("dir"),
  );
}

export interface PositionsResponse {
  /** Most recent activity first. */
  positions: Position[];
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

/** The cache file's own shape -- what /api/history/{year}/raw returns. */
export interface RawStatement {
  ok: boolean;
  trades: RealizedTrade[];
  fetched_at: IsoDateTime | null;
  account_id: string;
  error: string;
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
  positions: (period = "all"): Promise<PositionsResponse> =>
    get<PositionsResponse>(`/api/positions?period=${encodeURIComponent(period)}`),
  history: (): Promise<HistoryStatus> => get<HistoryStatus>("/api/history"),
  /** `started` is false when a download is already running -- only one runs
   *  at a time, and the message says which year holds the slot. */
  downloadYear: (year: number): Promise<{ started: boolean; message: string }> =>
    post<{ started: boolean; message: string }>(`/api/history/${year}`),
};

/** The raw cached statement for one year -- meant as a plain link target
 *  (`<a href={rawYearUrl(year)} target="_blank">`), not fetched from here.
 *  The browser's own JSON viewer is the whole UI: view-only by construction,
 *  since there is nothing on the page for a click to edit. */
export const rawYearUrl = (year: number): string => `/api/history/${year}/raw`;

/** A hover preview: the first `limit` trades only, so peeking at a year
 *  never pulls its whole statement across the wire. */
export const previewYear = (year: number, limit = 2): Promise<RawStatement> =>
  get<RawStatement>(`/api/history/${year}/raw?limit=${limit}`);
