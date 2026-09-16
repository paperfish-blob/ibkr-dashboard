<script lang="ts">
  /**
   * Per-trade ledger, grouped by day.
   *
   * "Realized only" / "Opening only" split trades client-side on
   * is_realizing; a day left with nothing is dropped entirely rather than
   * rendering an empty header. Day and grand totals are the same across all
   * three filters -- an opening trade's realized_pnl is exactly 0 -- so only
   * the counts move.
   *
   * groupFills collapses same-order executions into one row afterwards --
   * it changes what's rendered, not what's counted; the day header's count
   * and total, and the eyebrow's trade count, still reflect every execution.
   */
  import { fmtFullDate, fmtMoney, fmtPriceLike, fmtQty, num, toneOf, EM_DASH } from "$lib/format";
  import type { DayGroup, RealizedTrade } from "$lib/api";
  import type { TxFilter } from "$lib/stores";

  interface Props {
    days: DayGroup[];
    filter: TxFilter;
    groupFills?: boolean;
    currency?: string;
  }
  let { days, filter, groupFills = false, currency = "USD" }: Props = $props();

  type LedgerRow = RealizedTrade & { fillCount: number };

  /** Collapse the fills of one order (same ib_order_id) into a single row:
   *  quantity/commission/P&L sum, price is the quantity-weighted average, and
   *  the row is realizing if any fill closed part of a position. Trades from
   *  a Flex Query without IB Order ID (ib_order_id === "") never group --
   *  each stays its own row, same as before this existed. */
  function groupOrders(trades: RealizedTrade[]): LedgerRow[] {
    const byOrder = new Map<string, RealizedTrade[]>();
    const rows: LedgerRow[] = [];
    for (const t of trades) {
      if (!t.ib_order_id) {
        rows.push({ ...t, fillCount: 1 });
        continue;
      }
      const fills = byOrder.get(t.ib_order_id);
      if (fills) fills.push(t);
      else byOrder.set(t.ib_order_id, [t]);
    }
    for (const fills of byOrder.values()) {
      rows.push(fills.length === 1 ? { ...fills[0], fillCount: 1 } : aggregateFills(fills));
    }
    return rows.sort((a, b) => a.trade_time.localeCompare(b.trade_time));
  }

  function aggregateFills(fills: RealizedTrade[]): LedgerRow {
    const first = fills[0];
    const quantity = fills.reduce((s, f) => s + num(f.quantity), 0);
    const hasPrice = fills.every((f) => f.trade_price !== null);
    const hasMoney = fills.every((f) => f.trade_money !== null);
    const weightedPrice = hasPrice
      ? fills.reduce((s, f) => s + num(f.trade_price) * Math.abs(num(f.quantity)), 0) /
        (Math.abs(quantity) || 1)
      : null;
    const earliestTime = fills.reduce((min, f) => (!min || (f.trade_time && f.trade_time < min) ? f.trade_time : min), "");
    return {
      ...first,
      quantity: String(quantity),
      commission: String(fills.reduce((s, f) => s + num(f.commission), 0)),
      realized_pnl: String(fills.reduce((s, f) => s + num(f.realized_pnl), 0)),
      net_pnl: String(fills.reduce((s, f) => s + num(f.net_pnl), 0)),
      trade_money: hasMoney ? String(fills.reduce((s, f) => s + num(f.trade_money), 0)) : null,
      trade_price: weightedPrice === null ? null : String(weightedPrice),
      trade_time: earliestTime,
      is_realizing: fills.some((f) => f.is_realizing),
      fillCount: fills.length,
    };
  }

  const visible = $derived(
    filter === "all"
      ? days
      : days
          .map((d) => ({
            ...d,
            trades: d.trades.filter((t) => (filter === "realized" ? t.is_realizing : !t.is_realizing)),
          }))
          .filter((d) => d.trades.length > 0),
  );

  const displayDays = $derived(
    visible.map((d) => ({
      ...d,
      rows: groupFills ? groupOrders(d.trades) : (d.trades.map((t) => ({ ...t, fillCount: 1 })) as LedgerRow[]),
    })),
  );

  const tradeCount = $derived(visible.reduce((n, d) => n + d.trades.length, 0));

  // Price / Amount / Time only exist if the Flex Query exports Trade Price,
  // Trade Money and Date/Time. A query without them would otherwise render
  // three permanently empty columns, which reads as breakage rather than as
  // configuration. Hide what has no data anywhere; adding the fields to the
  // query brings the columns back on their own.
  const cols = $derived.by(() => {
    const all = days.flatMap((d) => d.trades);
    return {
      price: all.some((t) => t.trade_price !== null),
      amount: all.some((t) => t.trade_money !== null),
      commission: all.some((t) => num(t.commission) !== 0),
      time: all.some((t) => t.trade_time !== ""),
      orderId: all.some((t) => t.ib_order_id !== ""),
    };
  });
  const optionalCols = $derived(Object.values(cols).filter(Boolean).length);
  const COL_FIELDS: Record<string, string> = {
    price: "Trade Price",
    amount: "Trade Money",
    commission: "IB Commission",
    time: "Date/Time",
    orderId: "IB Order ID",
  };
  const missingFields = $derived(
    Object.entries(cols)
      .filter(([, present]) => !present)
      .map(([key]) => COL_FIELDS[key]),
  );
  /** Symbol, Side, Qty + whichever optional columns survive + Realized P&L. */
  const totalCols = $derived(3 + optionalCols + 1);
  /** The day band spans everything left of its trade-count and total cells. */
  const dayRowSpan = $derived(totalCols - 2);

  function sideLabel(buySell: string): string {
    const s = buySell.toUpperCase();
    if (s === "BUY") return "Bought";
    if (s === "SELL") return "Sold";
    return buySell || EM_DASH;
  }
  function sideClass(buySell: string): string {
    const s = buySell.toUpperCase();
    if (s === "BUY") return "buy";
    if (s === "SELL") return "sell";
    return "";
  }
