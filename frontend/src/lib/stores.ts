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
  type RoundTripsResponse,
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

// ── Round trips ──────────────────────────────────────────────────────────────

export const roundTrips = writable<RoundTripsResponse | null>(null);
export const roundTripsLoading = writable(true);
export const roundTripsError = writable<string | null>(null);

export async function refreshRoundTrips(): Promise<void> {
  roundTripsError.set(null);
  try {
    roundTrips.set(await api.roundTrips(get(period)));
  } catch (e) {
    roundTripsError.set(e instanceof Error ? e.message : "Failed to load round trips");
  } finally {
    roundTripsLoading.set(false);
  }
}

// ── Preferences ───────────────────────────────────────────────────────────────

export type TxFilter = "all" | "realized";

/** Ledger filter. Defaults to showing every execution, opens included, the
 *  way IBKR's own apps do. Persisted so the choice survives a reload. */
export const txFilter = persisted<TxFilter>("ibkr.tx.filter", "all");

/** Selected period: "all" or a four-digit year. Shared across every page that
 *  reads Flex data so the choice follows you between them. Defaults to "all"
 *  so a freshly downloaded year shows up without anyone hunting for a
 *  setting. */
export const period = persisted<string>("ibkr.period", "all");

/** Re-fetch every period-scoped feed when the period changes. */
export function setPeriod(value: string): void {
  if (get(period) === value) return;
  period.set(value);
  pnlLoading.set(true);
  transactionsLoading.set(true);
  roundTripsLoading.set(true);
  void refreshPnL();
  void refreshTransactions();
  void refreshRoundTrips();
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
    // pages are now showing a stale view of the data.
    if (wasDownloading !== null && status.downloading === null) {
      void refreshPnL();
      void refreshTransactions();
      void refreshRoundTrips();
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
