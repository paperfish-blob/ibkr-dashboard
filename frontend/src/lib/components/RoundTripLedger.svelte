<script lang="ts">
  /**
   * FIFO-matched round trips, grouped by the day each one closed.
   *
   * Grouped by closed_date, not opened_date: a round trip belongs to the day
   * its outcome landed, matching how Transactions groups executions by the
   * day they happened. A round trip's own opened date can fall on an
   * earlier day (or be unknown entirely -- see opened_date), which is why
   * it's shown per-row rather than as its own grouping.
   */
  import { fmtDay, fmtFullDate, fmtMoney, fmtPriceLike, fmtQty, num, toneOf, EM_DASH } from "$lib/format";
  import type { RealizedTrade, RoundTrip } from "$lib/api";

  interface Props {
    roundTrips: RoundTrip[]; // newest closed first
    currency?: string;
  }
  let { roundTrips, currency = "USD" }: Props = $props();

  const ROWS_PER_PAGE = 20;
  let shownDays = $state(ROWS_PER_PAGE);

  // Click a row to see the executions it was matched from. Keyed by
  // identity, not index: a Set survives "Show more" appending further days
  // without losing track of what's already open.
  function rowKey(rt: RoundTrip): string {
    return `${rt.symbol}|${rt.closed_time}|${rt.opened_time}|${rt.quantity}`;
  }
  let expanded = $state(new Set<string>());
  function toggle(key: string): void {
    const next = new Set(expanded);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    expanded = next;
  }

  interface DayGroup {
    date: string;
    total: number;
    rows: RoundTrip[];
  }

  const days = $derived.by((): DayGroup[] => {
    const by = new Map<string, RoundTrip[]>();
    for (const rt of roundTrips) {
      const bucket = by.get(rt.closed_date);
      if (bucket) bucket.push(rt);
      else by.set(rt.closed_date, [rt]);
    }
    // roundTrips already arrives newest-closed-first, so Map insertion order
    // already matches -- no separate sort needed.
    return [...by.entries()].map(([date, rows]) => ({
      date,
      rows,
      total: rows.reduce((sum, r) => sum + num(r.realized_pnl), 0),
    }));
  });

  const page = $derived(days.slice(0, shownDays));
  const hasMore = $derived(shownDays < days.length);

  function openedLabel(rt: RoundTrip): string {
    if (rt.opened_date === null) return "Before window";
    if (rt.opened_date === rt.closed_date) return rt.opened_time || EM_DASH;
    return `${fmtDay(rt.opened_date)} ${rt.opened_time}`.trim();
  }

  /** Wall-clock duration between two same-day times, or day-granularity
   *  across days -- there's no sub-day precision once the dates differ, and
   *  claiming otherwise (via a made-up 00:00:00) would be more precise than
   *  the data actually is. */
  function held(rt: RoundTrip): string {
    if (rt.opened_date === null) return EM_DASH;
    if (rt.opened_date === rt.closed_date && rt.opened_time && rt.closed_time) {
      const [oh, om, os] = rt.opened_time.split(":").map(Number);
      const [ch, cm, cs] = rt.closed_time.split(":").map(Number);
      const seconds = ch * 3600 + cm * 60 + cs - (oh * 3600 + om * 60 + os);
      if (seconds < 60) return `${seconds}s`;
      if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
      return `${Math.round(seconds / 3600)}h`;
    }
    const dayCount = Math.round(
      (Date.parse(rt.closed_date) - Date.parse(rt.opened_date)) / 86_400_000,
    );
    return `${dayCount}d`;
  }

  function sideLabel(buySell: string): string {
    const s = buySell.toUpperCase();
    if (s === "BUY") return "Bought";
    if (s === "SELL") return "Sold";
    return buySell || EM_DASH;
  }
</script>

