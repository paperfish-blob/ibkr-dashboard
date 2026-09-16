<script lang="ts">
  /**
   * Round-trip positions, one row per position with its entry/exit legs
   * dropping down on click. See src/ibkr_pnl/positions.py for how trades
   * become these -- this component only renders what the backend already
   * reconstructed.
   */
  import {
    fmtFullDate,
    fmtMoney,
    fmtPriceLike,
    fmtQty,
    num,
    sideClass,
    sideLabel,
    toneOf,
    EM_DASH,
  } from "$lib/format";
  import type { Position, PositionLeg } from "$lib/api";
  import type { PosGroupBy } from "$lib/stores";

  interface Props {
    positions: Position[];
    currency?: string;
    groupBy?: PosGroupBy;
  }
  let { positions, currency = "USD", groupBy = "exit" }: Props = $props();

  let expanded = $state<Set<number>>(new Set());
  function toggle(i: number) {
    const next = new Set(expanded);
    if (next.has(i)) next.delete(i);
    else next.add(i);
    expanded = next;
  }
  // Switching how rows are grouped reshuffles every index, so a previously
  // expanded row would otherwise land on whatever position now sits at that
  // index -- the wrong row appears open instead of nothing.
  $effect(() => {
    void groupBy;
    expanded = new Set();
  });

  /** Newest exit first, matching the rest of the app -- but numbered by
   *  when it actually happened, not by screen position, so "Exit 1" still
   *  means the first exit rather than the most recent one. */
  function numberedLegs(p: Position): { leg: PositionLeg; n: number }[] {
    return p.exit_legs.map((leg, i) => ({ leg, n: i + 1 })).reverse();
  }

  /** Gross trade value, same convention as the ledger's Amount column --
   *  positive for a buy, negative for a sell -- derived from price * qty
   *  since a position's price is already a weighted average, not a single
   *  execution's own trade_money. */
  function amount(price: string | null, quantity: string, buySell: string): number | null {
    if (price === null) return null;
    const sign = buySell.toUpperCase() === "SELL" ? -1 : 1;
    return sign * num(price) * num(quantity);
  }

  interface Row {
    p: Position;
    i: number;
  }
  interface DayGroup {
    date: string;
    rows: Row[];
  }

  /** The date a position's day band keys off, in the current mode --
   *  falling back the same way either direction: a carry-in has no entry
   *  date to group by, and a position with no exits yet has no exit date. */
  function groupDate(p: Position): string {
    return groupBy === "entry" ? (p.open_date ?? p.exit_date ?? "") : (p.exit_date ?? p.open_date ?? "");
  }

  /** Day bands, same as the ledger's. `positions` arrives most-recent-
   *  activity-first, which only clusters same-day rows together in exit
   *  mode -- entry mode re-sorts by open date first so same-day opens land
   *  adjacent too. Indexes are assigned after sorting so expand/collapse
   *  state (keyed by index) stays unique. */
  const displayGroups = $derived.by(() => {
    const ordered =
      groupBy === "entry"
        ? [...positions].sort((a, b) => groupDate(b).localeCompare(groupDate(a)))
        : positions;
    const groups: DayGroup[] = [];
    ordered.forEach((p, i) => {
      const date = groupDate(p);
      const last = groups.at(-1);
      if (last && last.date === date) last.rows.push({ p, i });
      else groups.push({ date, rows: [{ p, i }] });
    });
    return groups;
  });

  /** Symbol, Side, Qty + Price/Amount/Comm./Order ID + Realized P&L etc. */
  const totalCols = 14;
  /** The day band spans everything left of its count and total cells. */
  const dayRowSpan = totalCols - 2;
</script>

