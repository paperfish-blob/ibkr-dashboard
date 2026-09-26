/**
 * Formatting helpers.
 *
 * Every function here takes the raw API value (usually a DecimalString) and
 * returns display text. The house rules, carried over from ui-reference:
 * signed values always show an explicit "+", and a missing value is an em
 * dash rather than a zero.
 */

import type { DecimalString } from "./api";

export const EM_DASH = "—";

export type Tone = "pos" | "neg" | "flat";

/** Tone is computed here and applied as a CSS class -- never an inline colour. */
export function toneOf(n: number): Tone {
  if (n > 0) return "pos";
  if (n < 0) return "neg";
  return "flat";
}

/** "BUY"/"SELL" (however the Flex Query cases it) -> "Bought"/"Sold". Shared
 *  by the Transactions and Positions pages so a trade reads the same word
 *  wherever it shows up. */
export function sideLabel(buySell: string): string {
  const s = buySell.toUpperCase();
  if (s === "BUY") return "Bought";
  if (s === "SELL") return "Sold";
  return buySell || EM_DASH;
}

/** CSS class for sideLabel's counterpart -- "buy" / "sell" / "". */
export function sideClass(buySell: string): string {
  const s = buySell.toUpperCase();
  if (s === "BUY") return "buy";
  if (s === "SELL") return "sell";
  return "";
}

/** DecimalString -> number. Pydantic sends Decimals as strings; this is the
 *  single place that conversion is allowed to happen sloppily. */
export function num(value: DecimalString | number | null | undefined): number {
  if (value === null || value === undefined || value === "") return 0;
  return Number(value);
}

/** Gross trade value -- positive for a buy, negative for a sell -- derived
 *  from price * quantity rather than a stored trade_money, since a
 *  position's leg price is already a weighted average across its fills, not
 *  any single execution's own amount. Shared by the Positions table and its
 *  detail page. */
export function grossAmount(
  price: DecimalString | null,
  quantity: DecimalString,
  buySell: string,
): number | null {
  if (price === null) return null;
  const sign = buySell.toUpperCase() === "SELL" ? -1 : 1;
  return sign * num(price) * num(quantity);
}

/** Signed currency: "+$1,234.56" / "-$1,234.56". Zero shows unsigned. */
export function fmtMoney(value: number, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency || "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    signDisplay: "exceptZero",
  }).format(value);
}

/** Plain number with a fixed floor of 2 decimals and a variable ceiling. */
export function fmtNum(value: number, maxFrac = 2): string {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: maxFrac,
  }).format(value);
}

/** Absolute quantity, no decimals. */
export function fmtQty(value: number): string {
  return new Intl.NumberFormat("en-US").format(Math.abs(value));
}

const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: "$",
  EUR: "€",
  GBP: "£",
  JPY: "¥",
};

/**
 * Unsigned money for prices and gross amounts.
 *
 * The symbol is prefixed by hand rather than using Intl's currency style,
 * because that style forces a fixed fraction count -- and a fill price needs
 * more precision than an amount does.
 */
export function fmtPriceLike(value: number, currency = "USD", maxFrac = 2): string {
  const symbol = CURRENCY_SYMBOLS[currency] ?? `${currency} `;
  return symbol + fmtNum(value, maxFrac);
}

/** Compact axis/label date: "Sep 11". */
export function fmtDay(iso: string): string {
  return parseISODay(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** Same as fmtDay, plus a 2-digit year -- for a pair of dates close enough
 *  together that bare month/day alone can't tell which year either one
 *  fell in (a streak or trade spanning New Year's, several years of
 *  history compressed into one compact row). */
export function fmtDayYear(iso: string): string {
  return `${fmtDay(iso)} '${String(parseISODay(iso).getFullYear()).slice(-2)}`;
}

/** Full date for day-group headers: "September 11, 2026". */
export function fmtFullDate(iso: string): string {
  return parseISODay(iso).toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

/** Whole days between an ISO date and today (local calendar days, not a
 *  24h-multiple), for "how long has this been open" -- floored so a
 *  position opened earlier today reads as 0d rather than a fraction. */
export function daysSince(iso: string): number {
  const then = parseISODay(iso);
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.max(0, Math.round((startOfToday.getTime() - then.getTime()) / 86_400_000));
}

/** Clock time from an ISO timestamp: "4:20 PM". Null renders as an em dash. */
export function fmtTime(iso: string | null): string {
  if (!iso) return EM_DASH;
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

/** Compact date + clock time from an ISO timestamp: "Sep 23, 4:20 PM" --
 *  for a timestamp that could be from any past day (e.g. a year downloaded
 *  once and never refetched), where the bare time alone doesn't say which
 *  day it happened. Null renders as an em dash. */
export function fmtDateTime(iso: string | null): string {
  if (!iso) return EM_DASH;
  const d = new Date(iso);
  return `${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })}, ${fmtTime(iso)}`;
}

/**
 * "YYYY-MM-DD" -> local Date at midnight.
 *
 * Parsed field by field rather than via `new Date(iso)`: the Date constructor
 * reads a bare ISO date as UTC midnight, which shifts the day back one in any
 * timezone west of Greenwich.
 */
export function parseISODay(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}