</script>

<div class="panel">
  <div class="hd">
    <div class="hd-left">
      <div class="eyebrow">
        {tradeCount.toLocaleString()}
        {filter === "realized" ? "realizing trades" : filter === "opening" ? "opening trades" : "executions"}
      </div>
      <div class="title">Transactions</div>
    </div>

    {#if missingFields.length}
      <div
        class="hint"
        title="Add these fields to the Trades section of your Flex Query in Client Portal, then refresh."
      >
        {missingFields.join(" · ")} not in this Flex Query
      </div>
    {/if}
  </div>

  {#if visible.length === 0}
    <div class="empty">No trades in this statement period.</div>
  {:else}
    <div class="scroll">
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Side</th>
            <th class="num">Qty</th>
            {#if cols.price}<th class="num">Price</th>{/if}
            {#if cols.amount}<th class="num">Amount</th>{/if}
            {#if cols.commission}<th class="num">Comm.</th>{/if}
            {#if cols.time}<th class="num">Time</th>{/if}
            {#if cols.orderId}<th class="num">Order ID</th>{/if}
            <th class="num">Realized P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {#each displayDays as day (day.date)}
            {@const dayTone = toneOf(num(day.total_pnl))}
            <tr class="day-row">
              <td class="day-date" colspan={dayRowSpan}>{fmtFullDate(day.date)}</td>
              <td class="day-count num">{day.trades.length}</td>
              <td class="day-total num {dayTone}">{fmtMoney(num(day.total_pnl), currency)}</td>
            </tr>

            {#each day.rows as t, i (day.date + (t.ib_order_id || t.symbol + t.trade_time) + i)}
              <tr>
                <td class="sym">
                  {t.symbol}
                  {#if t.exchange}<span class="tag">{t.exchange}</span>{/if}
                  {#if t.asset_category}<span class="tag">{t.asset_category}</span>{/if}
                </td>
                <td>
                  <span class="side {sideClass(t.buy_sell)}">{sideLabel(t.buy_sell)}</span>
                  {#if t.order_type || t.notes_codes}
                    <span class="tag">{[t.order_type, t.notes_codes].filter(Boolean).join(" · ")}</span>
                  {/if}
                  {#if t.fillCount > 1}
                    <span class="tag fills" title="{t.fillCount} executions filled this order">
                      ×{t.fillCount} fills
                    </span>
                  {/if}
                </td>
                <td class="num">{fmtQty(num(t.quantity))}</td>
                {#if cols.price}
                  <td class="num">
                    {#if t.trade_price !== null}
                      {t.fillCount > 1 ? "≈" : ""}{fmtPriceLike(num(t.trade_price), t.currency, 4)}
                    {:else}<span class="dash">{EM_DASH}</span>{/if}
                  </td>
                {/if}
                {#if cols.amount}
                  <td class="num">
                    {#if t.trade_money !== null}
                      {fmtPriceLike(num(t.trade_money), t.currency, 2)}
                    {:else}<span class="dash">{EM_DASH}</span>{/if}
                  </td>
                {/if}
                {#if cols.commission}
                  <td class="num dim">
                    {#if num(t.commission) !== 0}
                      {fmtPriceLike(Math.abs(num(t.commission)), t.currency, 2)}
                    {:else}<span class="dash">{EM_DASH}</span>{/if}
                  </td>
                {/if}
                {#if cols.time}
                  <td class="num dim">{t.trade_time || EM_DASH}</td>
                {/if}
                {#if cols.orderId}
                  <td class="num dim order-id">{t.ib_order_id || EM_DASH}</td>
                {/if}
                <td class="num pnl">
                  {#if t.is_realizing}
                    <span class={toneOf(num(t.realized_pnl))}>
                      {fmtMoney(num(t.realized_pnl), t.currency)}
                    </span>
                  {:else}
                    <!-- An opening trade has no P&L yet: a dash, not a $0.00
                         that would read as a break-even close. -->
                    <span class="dash">{EM_DASH}</span>
                  {/if}
                </td>
              </tr>
            {/each}
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .panel {
    background: var(--surface);
    border: 1px solid var(--border-05);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }

  .hd {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 14px 22px;
    border-bottom: 1px solid var(--border-05);
  }
  .hd-left {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .eyebrow {
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--dim-55);
    font-variant-numeric: tabular-nums;
  }
  .title {
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    letter-spacing: -0.01em;
    color: var(--text);
  }

  .hint {
    font-size: var(--text-2xs);
    color: var(--dim-45);
    letter-spacing: 0.02em;
    text-align: right;
    cursor: help;
  }

  /* The table is denser than a phone is wide; it scrolls in its own box
     rather than forcing the page to scroll sideways. */
  .scroll {
    overflow-x: auto;
  }

  table {
    width: 100%;
    min-width: 760px;
    border-collapse: collapse;
    font-family: var(--font-sans);
    font-feature-settings: "ss01", "cv11";
  }

  th {
    padding: 8px 22px;
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--dim-70);
    text-align: left;
    white-space: nowrap;
    border-bottom: 1px solid var(--border-05);
    background: var(--surface);
  }
  th.num {
    text-align: right;
  }

  td {
    padding: 6px 22px;
    font-size: var(--text-xs);
    color: var(--text);
    text-align: left;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
    border-bottom: 1px solid var(--border-05);
  }
  td.num {
    text-align: right;
  }
  td.dim {
    color: var(--dim-70);
  }
  td.order-id {
    font-size: var(--text-2xs);
    color: var(--dim-45);
  }

  tbody tr:hover td {
    background: var(--surface-02);
  }

  /* Day group header: a full-width band carrying the date and that day's net. */
  .day-row td {
    background: var(--surface-04);
    border-bottom: 1px solid var(--border-08);
    padding-top: 9px;
    padding-bottom: 9px;
  }
  tbody tr.day-row:hover td {
    background: var(--surface-04);
  }
  .day-date {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--dim-70);
  }
  .day-count {
    font-size: var(--text-2xs);
    color: var(--dim-45);
  }
  .day-total {
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .sym {
    font-weight: var(--weight-bold);
  }
  .tag {
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    color: var(--dim-45);
    margin-left: 5px;
    letter-spacing: 0.02em;
  }
  .tag.fills {
    color: var(--accent);
    font-weight: var(--weight-semibold);
  }

  .side {
    font-weight: var(--weight-semibold);
  }
  .side.buy {
    color: var(--accent);
  }
  .side.sell {
    color: var(--dn);
  }

  .pnl {
    font-weight: var(--weight-semibold);
  }
  .pos {
    color: var(--up);
  }
  .neg {
    color: var(--dn);
  }
  .flat {
    color: var(--text);
  }
  .dash {
    color: var(--dim-35);
  }

  .empty {
    color: var(--dim-55);
    text-align: center;
    padding: 40px 0;
    font-size: var(--text-sm);
  }
</style>