<div class="panel">
  {#if positions.length === 0}
    <div class="empty">No positions in this statement period.</div>
  {:else}
    <div class="scroll">
      <table>
        <thead>
          <tr>
            <th class="chev-col"></th>
            <th>Symbol</th>
            <th>Date</th>
            <th>Time</th>
            <th>Order ID</th>
            <th>Side</th>
            <th class="num">Qty</th>
            <th class="num">Price</th>
            <th class="num">Amount</th>
            <th class="num">Comm.</th>
            <th>Exit Date</th>
            <th class="num">Exits #</th>
            <th class="num">Pos %</th>
            <th class="num">Realized P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {#each displayGroups as group (group.date + group.rows[0].i)}
            {@const groupTotal = group.rows.reduce((sum, { p }) => sum + (p.realized_pnl === null ? 0 : num(p.realized_pnl)), 0)}
            <tr class="day-row">
              <td class="day-date" colspan={dayRowSpan}>{group.date ? fmtFullDate(group.date) : EM_DASH}</td>
              <td class="day-count num">{group.rows.length}</td>
              <td class="day-total num {toneOf(groupTotal)}">{fmtMoney(groupTotal, currency)}</td>
            </tr>

          {#each group.rows as { p, i } (p.symbol + (p.open_date ?? "") + p.open_time + (p.exit_date ?? "") + p.direction + i)}
            {@const canExpand = p.exit_legs.length > 0}
            {@const isExpanded = expanded.has(i)}
            {@const entryAmount = amount(p.entry_price, p.quantity, p.direction === "short" ? "SELL" : "BUY")}
            <tr
              class="pos-row"
              class:open={p.is_open}
              class:expanded={isExpanded}
              onclick={() => canExpand && toggle(i)}
            >
              <td>
                {#if canExpand}
                  <svg class="chev" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M6 4l4 4-4 4" />
                  </svg>
                {/if}
              </td>
              <td class="sym">{p.symbol} <span class="tag">{p.asset_category}</span></td>
              <td class="full-date">{p.open_date ? fmtFullDate(p.open_date) : EM_DASH}</td>
              <td class="dim">{p.open_time || EM_DASH}</td>
              <td class="num dash">{EM_DASH}</td>
              <td>
                <span class="dir {p.direction}">{p.direction.toUpperCase()}</span>
                {#if p.is_carry_in}
                  <span class="badge" title="Opened before the fetched date range -- entry date, price and true position size are unknown">
                    CARRY-IN
                  </span>
                {/if}
              </td>
              <td class="num">{fmtQty(num(p.quantity))}</td>
              <td class="num">{p.entry_price !== null ? fmtPriceLike(num(p.entry_price), currency, 4) : EM_DASH}</td>
              <td class="num">{entryAmount !== null ? fmtPriceLike(entryAmount, currency, 2) : EM_DASH}</td>
              <td class="num dim">{num(p.commission) !== 0 ? fmtPriceLike(Math.abs(num(p.commission)), currency, 2) : EM_DASH}</td>
              <td class="full-date {p.exit_date ? '' : 'dash'}">{p.exit_date ? fmtFullDate(p.exit_date) : EM_DASH}</td>
              <td class="num">{p.exit_count || EM_DASH}</td>
              <td class="num dash">{EM_DASH}</td>
              <td class="num pnl {p.realized_pnl === null ? '' : toneOf(num(p.realized_pnl))}">
                {p.realized_pnl === null ? "open" : fmtMoney(num(p.realized_pnl), currency)}
              </td>
            </tr>

            {#if isExpanded}
              {#each numberedLegs(p) as { leg, n } (n)}
                {@const legAmount = amount(leg.price, leg.quantity, leg.buy_sell)}
                <tr class="leg-row">
                  <td></td>
                  <td class="leg-label">Exit {n}</td>
                  <td class="full-date">{fmtFullDate(leg.trade_date)}</td>
                  <td class="dim">{leg.trade_time || EM_DASH}</td>
                  <td class="num dim order-id">{leg.ib_order_id || EM_DASH}</td>
                  <td>
                    <span class="side {sideClass(leg.buy_sell)}">{sideLabel(leg.buy_sell)}</span>
                    {#if leg.fill_count > 1}<span class="fills">×{leg.fill_count} fills</span>{/if}
                  </td>
                  <td class="num">−{fmtQty(num(leg.quantity))}</td>
                  <td class="num">{leg.price !== null ? fmtPriceLike(num(leg.price), p.currency, 4) : EM_DASH}</td>
                  <td class="num">{legAmount !== null ? fmtPriceLike(legAmount, p.currency, 2) : EM_DASH}</td>
                  <td class="num dim">{num(leg.commission) !== 0 ? fmtPriceLike(Math.abs(num(leg.commission)), p.currency, 2) : EM_DASH}</td>
                  <td></td>
                  <td></td>
                  <td class="num">{leg.pct_of_position !== null ? `${num(leg.pct_of_position).toFixed(1)}%` : EM_DASH}</td>
                  <td class="num pnl {toneOf(num(leg.realized_pnl))}">{fmtMoney(num(leg.realized_pnl), p.currency)}</td>
                </tr>
              {/each}
            {/if}
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

  .scroll {
    overflow-x: auto;
  }

  table {
    width: 100%;
    min-width: 900px;
    border-collapse: collapse;
    font-family: var(--font-sans);
    font-feature-settings: "ss01", "cv11";
    font-variant-numeric: tabular-nums;
  }

  th {
    padding: 8px 16px;
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.07em;
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
  .chev-col {
    width: 30px;
  }

  td {
    padding: 8px 16px;
    font-size: var(--text-xs);
    color: var(--text);
    white-space: nowrap;
    border-bottom: 1px solid var(--border-05);
  }
  td.num {
    text-align: right;
  }
  td.dim {
    color: var(--dim-70);
  }
  td.dash {
    color: var(--dim-35);
  }
  td.order-id {
    font-size: var(--text-2xs);
    color: var(--dim-45);
  }
  td.full-date {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--dim-70);
  }
  td.full-date.dash {
    color: var(--dim-35);
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

  tr.pos-row {
    cursor: pointer;
  }
  tr.pos-row:hover td {
    background: var(--surface-02);
  }
  tr.pos-row.open td {
    background: var(--surface-04);
  }

  .chev {
    display: inline-flex;
    width: 13px;
    height: 13px;
    color: var(--dim-45);
    transition: transform 0.15s;
  }
  tr.pos-row.expanded .chev {
    transform: rotate(90deg);
    color: var(--text);
  }

  .sym {
    font-weight: var(--weight-bold);
  }
  .sym .tag {
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    color: var(--dim-45);
    margin-left: 5px;
  }

  .dir {
    display: inline-block;
    font-size: var(--text-2xs);
    font-weight: var(--weight-bold);
    letter-spacing: 0.04em;
    padding: 3px 8px;
    border-radius: var(--radius-pill);
  }
  .dir.long {
    background: var(--accent-bg);
    color: var(--accent);
  }
  .dir.short {
    background: var(--ai-bg);
    color: var(--ai);
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

  .badge {
    display: inline-block;
    font-size: var(--text-2xs);
    font-weight: var(--weight-bold);
    letter-spacing: 0.04em;
    padding: 3px 8px;
    border-radius: var(--radius-pill);
    margin-left: 5px;
    background: transparent;
    color: var(--dim-45);
    border: 1px dashed var(--border);
    cursor: help;
  }

  .pnl {
    font-weight: var(--weight-semibold);
  }
  .pnl.pos {
    color: var(--up);
  }
  .pnl.neg {
    color: var(--dn);
  }
  .pnl.flat {
    color: var(--text);
  }

  tr.leg-row td {
    background: var(--surface-04);
    border-bottom: 1px solid var(--border-08);
  }
  tr.leg-row:last-of-type td {
    border-bottom: 2px solid var(--border-08);
  }
  .leg-label {
    color: var(--dim-45);
    font-weight: var(--weight-semibold);
    padding-left: 38px;
  }
  .fills {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    color: var(--accent);
    margin-left: 6px;
  }

  .empty {
    color: var(--dim-55);
    text-align: center;
    padding: 40px 0;
    font-size: var(--text-sm);
  }
</style>
