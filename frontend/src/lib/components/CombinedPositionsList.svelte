<script lang="ts">
  /**
   * The "Combined" alternative to showing OpenPositionsList and
   * ClosedPositionsList as two stacked tables -- merges both row sets into
   * one table, entry date ascending, with Exit Date and Current Price
   * sharing a pair of columns (only one populated per row) and a single P&L
   * column standing in for Unrealized/Interim Realized/Realized P&L. Column
   * chrome (pill badges, pnl tone classes) matches the other two tables so
   * switching the Separate/Combined toggle doesn't jar.
   */
  import { positionDetailParams } from "$lib/api";
  import { fmtDateWeekday, fmtMoney, fmtPriceLike, toneOf, EM_DASH } from "$lib/format";
  import type { OpenPositionsRow } from "./OpenPositionsList.svelte";
  import type { ClosedPositionsRow } from "./ClosedPositionsList.svelte";

  interface CombinedRow {
    key: string;
    p: OpenPositionsRow["p"];
    statusLabel: string;
    statusClass: "full" | "partial" | "closed";
    daysHeld: number | null;
    entryPrice: number;
    qty: number;
    costBasis: number;
    exitDate: string | null;
    current: number | null;
    pnl: number | null;
    subLabel: string;
  }

  interface Props {
    openRows: OpenPositionsRow[];
    closedRows: ClosedPositionsRow[];
    currency?: string;
  }
  let { openRows, closedRows, currency = "USD" }: Props = $props();

  const rows = $derived.by((): CombinedRow[] => {
    const fromOpen: CombinedRow[] = openRows.map((r) => ({
      key: r.p.symbol + r.p.open_date + r.p.open_time,
      p: r.p,
      statusLabel: r.status === "full" ? "Open (Full)" : "Open (Partial)",
      statusClass: r.status,
      daysHeld: r.daysHeld,
      entryPrice: r.entryPrice,
      qty: r.qtyOpen,
      costBasis: r.costBasis,
      exitDate: null,
      current: r.current,
      pnl: r.unrealized,
      subLabel: r.status === "partial" && r.interim !== null ? `${fmtMoney(r.interim, currency)} so far` : "unrealized",
    }));
    const fromClosed: CombinedRow[] = closedRows.map((r) => ({
      key: r.p.symbol + r.p.open_date + r.p.open_time + "-closed",
      p: r.p,
      statusLabel: "Closed",
      statusClass: "closed",
      daysHeld: r.daysHeld,
      entryPrice: r.entryPrice,
      qty: r.qty,
      costBasis: r.costBasis,
      exitDate: r.p.exit_date,
      current: null,
      pnl: r.realized,
      subLabel: "realized",
    }));
    return [...fromOpen, ...fromClosed].sort(
      (a, b) => (a.p.open_date ?? "") + a.p.open_time < (b.p.open_date ?? "") + b.p.open_time ? -1 : 1,
    );
  });
  const openCount = $derived(rows.filter((r) => r.statusClass !== "closed").length);
  const closedCount = $derived(rows.length - openCount);
  const netPnl = $derived(rows.reduce((sum, r) => sum + (r.pnl ?? 0), 0));
</script>

