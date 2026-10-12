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
    grossAmount,
    num,
    parseISODay,
    sideClass,
    sideLabel,
    toneOf,
    EM_DASH,
  } from "$lib/format";
  import { positionDetailParams, type Position, type PositionLeg } from "$lib/api";
  import type { PosGroupBy } from "$lib/stores";
  import SegToggle from "./SegToggle.svelte";

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

  /** Open/closed status, with carry-in folded in as a qualifier on
   *  whichever of the three applies rather than a 4th exclusive value --
   *  a carry-in position (the first trade we ever see for it already
   *  closes something opened before the fetched date range) has by
   *  definition already had at least one exit, so it can pair with
   *  "closed" or "partial" but never with "full". */
  function statusInfo(p: Position): { label: string; cls: string; carryIn: boolean } {
    const carryIn = p.is_carry_in;
    if (!p.is_open) return { label: "Closed", cls: "closed", carryIn };
    if (p.exit_count > 0) return { label: "Open (Partial)", cls: "partial", carryIn };
    return { label: "Open (Full)", cls: "full", carryIn };
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

  /** The time-of-day a position is ordered by inside its day band: the same
   *  event groupDate() keys the band off (entry -> open time, exit -> last
   *  exit leg's time), including its fallbacks, so the order always agrees
   *  with the band's own date. */
  function exitTime(p: Position): string {
    return p.exit_legs[p.exit_legs.length - 1]?.trade_time ?? "";
  }
  function groupTime(p: Position): string {
    const byExit = groupBy === "exit" ? p.exit_date !== null : p.open_date === null;
    return (byExit ? exitTime(p) : p.open_time) ?? "";
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
    // Latest first inside each band. Array#sort is stable, so ties (and
    // positions with no time at all) keep their incoming order.
    for (const g of groups) g.rows.sort((a, b) => groupTime(b.p).localeCompare(groupTime(a.p)));
    return groups;
  });

  /** Symbol, Status, Side, Qty + Price/Amount/Comm./Order ID + Realized P&L etc. */
  const totalCols = 15;
  /** The day band spans everything left of its count and total cells. */
  const dayRowSpan = totalCols - 2;

  /** How many trading days elapsed between one day band and the previous
   *  one -- weekends never count, since the market isn't open then anyway,
   *  so a Friday -> Monday pair of trades shouldn't read as a 3-day gap.
   *  Counts every weekday strictly between the two dates, so trades on
   *  consecutive trading days (or Friday -> Monday) show no gap -- it's how
   *  many trading days sat idle in between. */
  function tradingDayGap(newer: string, older: string): number {
    let count = 0;
    const cursor = parseISODay(older);
    const end = parseISODay(newer);
    cursor.setDate(cursor.getDate() + 1);
    while (cursor < end) {
      const wd = cursor.getDay();
      if (wd !== 0 && wd !== 6) count++;
      cursor.setDate(cursor.getDate() + 1);
    }
    return count;
  }

  interface GapDay {
    abbr: string;
    dateNum: number;
    isWeekend: boolean;
  }
  const WEEKDAY_ABBR = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const WEEKDAY_FULL = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  /** Which weekday a date fell on -- shown next to every date this table
   *  displays (day bands, and each row's own Date/Exit Date/leg date) so a
   *  gap's Mon/Tue/Wed breakdown isn't the only place that context shows up. */
  function weekdayAbbr(iso: string): string {
    return WEEKDAY_ABBR[parseISODay(iso).getDay()];
  }
  function weekdayFull(iso: string): string {
    return WEEKDAY_FULL[parseISODay(iso).getDay()];
  }

  /** Every calendar day strictly between the two dates -- the same walk tradingDayGap does, but keeping each day instead
   *  of just the count, for the hover tooltip's Mon/Tue/Wed breakdown. */
  function gapDayBreakdown(newer: string, older: string): GapDay[] {
    const days: GapDay[] = [];
    const cursor = parseISODay(older);
    const end = parseISODay(newer);
    cursor.setDate(cursor.getDate() + 1);
    while (cursor < end) {
      const wd = cursor.getDay();
      days.push({ abbr: WEEKDAY_ABBR[wd], dateNum: cursor.getDate(), isWeekend: wd === 0 || wd === 6 });
      cursor.setDate(cursor.getDate() + 1);
    }
    return days;
  }

  /** "All" by default -- "all" and up show every gap of at least that many
   *  trading days (0 included, as a "consecutive" marker); "off" shows none. */
  type GapFilter = "off" | "all" | "3" | "7";
  let gapFilter = $state<GapFilter>("all");
  const minGapDays = $derived(gapFilter === "off" ? null : gapFilter === "all" ? 0 : Number(gapFilter));
  const GAP_OPTIONS = [
    { label: "All", value: "all" },
    { label: "Off", value: "off" },
    { label: "3+ days", value: "3" },
    { label: "7+ days", value: "7" },
  ];
