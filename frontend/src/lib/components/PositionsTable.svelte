<script lang="ts">
  /**
   * Round-trip positions, one row per position with its entry/exit legs
   * dropping down on click. See src/ibkr_pnl/positions.py for how trades
   * become these -- this component only renders what the backend already
   * reconstructed.
   */
  import { fmtDay, fmtMoney, fmtPriceLike, fmtQty, num, toneOf, EM_DASH } from "$lib/format";
  import type { Position, PositionLeg } from "$lib/api";

  interface Props {
    positions: Position[];
    currency?: string;
  }
  let { positions, currency = "USD" }: Props = $props();

  let expanded = $state<Set<number>>(new Set());
  function toggle(i: number) {
    const next = new Set(expanded);
    if (next.has(i)) next.delete(i);
    else next.add(i);
    expanded = next;
  }

  function legs(p: Position): PositionLeg[] {
    return p.exit_legs;
  }

  function fmtDateTime(iso: string | null, time: string): string {
    if (!iso) return EM_DASH;
    return time ? `${fmtDay(iso)}, ${time}` : fmtDay(iso);
  }
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
            <th>Side</th>
            <th>Date</th>
            <th>Time</th>
            <th class="num">Price</th>
            <th class="num">Qty</th>
            <th>Exit Date</th>
            <th class="num">Exits #</th>
            <th class="num">Pos %</th>
            <th class="num">Total P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {#each positions as p, i (p.symbol + (p.open_date ?? "") + p.open_time + (p.exit_date ?? "") + p.direction + i)}
            {@const canExpand = legs(p).length > 0}
            {@const isExpanded = expanded.has(i)}
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
              <td>
                <span class="dir {p.direction}">{p.direction.toUpperCase()}</span>
                {#if p.is_carry_in}
                  <span class="badge" title="Opened before the fetched date range -- entry date, price and true position size are unknown">
                    CARRY-IN
                  </span>
                {/if}
              </td>
              <td>{p.open_date ? fmtDay(p.open_date) : EM_DASH}</td>
              <td class="dim">{p.open_time || EM_DASH}</td>
              <td class="num">{p.entry_price !== null ? fmtPriceLike(num(p.entry_price), currency, 4) : EM_DASH}</td>
              <td class="num">{fmtQty(num(p.quantity))}</td>
              <td class={p.exit_date ? "" : "dash"}>{p.exit_date ? fmtDay(p.exit_date) : EM_DASH}</td>
              <td class="num">{p.exit_count || EM_DASH}</td>
              <td class="num dash">{EM_DASH}</td>
              <td class="num pnl {p.realized_pnl === null ? '' : toneOf(num(p.realized_pnl))}">
                {p.realized_pnl === null ? "open" : fmtMoney(num(p.realized_pnl), currency)}
              </td>
            </tr>

            {#if isExpanded}
              {#each legs(p) as leg, li (li)}
                <tr class="leg-row">
                  <td></td>
                  <td class="leg-label">Exit {li + 1}</td>
                  <td><span class="dir {leg.buy_sell.toUpperCase() === 'BUY' ? 'buy' : 'sell'}">{leg.buy_sell.toUpperCase()}</span></td>
                  <td>{fmtDay(leg.trade_date)}</td>
                  <td class="dim">{leg.trade_time || EM_DASH}</td>
                  <td class="num">
                    {leg.price !== null ? fmtPriceLike(num(leg.price), p.currency, 4) : EM_DASH}
                    {#if leg.fill_count > 1}<span class="fills">×{leg.fill_count}</span>{/if}
                  </td>
                  <td class="num">−{fmtQty(num(leg.quantity))}</td>
                  <td></td>
                  <td></td>
                  <td class="num">{leg.pct_of_position !== null ? `${num(leg.pct_of_position).toFixed(1)}%` : EM_DASH}</td>
                  <td class="num pnl {toneOf(num(leg.realized_pnl))}">{fmtMoney(num(leg.realized_pnl), p.currency)}</td>
                </tr>
              {/each}
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
  .dir.buy {
    background: var(--accent-bg);
    color: var(--accent);
  }
  .dir.sell {
    background: var(--dn-bg);
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
