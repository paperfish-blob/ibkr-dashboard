/**
 * Data stores. Follows ui-reference/src/lib/stores.ts: a writable per feed,
 * plus a refresh function that flags loading, catches into an error store,
 * and always clears loading in a finally.
 */

import { get, writable, type Writable } from "svelte/store";
import { browser } from "$app/environment";
import {
  api,
  type HistoryStatus,
  type PnLResponse,
  type PositionsResponse,
  type TransactionsResponse,
} from "./api";

/** A writable mirrored into localStorage. Key convention: ibkr.<page>.<thing>. */
function persisted<T>(key: string, initial: T): Writable<T> {
  let start = initial;
  if (browser) {
    try {
      const raw = localStorage.getItem(key);
      if (raw !== null) start = JSON.parse(raw) as T;
    } catch {
      // Corrupt value -- fall back to the default rather than throwing on boot.
    }
  }
  const store = writable<T>(start);
  if (browser) {
    store.subscribe((v) => {
      try {
        localStorage.setItem(key, JSON.stringify(v));
      } catch {
        // Quota exceeded / private mode -- the store still works in memory.
      }
    });
  }
  return store;
}

// ── P&L ───────────────────────────────────────────────────────────────────────

export const pnl = writable<PnLResponse | null>(null);
export const pnlLoading = writable(true);
export const pnlError = writable<string | null>(null);

export async function refreshPnL(): Promise<void> {
  pnlError.set(null);
  try {
    pnl.set(await api.pnl(get(period)));
  } catch (e) {
    pnlError.set(e instanceof Error ? e.message : "Failed to load P&L");
  } finally {
    pnlLoading.set(false);
  }
}

// ── Transactions ──────────────────────────────────────────────────────────────

export const transactions = writable<TransactionsResponse | null>(null);
export const transactionsLoading = writable(true);
export const transactionsError = writable<string | null>(null);

export async function refreshTransactions(): Promise<void> {
  transactionsError.set(null);
  try {
    transactions.set(await api.transactions(get(period)));
  } catch (e) {
    transactionsError.set(e instanceof Error ? e.message : "Failed to load transactions");
  } finally {
    transactionsLoading.set(false);
  }
}

// ── Positions ─────────────────────────────────────────────────────────────────

export const positions = writable<PositionsResponse | null>(null);
export const positionsLoading = writable(true);
export const positionsError = writable<string | null>(null);

export async function refreshPositions(): Promise<void> {
  positionsError.set(null);
  try {
    positions.set(await api.positions(get(period)));
  } catch (e) {
    positionsError.set(e instanceof Error ? e.message : "Failed to load positions");
  } finally {
    positionsLoading.set(false);
  }
}

// ── Preferences ───────────────────────────────────────────────────────────────

export type TxFilter = "all" | "realized" | "opening";

/** Ledger filter. Defaults to showing every execution, opens included, the
 *  way IBKR's own apps do. Persisted so the choice survives a reload. */
export const txFilter = persisted<TxFilter>("ibkr.tx.filter", "all");

/** Symbols to show in the ledger. Empty means every symbol. Persisted like
 *  txFilter; a stale symbol from a since-changed period just filters to
 *  nothing rather than erroring, same as any other empty-result state. */
export const txSymbols = persisted<string[]>("ibkr.tx.symbols", []);

/** Collapse an order's partial fills into one ledger row. Off by default --
 *  it changes numbers people are used to reading per-execution (price,
 *  time), so it should be an opt-in rather than a surprise on load. */
export const txGroupFills = persisted<boolean>("ibkr.tx.groupFills", false);

export type PosFilter = "all" | "open" | "closed";

/** Positions filter, same idea as txFilter. */
export const posFilter = persisted<PosFilter>("ibkr.pos.filter", "all");

/** Symbols to show on the Positions page, same idea as txSymbols. */
export const posSymbols = persisted<string[]>("ibkr.pos.symbols", []);

/** Selected period: "all" or a four-digit year. Shared by Overview,
 *  Transactions and Positions so the choice follows you between them.
 *  Defaults to "all" so a freshly downloaded year shows up without anyone
 *  hunting for a setting. */
export const period = persisted<string>("ibkr.period", "all");

/** Re-fetch every period-scoped feed when the period changes. */
export function setPeriod(value: string): void {
  if (get(period) === value) return;
  period.set(value);
  pnlLoading.set(true);
  transactionsLoading.set(true);
  positionsLoading.set(true);
  void refreshPnL();
  void refreshTransactions();
  void refreshPositions();
}

// ── History / downloads ───────────────────────────────────────────────────────

const HISTORY_POLL_MS = 4000;

export const history = writable<HistoryStatus | null>(null);
export const historyError = writable<string | null>(null);

let historyPoll: ReturnType<typeof setInterval> | null = null;
let wasDownloading: number | null = null;

export async function refreshHistory(): Promise<void> {
  try {
    const status = await api.history();
    history.set(status);

    // A download just finished: what "all" covers has changed, so the other
    // two pages are now showing a stale view of the data.
    if (wasDownloading !== null && status.downloading === null) {
      void refreshPnL();
      void refreshTransactions();
    }
    wasDownloading = status.downloading;

    // Poll only while a download is actually running. A permanent 4s timer
    // against an idle server is the kind of thing that quietly runs forever.
    if (status.downloading !== null) startHistoryPoll();
    else stopHistoryPoll();
  } catch (e) {
    historyError.set(e instanceof Error ? e.message : "Failed to load history");
    stopHistoryPoll();
  }
}

function startHistoryPoll(): void {
  if (historyPoll !== null) return;
  historyPoll = setInterval(refreshHistory, HISTORY_POLL_MS);
}

export function stopHistoryPoll(): void {
  if (historyPoll === null) return;
  clearInterval(historyPoll);
  historyPoll = null;
}

/** Start a download. Returns the server's message so the page can show why
 *  nothing happened when it refuses. */
export async function downloadYear(year: number): Promise<{ started: boolean; message: string }> {
  historyError.set(null);
  try {
    const res = await api.downloadYear(year);
    await refreshHistory();
    if (res.started) {
      // A finished download changes what "all" covers.
      startHistoryPoll();
    }
    return res;
  } catch (e) {
    const message = e instanceof Error ? e.message : "Could not start the download";
    historyError.set(message);
    return { started: false, message };
  }
}
