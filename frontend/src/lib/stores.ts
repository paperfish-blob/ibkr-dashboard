/**
 * Data stores. Follows ui-reference/src/lib/stores.ts: a writable per feed,
 * plus a refresh function that flags loading, catches into an error store,
 * and always clears loading in a finally.
 */

import { writable, type Writable } from "svelte/store";
import { browser } from "$app/environment";
import { api, type PnLResponse, type TransactionsResponse } from "./api";

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

export async function refreshPnL(force = false): Promise<void> {
  pnlError.set(null);
  try {
    pnl.set(await api.pnl(force));
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

export async function refreshTransactions(force = false): Promise<void> {
  transactionsError.set(null);
  try {
    transactions.set(await api.transactions(force));
  } catch (e) {
    transactionsError.set(e instanceof Error ? e.message : "Failed to load transactions");
  } finally {
    transactionsLoading.set(false);
  }
}

// ── Preferences ───────────────────────────────────────────────────────────────

export type TxFilter = "all" | "realized";

/** Ledger filter. Defaults to showing every execution, opens included, the
 *  way IBKR's own apps do. Persisted so the choice survives a reload. */
export const txFilter = persisted<TxFilter>("ibkr.tx.filter", "all");
