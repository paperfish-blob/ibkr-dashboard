<script lang="ts">
  /**
   * The open positions table itself -- see OpenPositionsRow in
   * positions/open/+page.svelte for how each row (qty still open, cost
   * basis, mark-to-market unrealized P&L) is derived from a Position. The
   * exposure-by-symbol bar panel that used to sit above this table now
   * lives in PositionExposurePanel.svelte, split out so the page can put
   * another panel (e.g. ClosedPositionsList) between the two.
   */
  import { positionDetailParams, type Position } from "$lib/api";
  import { fmtDateWeekday, fmtMoney, fmtPriceLike, num, toneOf, EM_DASH } from "$lib/format";

  export interface OpenPositionsRow {
    p: Position;
    status: "full" | "partial";
    qtyOpen: number;
    /** Size when first entered: qtyOpen plus every exit leg's quantity.
     *  null for a carry-in, whose original size is unknown. */
    qtyInitial: number | null;
    /** Share of qtyInitial already sold, 0-100; null alongside it. */
    pctSold: number | null;
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

  function fmtPct(n: number): string {
    return `${Number(n.toFixed(1))}%`;
  }

  // ---- Base Qty hover: a third of the original size, how many thirds
  // are already sold. position:fixed so the panel's and scroller's
  // overflow clipping can't cut it off on the last row. ----
  const TIP_W = 220;
  const TIP_H = 150;
  let tip: { row: OpenPositionsRow; left: number; top: number | null; bottom: number | null } | null = $state(null);

  function showTip(row: OpenPositionsRow, e: Event) {
    if (row.qtyInitial === null) return;
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const left = Math.max(8, Math.min(r.right - TIP_W, window.innerWidth - TIP_W - 8));
    const below = r.bottom + 4 + TIP_H <= window.innerHeight;
    tip = {
      row,
      left,
      top: below ? r.bottom + 4 : null,
      bottom: below ? null : window.innerHeight - r.top + 4,
    };
  }

  const fmt2 = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  function statusLabel(s: "full" | "partial"): string {
    return s === "full" ? "Open (Full)" : "Open (Partial)";
  }
</script>

<svelte:window onscroll={() => (tip = null)} />

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
          <th class="num">Cost Basis</th>
          <th class="num">Open Qty</th>
          <th class="num">Base Qty</th>
          <th class="num">% Sold</th>
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
            <td class="full-date">{r.p.open_date ? fmtDateWeekday(r.p.open_date) : EM_DASH}</td>
            <td class="num dim">{r.daysHeld === null ? EM_DASH : `${r.daysHeld}d`}</td>
            <td class="num">{fmtPriceLike(r.entryPrice, currency, 2)}</td>
            <td class="num">{fmtMoney(r.costBasis, currency)}</td>
            <td class="num">{r.qtyOpen}</td>
            <td
              class="num"
              class:dim={r.qtyInitial === null}
              class:hoverable={r.qtyInitial !== null}
              tabindex={r.qtyInitial === null ? undefined : 0}
              onmouseenter={(e) => showTip(r, e)}
              onmouseleave={() => (tip = null)}
              onfocus={(e) => showTip(r, e)}
              onblur={() => (tip = null)}
            >
              {#if r.qtyInitial === null}{EM_DASH}{:else}<span class="init-val">{r.qtyInitial}</span>{/if}
            </td>
            <td class="num sold" class:none={!r.pctSold}>
              <span class="sold-pct">{r.pctSold ? fmtPct(r.pctSold) : EM_DASH}</span>
              {#if r.pctSold !== null}
                <span class="sold-track"><span class="sold-fill" style="width:{r.pctSold}%"></span></span>
              {/if}
            </td>
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

{#if tip && tip.row.qtyInitial !== null}
  {@const initial = tip.row.qtyInitial}
  {@const third = initial / 3}
  {@const sold = Number((initial - tip.row.qtyOpen).toFixed(6))}
  {@const thirdsSold = sold / third}
  <div
    class="init-tip"
    role="tooltip"
    style="left:{tip.left}px;{tip.top !== null ? `top:${tip.top}px` : `bottom:${tip.bottom}px`};width:{TIP_W}px"
  >
    <div class="tip-h">One third of base qty</div>
    <div class="tip-big">{fmt2(third)}<small>of {initial}</small></div>
    <div class="tip-r"><span>Two thirds</span><span>{fmt2(third * 2)}</span></div>
    <div class="tip-r"><span>Sold so far</span><span>{sold} · {thirdsSold.toFixed(2)} thirds</span></div>
    <div class="tip-thirds">
      {#each [0, 1, 2] as i}
        <i><b style="width:{Math.max(0, Math.min(1, thirdsSold - i)) * 100}%"></b></i>
      {/each}
    </div>
  </div>
{/if}

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
  /* Columns 1-8 (Symbol through Open Qty) match ClosedPositionsList's
     same columns pixel-for-pixel so the two stacked tables line up -- Symbol
     has to be pinned too, not just left flexible, since each table has a
     different number of flexible trailing columns competing for the
     leftover space. */
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
    width: 110px;
  }
  th:nth-child(8),
  td:nth-child(8) {
    width: 70px;
  }
  th:nth-child(9),
  td:nth-child(9) {
    width: 90px;
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
  td.hoverable {
    cursor: help;
  }
  td.hoverable:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }
  .init-val {
    border-bottom: 1px dotted var(--dim-45);
    padding-bottom: 1px;
  }
  .init-tip {
    position: fixed;
    z-index: 20;
    pointer-events: none;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 10px 13px;
    font-size: var(--text-xs);
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.12);
  }
  .tip-h {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--dim-55);
    margin-bottom: 4px;
  }
  .tip-big {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.01em;
  }
  .tip-big small {
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    color: var(--dim-55);
    margin-left: 6px;
  }
  .tip-r {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px solid var(--border-05);
    font-variant-numeric: tabular-nums;
  }
  .tip-r span:first-child {
    color: var(--dim-55);
  }
  .tip-thirds {
    display: flex;
    gap: 3px;
    margin-top: 8px;
  }
  .tip-thirds i {
    flex: 1;
    height: 5px;
    border-radius: 2px;
    background: var(--track);
    position: relative;
    overflow: hidden;
  }
  .tip-thirds b {
    position: absolute;
    inset: 0 auto 0 0;
    background: var(--amber);
  }
  .sold-pct {
    display: block;
  }
  .sold.none .sold-pct {
    color: var(--dim-35);
  }
  .sold-track {
    display: block;
    height: 3px;
    margin-top: 4px;
    border-radius: 2px;
    background: var(--track);
    overflow: hidden;
  }
  .sold-fill {
    display: block;
    height: 100%;
    border-radius: 2px;
    background: var(--amber);
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