</script>

<div class="panel">
  {#if positions.length === 0}
    <div class="empty">No positions in this statement period.</div>
  {:else}
    <div class="gap-filter-row">
      <span class="gap-filter-label">Show trading-day gaps</span>
      <SegToggle options={GAP_OPTIONS} active={gapFilter} onChange={(v) => (gapFilter = v as GapFilter)} />
    </div>
    <div class="scroll">
      <table>
        <thead>
          <tr>
            <th class="chev-col"></th>
            <th>Symbol</th>
            <th>Status</th>
            <th class="num">Exits #</th>
            <th>Date</th>
            <th>Time</th>
            <th>Order ID</th>
            <th>Side</th>
            <th class="num">Qty</th>
            <th class="num">Price</th>
            <th class="num">Amount</th>
            <th class="num">Comm.</th>
            <th>Exit Date</th>
            <th class="num">Pos %</th>
            <th class="num">Realized P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {#each displayGroups as group, gi (group.date + group.rows[0].i)}
            {@const groupTotal = group.rows.reduce((sum, { p }) => sum + (p.realized_pnl === null ? 0 : num(p.realized_pnl)), 0)}
            <tr class="day-row">
              <td class="day-date" colspan={dayRowSpan}>
                {group.date ? fmtFullDate(group.date) : EM_DASH}
                {#if group.date}<span class="wd">&middot; {weekdayFull(group.date)}</span>{/if}
              </td>
              <td class="day-count num">{group.rows.length}</td>
              <td class="day-total num {toneOf(groupTotal)}">{fmtMoney(groupTotal, currency)}</td>
            </tr>

          {#each group.rows as { p, i } (p.symbol + (p.open_date ?? "") + p.open_time + (p.exit_date ?? "") + p.direction + i)}
            {@const canExpand = p.exit_legs.length > 0}
            {@const isExpanded = expanded.has(i)}
            {@const entryAmount = grossAmount(p.entry_price, p.quantity, p.direction === "short" ? "SELL" : "BUY")}
            {@const status = statusInfo(p)}
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
              <td class="sym">
                <a
                  class="sym-link"
                  href="/positions/detail?{positionDetailParams(p)}"
                  target="_blank"
                  rel="noopener"
                  onclick={(e) => e.stopPropagation()}
                >
                  {p.symbol}
                </a>
                <span class="tag">{p.asset_category}</span>
              </td>
              <td>
                <span
                  class="status {status.cls}"
                  title={status.carryIn
                    ? "Opened before the fetched date range -- entry date, price and true position size are unknown"
                    : undefined}
                >
                  {status.label}{#if status.carryIn}<span class="q"> · Carry-in</span>{/if}
                </span>
              </td>
              <td class="num">{p.exit_count || EM_DASH}</td>
              <td class="full-date">
                {p.open_date ? fmtFullDate(p.open_date) : EM_DASH}
                {#if p.open_date}<span class="wd-abbr">{weekdayAbbr(p.open_date)}</span>{/if}
              </td>
              <td class="dim">{p.open_time || EM_DASH}</td>
              <td class="num dash">{EM_DASH}</td>
              <td>
                <span class="dir {p.direction}">{p.direction.toUpperCase()}</span>
              </td>
              <td class="num">{fmtQty(num(p.quantity))}</td>
              <td class="num">{p.entry_price !== null ? fmtPriceLike(num(p.entry_price), currency, 4) : EM_DASH}</td>
              <td class="num">{entryAmount !== null ? fmtPriceLike(entryAmount, currency, 2) : EM_DASH}</td>
              <td class="num dim">{num(p.commission) !== 0 ? fmtPriceLike(Math.abs(num(p.commission)), currency, 2) : EM_DASH}</td>
              <td class="full-date {p.exit_date ? '' : 'dash'}">
                {p.exit_date ? fmtFullDate(p.exit_date) : EM_DASH}
                {#if p.exit_date}<span class="wd-abbr">{weekdayAbbr(p.exit_date)}</span>{/if}
                {#if exitTime(p)}<span class="wd-abbr">{exitTime(p)}</span>{/if}
              </td>
              <td class="num dash">{EM_DASH}</td>
              <td class="num pnl {p.realized_pnl === null ? '' : toneOf(num(p.realized_pnl))}">
                {p.realized_pnl === null ? "open" : fmtMoney(num(p.realized_pnl), currency)}
              </td>
            </tr>

            {#if isExpanded}
              {#each numberedLegs(p) as { leg, n } (n)}
                {@const legAmount = grossAmount(leg.price, leg.quantity, leg.buy_sell)}
                <tr class="leg-row">
                  <td></td>
                  <td></td>
                  <td></td>
                  <td class="leg-label">Exit {n}</td>
                  <td class="full-date">{fmtFullDate(leg.trade_date)} <span class="wd-abbr">{weekdayAbbr(leg.trade_date)}</span></td>
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
                  <td class="num">{leg.pct_of_position !== null ? `${num(leg.pct_of_position).toFixed(1)}%` : EM_DASH}</td>
                  <td class="num pnl {toneOf(num(leg.realized_pnl))}">{fmtMoney(num(leg.realized_pnl), p.currency)}</td>
                </tr>
              {/each}
            {/if}
          {/each}

          {#if minGapDays !== null && gi < displayGroups.length - 1 && group.date && displayGroups[gi + 1].date}
            {@const gap = tradingDayGap(group.date, displayGroups[gi + 1].date)}
            {#if gap >= minGapDays}
              {@const days = gapDayBreakdown(group.date, displayGroups[gi + 1].date)}
              <tr class="gap-row" class:consecutive={gap === 0}>
                <td colspan={totalCols}>
                  <div class="gap-line">
                    <span class="gap-rule"></span>
                    {#if gap === 0}
                      <span class="gap-pill"><span class="gap-dot"></span>Consecutive trading days</span>
                    {:else}
                    <button type="button" class="gap-hover">
                      <span class="gap-pill"
                        ><span class="gap-dot"></span>{gap} trading day{gap === 1 ? "" : "s"} without a trade</span
                      >
                      <span class="gap-tip">
                        <span class="gap-tip-title">{gap} trading day{gap === 1 ? "" : "s"} without a trade</span>
                        <span class="gap-tip-days">
                          {#each days as day}
                            <span class="day-chip" class:weekend={day.isWeekend}>
                              <span class="day-abbr">{day.abbr}</span>
                              <span class="day-num">{day.dateNum}</span>
                            </span>
                          {/each}
                        </span>
                        <span class="gap-tip-foot">
                          {fmtFullDate(displayGroups[gi + 1].date)} &rarr; {fmtFullDate(group.date)} &middot; weekends excluded
                        </span>
                        <span class="gap-tip-arrow"></span>
                      </span>
                    </button>
                    {/if}
                    <span class="gap-rule"></span>
                  </div>
                </td>
              </tr>
            {/if}
          {/if}
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
    /* Not overflow:hidden -- the gap tooltip pops up above its row and
       needs to escape this panel rather than get clipped at its edge. */
  }

  .gap-filter-row {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 10px;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border-05);
  }
  .gap-filter-label {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--dim-45);
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
  .wd-abbr {
    font-weight: var(--weight-medium);
    text-transform: none;
    letter-spacing: normal;
    color: var(--dim-35);
    margin-left: 3px;
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
  .day-date .wd {
    font-weight: var(--weight-medium);
    text-transform: none;
    letter-spacing: normal;
    color: var(--dim-35);
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
  .sym-link {
    color: var(--text);
    text-decoration: none;
  }
  .sym-link:hover {
    color: var(--accent);
    text-decoration: underline;
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

  .status {
    display: inline-flex;
    align-items: baseline;
    gap: 4px;
    font-size: var(--text-2xs);
    font-weight: var(--weight-bold);
    letter-spacing: 0.03em;
    padding: 3px 8px;
    border-radius: var(--radius-pill);
    white-space: nowrap;
  }
  .status .q {
    font-weight: var(--weight-medium);
    opacity: 0.72;
  }
  .status.closed {
    color: var(--dim-45);
    border: 1px dashed var(--border);
    background: transparent;
  }
  .status.full {
    color: var(--accent);
    background: var(--accent-bg);
  }
  .status.partial {
    color: var(--amber);
    background: var(--amber-bg);
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
    text-align: right;
  }
  .fills {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    color: var(--accent);
    margin-left: 6px;
  }

  .gap-row td {
    padding: 4px 16px;
    border-bottom: none;
  }
  .gap-line {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .gap-rule {
    flex-grow: 1;
    height: 0;
    border-top: 1px dashed rgba(var(--amber-rgb), 0.35);
  }
  .gap-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
    padding: 4px 12px;
    border-radius: var(--radius-pill);
    background: var(--amber-bg);
    border: 1px dashed rgba(var(--amber-rgb), 0.4);
    font-size: var(--text-2xs);
    font-weight: var(--weight-bold);
    letter-spacing: 0.03em;
    color: var(--amber);
    white-space: nowrap;
  }
  .consecutive .gap-rule {
    border-top-color: var(--border);
  }
  .consecutive .gap-pill {
    background: var(--surface-alt);
    border-color: var(--border);
    color: var(--text-muted);
  }
  .consecutive .gap-dot {
    background: var(--text-muted);
  }
  .gap-dot {
    width: 5px;
    height: 5px;
    border-radius: var(--radius-pill);
    background: var(--amber);
  }

  .gap-hover {
    position: relative;
    flex-shrink: 0;
    display: inline-flex;
    background: none;
    border: none;
    padding: 0;
    margin: 0;
    font: inherit;
    cursor: help;
  }
  .gap-hover:focus-visible {
    outline: 2px solid var(--amber);
    outline-offset: 2px;
    border-radius: var(--radius-pill);
  }
  .gap-tip {
    position: absolute;
    bottom: 100%;
    left: 50%;
    margin-bottom: 10px;
    z-index: 5;
    width: max-content;
    max-width: 360px;
    padding: 12px 14px;
    background: var(--surface);
    border: 1px solid var(--border-08);
    border-radius: var(--radius-md);
    box-shadow: 0 10px 28px rgba(var(--ink-rgb), 0.16);
    opacity: 0;
    visibility: hidden;
    transform: translateX(-50%) translateY(-4px);
    transition:
      opacity 0.12s ease,
      transform 0.12s ease;
    pointer-events: none;
  }
  .gap-hover:hover .gap-tip,
  .gap-hover:focus-within .gap-tip {
    opacity: 1;
    visibility: visible;
    transform: translateX(-50%) translateY(0);
    pointer-events: auto;
  }
  .gap-tip-arrow {
    position: absolute;
    top: 100%;
    left: 50%;
    width: 10px;
    height: 10px;
    background: var(--surface);
    border-right: 1px solid var(--border-08);
    border-bottom: 1px solid var(--border-08);
    transform: translateX(-50%) translateY(-6px) rotate(45deg);
  }
  .gap-tip-title {
    display: block;
    font-size: var(--text-2xs);
    font-weight: var(--weight-bold);
    color: var(--text);
    margin-bottom: 8px;
    white-space: nowrap;
    text-align: left;
  }
  .gap-tip-days {
    display: flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
  }
  .day-chip {
    display: inline-block;
    width: 34px;
    flex-shrink: 0;
    text-align: center;
    padding: 4px 0;
    border-radius: var(--radius-sm);
    background: var(--amber-bg);
    border: 1px solid transparent;
  }
  .day-chip .day-abbr {
    display: block;
    font-size: 8px;
    font-weight: var(--weight-bold);
    letter-spacing: 0.02em;
    color: var(--amber);
  }
  .day-chip .day-num {
    display: block;
    font-size: 7px;
    font-weight: var(--weight-semibold);
    color: var(--dim-55);
    margin-top: 1px;
  }
  .day-chip.weekend {
    background: transparent;
    border: 1px dashed var(--border-12);
  }
  .day-chip.weekend .day-abbr {
    color: var(--dim-35);
    text-decoration: line-through;
  }
  .day-chip.weekend .day-num {
    color: var(--dim-35);
  }
  .gap-tip-foot {
    display: block;
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--border-05);
    font-size: 9px;
    color: var(--dim-45);
    white-space: nowrap;
  }

  .empty {
    color: var(--dim-55);
    text-align: center;
    padding: 40px 0;
    font-size: var(--text-sm);
  }
</style>