<div class="panel">
  <div class="hd">
    <div class="eyebrow">Open + Closed &middot; combined</div>
    <div class="title">All positions</div>
    <div class="caption">Click a symbol to open its detail page in a new tab · entry date ascending by default</div>
  </div>
  <div class="scroll">
    <table>
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Status</th>
          <th>Side</th>
          <th>Entry Date</th>
          <th class="num">Days Held</th>
          <th class="num">Entry Price</th>
          <th class="num">Qty</th>
          <th class="num">Cost Basis</th>
          <th>Exit Date</th>
          <th class="num">Current</th>
          <th class="num">P&amp;L</th>
        </tr>
      </thead>
      <tbody>
        {#each rows as r (r.key)}
          <tr>
            <td class="sym">
              <a class="sym-link" href="/positions/detail?{positionDetailParams(r.p)}" target="_blank" rel="noopener">
                {r.p.symbol}
              </a>
              <span class="tag">{r.p.asset_category}</span>
            </td>
            <td><span class="status {r.statusClass}">{r.statusLabel}</span></td>
            <td><span class="dir {r.p.direction}">{r.p.direction.toUpperCase()}</span></td>
            <td class="full-date">{r.p.open_date ? fmtDateWeekday(r.p.open_date) : EM_DASH}</td>
            <td class="num dim">{r.daysHeld === null ? EM_DASH : `${r.daysHeld}d`}</td>
            <td class="num">{fmtPriceLike(r.entryPrice, currency, 2)}</td>
            <td class="num">{r.qty}</td>
            <td class="num">{fmtMoney(r.costBasis, currency)}</td>
            <td class="full-date">{r.exitDate ? fmtDateWeekday(r.exitDate) : EM_DASH}</td>
            <td class="num">{r.current === null ? EM_DASH : fmtPriceLike(r.current, currency, 2)}</td>
            <td class="num">
              {#if r.pnl === null}
                <span class="dash">{EM_DASH}</span>
              {:else}
                <span class="pnl {toneOf(r.pnl)}">{fmtMoney(r.pnl, currency)}</span>
                <span class="sublabel">{r.subLabel}</span>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
      <tfoot>
        <tr>
          <td colspan="10">Net P&amp;L across {rows.length} row{rows.length === 1 ? "" : "s"} ({openCount} open, {closedCount} closed)</td>
          <td class="num"><span class="pnl {toneOf(netPnl)}">{fmtMoney(netPnl, currency)}</span></td>
        </tr>
      </tfoot>
    </table>
  </div>
</div>

<style>
  .panel {
    background: var(--surface);
    border: 1px solid var(--border-05);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }
  .hd {
    padding: 11px 22px;
    border-bottom: 1px solid var(--border-05);
  }
  .eyebrow {
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--dim-55);
  }
  .title {
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    letter-spacing: -0.01em;
    color: var(--text);
    margin-top: 2px;
  }
  .caption {
    font-size: var(--text-2xs);
    color: var(--dim-45);
    margin-top: 2px;
  }

  .scroll {
    max-height: 460px;
    overflow: auto;
  }
  table {
    width: 100%;
    min-width: 1000px;
    border-collapse: collapse;
    font-feature-settings: "ss01", "cv11";
    font-variant-numeric: tabular-nums;
  }
  th {
    position: sticky;
    top: 0;
    z-index: 1;
    padding: 8px 16px;
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--dim-70);
    text-align: left;
    white-space: nowrap;
    background: var(--surface);
    border-bottom: 1px solid var(--border-05);
  }
  th.num {
    text-align: right;
  }
  /* Pin the narrow columns to a content-sized width -- Symbol and P&L (the
     widest natural content) absorb whatever's left. */
  th:nth-child(2),
  td:nth-child(2) {
    width: 130px;
  }
  th:nth-child(3),
  td:nth-child(3) {
    width: 74px;
  }
  th:nth-child(4),
  td:nth-child(4) {
    width: 100px;
  }
  th:nth-child(5),
  td:nth-child(5) {
    width: 80px;
  }
  th:nth-child(6),
  td:nth-child(6) {
    width: 100px;
  }
  th:nth-child(7),
  td:nth-child(7) {
    width: 70px;
  }
  th:nth-child(8),
  td:nth-child(8) {
    width: 110px;
  }
  th:nth-child(9),
  td:nth-child(9) {
    width: 100px;
  }
  th:nth-child(10),
  td:nth-child(10) {
    width: 110px;
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
  td.full-date {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    white-space: nowrap;
    color: var(--dim-70);
  }
  tbody tr:last-child td {
    border-bottom: none;
  }
  tbody tr:hover td {
    background: var(--surface-02);
  }
  tfoot td {
    position: sticky;
    bottom: 0;
    padding: 10px 16px;
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    color: var(--text);
    background: var(--surface);
    border-top: 1px solid var(--border-08);
  }
  tfoot td.num {
    text-align: right;
  }
  .sym-link {
    color: var(--text);
    font-weight: var(--weight-semibold);
    text-decoration: none;
  }
  .sym-link:hover {
    color: var(--accent);
    text-decoration: underline;
  }
  .tag {
    font-size: 9.5px;
    font-weight: var(--weight-semibold);
    color: var(--dim-45);
    background: var(--border-05);
    border-radius: 4px;
    padding: 1px 5px;
    margin-left: 6px;
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
  .status.full {
    color: var(--accent);
    background: var(--accent-bg);
  }
  .status.partial {
    color: var(--amber);
    background: var(--amber-bg);
  }
  .status.closed {
    color: var(--dim-55);
    background: var(--surface-04);
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
  .sublabel {
    display: block;
    font-size: 9px;
    font-weight: var(--weight-semibold);
    color: var(--dim-45);
  }
  .dash {
    color: var(--dim-35);
  }
</style>
