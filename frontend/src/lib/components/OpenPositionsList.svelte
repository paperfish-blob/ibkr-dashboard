<script lang="ts">
  /**
   * Exposure-by-symbol bar panel + the open positions table itself, both
   * driven by the same precomputed rows -- see OpenPositionsRow in
   * positions/open/+page.svelte for how each row (qty still open, cost
   * basis, mark-to-market unrealized P&L) is derived from a Position.
   */
  import { positionDetailParams, type Position } from "$lib/api";
  import { fmtDayYear, fmtMoney, fmtPriceLike, num, toneOf, EM_DASH } from "$lib/format";

  export interface OpenPositionsRow {
    p: Position;
    status: "full" | "partial";
    qtyOpen: number;
    entryPrice: number;
    costBasis: number;
    current: number | null;
    unrealized: number | null;
    interim: number | null;
    daysHeld: number | null;
  }

  interface Props {
    rows: OpenPositionsRow[];
    currency?: string;
  }
  let { rows, currency = "USD" }: Props = $props();

  const byCostDesc = $derived([...rows].sort((a, b) => b.costBasis - a.costBasis));
  const maxCost = $derived(Math.max(1, ...rows.map((r) => r.costBasis)));

  function statusLabel(s: "full" | "partial"): string {
    return s === "full" ? "Open (Full)" : "Open (Partial)";
  }
</script>

<div class="panel">
  <div class="hd">
    <div class="eyebrow">Open positions</div>
    <div class="title">Exposure by symbol</div>
    <div class="caption">Cost basis on the remaining open quantity, sorted largest first</div>
  </div>
  <div class="exp-body">
    {#each byCostDesc as r (r.p.symbol + r.p.open_date + r.p.open_time)}
      <div class="exp-row">
        <div class="exp-label">{r.p.symbol}</div>
        <div class="exp-track"><div class="exp-fill" style="width:{(r.costBasis / maxCost) * 100}%"></div></div>
        <div class="exp-val">{fmtMoney(r.costBasis, currency)}</div>
      </div>
    {/each}
  </div>
</div>

<div class="gap"></div>

<div class="panel">
  <div class="hd">
    <div class="eyebrow">Open positions</div>
    <div class="title">Positions</div>
    <div class="caption">Click a symbol to open its detail page in a new tab · Interim Realized only applies to Partial rows, and isn't final</div>
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
          <th class="num">Qty Open</th>
          <th class="num">Cost Basis</th>
          <th class="num">Current Price</th>
          <th class="num">Unrealized P&amp;L</th>
          <th class="num">Interim Realized</th>
        </tr>
      </thead>
      <tbody>
        {#each rows as r (r.p.symbol + r.p.open_date + r.p.open_time)}
          <tr>
            <td class="sym">
              <a class="sym-link" href="/positions/detail?{positionDetailParams(r.p)}" target="_blank" rel="noopener">
                {r.p.symbol}
              </a>
              <span class="tag">{r.p.asset_category}</span>
            </td>
            <td><span class="status {r.status}">{statusLabel(r.status)}</span></td>
            <td><span class="dir {r.p.direction}">{r.p.direction.toUpperCase()}</span></td>
            <td class="full-date">{r.p.open_date ? fmtDayYear(r.p.open_date) : EM_DASH}</td>
            <td class="num dim">{r.daysHeld === null ? EM_DASH : `${r.daysHeld}d`}</td>
            <td class="num">{fmtPriceLike(r.entryPrice, currency, 2)}</td>
            <td class="num">{r.qtyOpen}</td>
            <td class="num">{fmtMoney(r.costBasis, currency)}</td>
            <td class="num">{r.current === null ? EM_DASH : fmtPriceLike(r.current, currency, 2)}</td>
            <td class="num">
              {#if r.unrealized === null}
                <span class="dash">{EM_DASH}</span>
              {:else}
                <span class="pnl {toneOf(r.unrealized)}">{fmtMoney(r.unrealized, currency)}</span>
              {/if}
            </td>
            <td class="num">
              {#if r.interim === null}
                <span class="dash">{EM_DASH}</span>
              {:else}
                <span class="pnl {toneOf(r.interim)}">{fmtMoney(r.interim, currency)}</span>
                <span class="sofar">so far</span>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
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
  .gap {
    height: 16px;
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

  .exp-body {
    padding: 14px 22px 18px;
  }
  .exp-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 0;
  }
  .exp-label {
    width: 64px;
    font-size: var(--text-xs);
    font-weight: var(--weight-bold);
    color: var(--text);
    flex: none;
  }
  .exp-track {
    flex: 1;
    height: 10px;
    background: var(--border-05);
    border-radius: 4px;
    overflow: hidden;
  }
  .exp-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 4px;
  }
  .exp-val {
    width: 90px;
    text-align: right;
    font-size: var(--text-xs);
    font-weight: var(--weight-semibold);
    color: var(--dim-70);
    flex: none;
    font-variant-numeric: tabular-nums;
  }

  .scroll {
    overflow-x: auto;
  }
  table {
    width: 100%;
    min-width: 900px;
    border-collapse: collapse;
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
  }
  th.num {
    text-align: right;
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
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--dim-70);
  }
  tbody tr:last-child td {
    border-bottom: none;
  }
  tbody tr:hover td {
    background: var(--surface-02);
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
  .sofar {
    display: block;
    font-size: 9px;
    font-weight: var(--weight-semibold);
    color: var(--dim-45);
  }
  .dash {
    color: var(--dim-35);
  }
</style>