{#snippet execution(trade: RealizedTrade)}
  <div class="exec">
    <div class="exec-row">
      <span class="side {trade.buy_sell.toUpperCase() === 'BUY' ? 'long' : 'short'}">
        {sideLabel(trade.buy_sell)}
      </span>
      <span>{fmtQty(num(trade.quantity))} sh</span>
      {#if trade.trade_price !== null}
        <span class="dim">@ {fmtPriceLike(num(trade.trade_price), trade.currency, 4)}</span>
      {/if}
    </div>
    <div class="exec-row dim">
      {trade.trade_date}
      {trade.trade_time || EM_DASH}
      {#if trade.exchange}· {trade.exchange}{/if}
      {#if trade.order_type || trade.notes_codes}
        · {[trade.order_type, trade.notes_codes].filter(Boolean).join(" ")}
      {/if}
    </div>
    <div class="exec-row dim">
      {#if trade.trade_money !== null}
        Amount {fmtPriceLike(num(trade.trade_money), trade.currency, 2)}
      {/if}
      {#if num(trade.commission) !== 0}
        · Comm. {fmtPriceLike(Math.abs(num(trade.commission)), trade.currency, 2)}
      {/if}
    </div>
  </div>
{/snippet}

<div class="panel">
  <div class="hd">
    <div class="hd-left">
      <div class="eyebrow">{roundTrips.length.toLocaleString()} round trips</div>
      <div class="title">Round Trips</div>
    </div>
  </div>

  {#if days.length === 0}
    <div class="empty">No completed round trips in this period.</div>
  {:else}
    <div class="scroll">
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Side</th>
            <th class="num">Qty</th>
            <th>Opened</th>
            <th class="num">Entry</th>
            <th>Closed</th>
            <th class="num">Exit</th>
            <th class="num">Held</th>
            <th class="num">Realized P&amp;L</th>
            <th class="num">Comm.</th>
            <th class="num">Net P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {#each page as day (day.date)}
            {@const dayTone = toneOf(day.total)}
            <tr class="day-row">
              <td class="day-date" colspan={9}>{fmtFullDate(day.date)}</td>
              <td class="day-count num">{day.rows.length}</td>
              <td class="day-total num {dayTone}">{fmtMoney(day.total, currency)}</td>
            </tr>

            {#each day.rows as rt, i (rt.symbol + rt.closed_time + rt.quantity + i)}
              {@const key = rowKey(rt)}
              {@const isOpen = expanded.has(key)}
              <tr class="clickable" class:open={isOpen} onclick={() => toggle(key)}>
                <td class="sym">
                  <span class="chevron" class:open={isOpen}>▸</span>
                  {rt.symbol}
                  {#if rt.asset_category}<span class="tag">{rt.asset_category}</span>{/if}
                </td>
                <td><span class="side {rt.side}">{rt.side === "long" ? "Long" : "Short"}</span></td>
                <td class="num">{fmtQty(num(rt.quantity))}</td>
                <td class:dim={rt.opened_date === null}>{openedLabel(rt)}</td>
                <td class="num">
                  {#if rt.open_price !== null}
                    {fmtPriceLike(num(rt.open_price), rt.currency, 4)}
                  {:else}<span class="dash">{EM_DASH}</span>{/if}
                </td>
                <td>{rt.closed_time || EM_DASH}</td>
                <td class="num">
                  {#if rt.close_price !== null}
                    {fmtPriceLike(num(rt.close_price), rt.currency, 4)}
                  {:else}<span class="dash">{EM_DASH}</span>{/if}
                </td>
                <td class="num dim">{held(rt)}</td>
                <td class="num pnl">
                  <span class={toneOf(num(rt.realized_pnl))}>
                    {fmtMoney(num(rt.realized_pnl), rt.currency)}
                  </span>
                </td>
                <td class="num dim">
                  {#if num(rt.commission) !== 0}
                    {fmtPriceLike(Math.abs(num(rt.commission)), rt.currency, 2)}
                  {:else}<span class="dash">{EM_DASH}</span>{/if}
                </td>
                <td class="num pnl">
                  <span class={toneOf(num(rt.net_pnl))}>{fmtMoney(num(rt.net_pnl), rt.currency)}</span>
                </td>
              </tr>
              {#if isOpen}
                <tr class="detail-row">
                  <td colspan={11}>
                    <div class="detail">
                      <div class="detail-col">
                        <div class="detail-label">Opening execution</div>
                        {#if rt.opening_trade}
                          {@render execution(rt.opening_trade)}
                        {:else}
                          <div class="detail-empty">
                            No execution on record — this position was already open
                            when the downloaded history begins.
                          </div>
                        {/if}
                      </div>
                      <div class="detail-col">
                        <div class="detail-label">Closing execution</div>
                        {@render execution(rt.closing_trade)}
                      </div>
                    </div>
                  </td>
                </tr>
              {/if}
            {/each}
          {/each}
        </tbody>
      </table>
    </div>

    {#if hasMore}
      <button class="more" onclick={() => (shownDays += ROWS_PER_PAGE)}>
        Show more — {days.length - shownDays} more {days.length - shownDays === 1 ? "day" : "days"}
      </button>
    {/if}
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

  .scroll {
    overflow-x: auto;
  }

  table {
    width: 100%;
    min-width: 920px;
    border-collapse: collapse;
    font-family: var(--font-sans);
    font-feature-settings: "ss01", "cv11";
  }

  th {
    padding: 8px 18px;
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
    padding: 6px 18px;
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

  tbody tr:hover td {
    background: var(--surface-02);
  }

  tr.clickable {
    cursor: pointer;
  }
  .chevron {
    display: inline-block;
    margin-right: 6px;
    color: var(--dim-45);
    transition: transform 0.15s;
  }
  .chevron.open {
    transform: rotate(90deg);
  }

  tr.detail-row td {
    padding: 0;
    background: var(--surface-02);
    border-bottom: 1px solid var(--border-08);
  }
  .detail {
    display: flex;
    flex-wrap: wrap;
    gap: 24px;
    padding: 14px 18px 16px calc(18px + 15px); /* left-align under the chevron */
    white-space: normal;
  }
  .detail-col {
    min-width: 220px;
  }
  .detail-label {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--dim-45);
    margin-bottom: 6px;
  }
  .detail-empty {
    font-size: var(--text-xs);
    color: var(--dim-55);
    max-width: 320px;
    line-height: 1.4;
  }
  .exec {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .exec-row {
    font-size: var(--text-xs);
    display: flex;
    gap: 6px;
    align-items: baseline;
    font-variant-numeric: tabular-nums;
  }
  .exec-row.dim {
    color: var(--dim-55);
    font-size: var(--text-2xs);
  }
  .exec-row .dim {
    color: var(--dim-55);
  }

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

  .side {
    font-weight: var(--weight-semibold);
  }
  .side.long {
    color: var(--accent);
  }
  .side.short {
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

  .more {
    display: block;
    width: 100%;
    padding: 11px;
    border: none;
    border-top: 1px solid var(--border-05);
    background: var(--surface);
    color: var(--dim-55);
    font-family: var(--font-sans);
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
    cursor: pointer;
    transition:
      background 0.15s,
      color 0.15s;
  }
  .more:hover {
    background: var(--surface-06);
    color: var(--text);
  }
</style>
