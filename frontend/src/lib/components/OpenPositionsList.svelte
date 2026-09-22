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
  const totalCost = $derived(rows.reduce((sum, r) => sum + r.costBasis, 0));

  function rowKey(r: OpenPositionsRow): string {
    return r.p.symbol + r.p.open_date + r.p.open_time;
  }

  // Same rotating palette PotentialPnlPanel uses for its Normalized view, so
  // a symbol's color means the same thing wherever it shows up on this page.
  // Assigned once per row (by cost-basis rank) so the stacked composition
  // bar, its legend, and the per-row bars below all agree on which color is
  // which symbol.
  const PALETTE = ["var(--accent)", "var(--ai)", "var(--amber)", "var(--up)", "var(--dn)"];
  const exposureRows = $derived(
    byCostDesc.map((r, i) => ({
      r,
      key: rowKey(r),
      color: PALETTE[i % PALETTE.length],
      pct: totalCost > 0 ? (r.costBasis / totalCost) * 100 : 0,
      tooltip: `${r.p.symbol} · ${fmtMoney(r.costBasis, currency)} · ${(totalCost > 0 ? (r.costBasis / totalCost) * 100 : 0).toFixed(1)}%`,
    })),
  );

  // Hovering any one of a segment / legend chip / row bar highlights that
  // same symbol in all three places at once and dims the rest -- tracked by
  // the same composite key the rows are already keyed by, not bare symbol,
  // so two different positions that happen to share a symbol never cross-
  // highlight each other.
  let hoveredKey = $state<string | null>(null);

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
  <div class="stack-wrap">
    <div class="stack">
      {#each exposureRows as er (er.key)}
        <div
          class="seg"
          class:dim={hoveredKey !== null && hoveredKey !== er.key}
          style="width:{er.pct}%;background:{er.color}"
          title={er.tooltip}
          onmouseenter={() => (hoveredKey = er.key)}
          onmouseleave={() => (hoveredKey = null)}
        ></div>
      {/each}
    </div>
    <div class="legend">
      {#each exposureRows as er (er.key)}
        <div
          class="legend-item"
          class:dim={hoveredKey !== null && hoveredKey !== er.key}
          class:active={hoveredKey === er.key}
          onmouseenter={() => (hoveredKey = er.key)}
          onmouseleave={() => (hoveredKey = null)}
        >
          <span class="dot" style="background:{er.color}"></span>
          <span class="legend-sym">{er.r.p.symbol}</span>
          <span class="legend-pct">{er.pct.toFixed(1)}%</span>
        </div>
      {/each}
    </div>
  </div>
  <div class="exp-body">
    {#each exposureRows as er (er.key)}
      <div
        class="exp-row"
        class:dim={hoveredKey !== null && hoveredKey !== er.key}
        class:active={hoveredKey === er.key}
        onmouseenter={() => (hoveredKey = er.key)}
        onmouseleave={() => (hoveredKey = null)}
      >
        <div class="exp-label">{er.r.p.symbol}</div>
        <div class="exp-track"><div class="exp-fill" style="width:{er.pct}%;background:{er.color}"></div></div>
        <div class="exp-vals">
          <span class="exp-val">{fmtMoney(er.r.costBasis, currency)}</span>
          <span class="exp-pct">{er.pct.toFixed(1)}%</span>
        </div>
      </div>
    {/each}
    <div class="exp-row exp-total">
      <div class="exp-label">Total</div>
      <div class="exp-track" style="visibility:hidden"></div>
      <div class="exp-vals">
        <span class="exp-val">{fmtMoney(totalCost, currency)}</span>
        <span class="exp-pct">100%</span>
      </div>
    </div>
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

  .stack-wrap {
    padding: 16px 22px 14px;
    border-bottom: 1px solid var(--border-05);
  }
  .stack {
    display: flex;
    height: 14px;
    border-radius: 6px;
    overflow: hidden;
    background: var(--border-05);
  }
  .seg {
    height: 100%;
    cursor: pointer;
    opacity: 1;
    transition: opacity 0.12s ease;
  }
  .seg.dim {
    opacity: 0.28;
  }
  .legend {
    display: flex;
    gap: 18px;
    flex-wrap: wrap;
    margin-top: 10px;
    font-size: var(--text-2xs);
  }
  .legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    padding: 2px 4px;
    border-radius: 4px;
    opacity: 1;
    transition:
      opacity 0.12s ease,
      background 0.12s ease;
  }
  .legend-item.dim {
    opacity: 0.35;
  }
  .legend-item.active {
    background: var(--surface-02);
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 2px;
    flex: none;
  }
  .legend-sym {
    font-weight: var(--weight-bold);
    color: var(--text);
  }
  .legend-pct {
    color: var(--dim-45);
  }

  .exp-body {
    padding: 14px 22px 6px;
  }
  .exp-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 4px;
    border-radius: 6px;
    cursor: pointer;
    opacity: 1;
    transition:
      opacity 0.12s ease,
      background 0.12s ease;
  }
  .exp-row.dim {
    opacity: 0.35;
  }
  .exp-row.active {
    background: var(--surface-02);
  }
  .exp-row.active .exp-fill {
    filter: brightness(1.12);
  }
  .exp-row.exp-total {
    cursor: default;
  }
  .exp-row.exp-total {
    margin-top: 4px;
    padding-top: 12px;
    padding-bottom: 12px;
    border-top: 1px solid var(--border-05);
  }
  .exp-total .exp-label {
    color: var(--dim-55);
    font-weight: var(--weight-semibold);
  }
  .exp-total .exp-val {
    color: var(--text);
    font-weight: var(--weight-bold);
  }
  .exp-total .exp-pct {
    color: var(--dim-55);
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
    border-radius: 4px;
  }
  .exp-vals {
    width: 150px;
    display: flex;
    justify-content: flex-end;
    align-items: baseline;
    gap: 8px;
    flex: none;
  }
  .exp-val {
    text-align: right;
    font-size: var(--text-xs);
    font-weight: var(--weight-semibold);
    color: var(--dim-70);
    font-variant-numeric: tabular-nums;
  }
  .exp-pct {
    width: 38px;
    text-align: right;
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    color: var(--dim-45);
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
