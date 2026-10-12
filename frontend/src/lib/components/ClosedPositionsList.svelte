<script lang="ts">
  /**
   * The realized-since-window table shown under Open Positions when
   * "Include realized" is on -- every fully closed, non-carry-in position
   * whose own entry date falls on or after the window's boundary (see
   * boundaryDate in +page.svelte). Mirrors OpenPositionsList's table
   * conventions (same column chrome, pill badges, pnl tone classes) so the
   * two tables read as one system stacked on the same page.
   */
  import { positionDetailParams, type Position } from "$lib/api";
  import { fmtDateWeekday, fmtMoney, fmtPriceLike, toneOf, EM_DASH } from "$lib/format";

  export interface ClosedPositionsRow {
    p: Position;
    realized: number;
    daysHeld: number | null;
    entryPrice: number;
    qty: number;
    costBasis: number;
  }

  interface Props {
    rows: ClosedPositionsRow[];
    currency?: string;
  }
  let { rows, currency = "USD" }: Props = $props();

  const byEntryAsc = $derived(
    [...rows].sort((a, b) => (a.p.open_date ?? "").localeCompare(b.p.open_date ?? "")),
  );
  const total = $derived(rows.reduce((sum, r) => sum + r.realized, 0));
</script>

<div class="panel">
  <div class="hd">
    <div class="eyebrow">Realized, folded into the window</div>
    <div class="title">Closed positions</div>
    <div class="caption">Click a symbol to open its detail page in a new tab · earliest entry date first</div>
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
          <th class="num">Realized P&amp;L</th>
        </tr>
      </thead>
      <tbody>
        {#each byEntryAsc as r (r.p.symbol + r.p.open_date + r.p.open_time)}
          <tr>
            <td class="sym">
              <a class="sym-link" href="/positions/detail?{positionDetailParams(r.p)}" target="_blank" rel="noopener">
                {r.p.symbol}
              </a>
              <span class="tag">{r.p.asset_category}</span>
            </td>
            <td><span class="status closed">Closed</span></td>
            <td><span class="dir {r.p.direction}">{r.p.direction.toUpperCase()}</span></td>
            <td class="full-date">{r.p.open_date ? fmtDateWeekday(r.p.open_date) : EM_DASH}</td>
            <td class="num dim">{r.daysHeld === null ? EM_DASH : `${r.daysHeld}d`}</td>
            <td class="num">{fmtPriceLike(r.entryPrice, currency, 2)}</td>
            <td class="num">{r.qty}</td>
            <td class="num">{fmtMoney(r.costBasis, currency)}</td>
            <td class="full-date">{r.p.exit_date ? fmtDateWeekday(r.p.exit_date) : EM_DASH}</td>
            <td class="num"><span class="pnl {toneOf(r.realized)}">{fmtMoney(r.realized, currency)}</span></td>
          </tr>
        {/each}
      </tbody>
      <tfoot>
        <tr>
          <td colspan="9">Total realized in window</td>
          <td class="num"><span class="pnl {toneOf(total)}">{fmtMoney(total, currency)}</span></td>
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
    min-width: 900px;
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
  /* Pin the narrow date/day/price columns to a content-sized width so the
     auto table layout doesn't hand their leftover space to a short column,
     drifting it away from its neighbors -- Realized P&L (the widest
     remaining content) absorbs whatever's left instead. Columns 1-8
     (Symbol through Cost Basis) share their widths with OpenPositionsList's
     same columns so the two stacked tables line up -- Symbol has to be
     pinned too, not just left flexible, since each table has a different
     number of flexible trailing columns competing for the leftover space. */
  th:nth-child(1),
  td:nth-child(1) {
    width: 220px;
  }
  th:nth-child(2),
  td:nth-child(2) {
    width: 132px;
  }
  th:nth-child(3),
  td:nth-child(3) {
    width: 76px;
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
  .status {
    display: inline-block;
    font-size: var(--text-2xs);
    font-weight: var(--weight-bold);
    letter-spacing: 0.03em;
    padding: 3px 8px;
    border-radius: var(--radius-pill);
    white-space: nowrap;
  }
  .status.closed {
    color: var(--dim-55);
    background: var(--surface-04);
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
</style>
