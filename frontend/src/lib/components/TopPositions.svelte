<script lang="ts">
  /**
   * Best or worst closed trades by realized P&L, ranked list -- same row
   * language as PositionsTable (a symbol link straight to the position's
   * detail page), with a size-scaled tint behind each row so the ranking
   * still reads before you've checked the numbers themselves. One component
   * for both "Top wins" and "Top losses" since they're the same layout with
   * the sign of the comparison (and the color) flipped.
   */
  import type { Position } from "$lib/api";
  import { positionDetailParams } from "$lib/api";
  import { fmtMoney, fmtDayYear, num, EM_DASH } from "$lib/format";

  const N_OPTIONS = [5, 10, 20] as const;

  interface Props {
    positions: Position[];
    currency?: string;
    mode: "win" | "loss";
    /** Controlled from outside so wins and losses can share one Top N
     *  control instead of each keeping (and showing) its own. */
    topN: (typeof N_OPTIONS)[number];
    onTopNChange: (n: (typeof N_OPTIONS)[number]) => void;
    /** Only one of a wins/losses pair needs to render the control itself. */
    showControl?: boolean;
  }
  let { positions, currency = "USD", mode, topN, onTopNChange, showControl = true }: Props = $props();

  const rows = $derived(
    positions
      .filter((p) => !p.is_open && p.realized_pnl !== null && (mode === "win" ? num(p.realized_pnl) > 0 : num(p.realized_pnl) < 0))
      .sort((a, b) => (mode === "win" ? num(b.realized_pnl) - num(a.realized_pnl) : num(a.realized_pnl) - num(b.realized_pnl)))
      .slice(0, topN),
  );

  const maxAbsPnl = $derived(rows.length ? Math.abs(num(rows[0].realized_pnl)) : 1);

  function rankClass(rank: number): string {
    return rank === 1 ? "gold" : rank === 2 ? "silver" : rank === 3 ? "bronze" : "";
  }
</script>

<div class="panel">
  <div class="hd">
    <div class="hd-left">
      <div class="eyebrow">Positions overview</div>
      <div class="title">{mode === "win" ? "Top wins" : "Top losses"}</div>
      <div class="caption">
        {mode === "win" ? "Best" : "Worst"} closed trades by realized P&amp;L, in this view
      </div>
    </div>
    {#if showControl}
      <div class="seg">
        {#each N_OPTIONS as n, i (n)}
          <button class="seg-btn" class:first={i === 0} class:active={topN === n} onclick={() => onTopNChange(n)}>
            Top {n}
          </button>
        {/each}
      </div>
    {/if}
  </div>

  {#if rows.length === 0}
    <div class="empty">No {mode === "win" ? "winning" : "losing"} closed positions in this view.</div>
  {:else}
    <div class="body">
      {#each rows as p, i (p.symbol + (p.open_date ?? "") + p.open_time + (p.exit_date ?? ""))}
        {@const pnl = num(p.realized_pnl)}
        <a class="row" href="/positions/detail?{positionDetailParams(p)}">
          <div class="fill" class:up={mode === "win"} class:dn={mode === "loss"} style="width:{(Math.abs(pnl) / maxAbsPnl) * 100}%"></div>
          <div class="rank {rankClass(i + 1)}">{i + 1}</div>
          <div class="sym">{p.symbol}<span class="tag">{p.asset_category}</span></div>
          <div class="dates">
            {p.open_date ? fmtDayYear(p.open_date) : EM_DASH}
            <span class="arrow">→</span>
            {p.exit_date ? fmtDayYear(p.exit_date) : EM_DASH}
          </div>
          <div class="pnl" class:up={mode === "win"} class:dn={mode === "loss"}>{fmtMoney(pnl, currency)}</div>
        </a>
      {/each}
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
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    padding: 11px 22px;
    border-bottom: 1px solid var(--border-05);
    flex-wrap: wrap;
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
  }
  .title {
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    letter-spacing: -0.01em;
    color: var(--text);
  }
  .caption {
    font-size: var(--text-2xs);
    color: var(--dim-45);
    margin-top: 2px;
  }

  .seg {
    display: inline-flex;
    align-items: stretch;
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
    background: var(--surface);
    font-variant-numeric: tabular-nums;
    flex: none;
  }
  .seg-btn {
    padding: 7px 12px;
    border: none;
    border-left: 1px solid var(--border-05);
    background: transparent;
    color: var(--dim-70);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    letter-spacing: 0.04em;
    cursor: pointer;
    font-family: inherit;
    font-variant-numeric: inherit;
  }
  .seg-btn.first {
    border-left: none;
  }
  .seg-btn.active {
    background: var(--ink);
    color: var(--on-ink);
    font-weight: var(--weight-bold);
  }

  .body {
    padding: 6px 22px 10px;
  }
  .row {
    position: relative;
    display: flex;
    align-items: center;
    gap: 10px;
    height: 34px;
    padding: 0 4px;
    border-bottom: 1px solid var(--border-05);
    text-decoration: none;
    color: inherit;
    box-sizing: border-box;
  }
  .row:last-child {
    border-bottom: none;
  }
  .row:hover {
    background: var(--accent-bg);
  }
  .fill {
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    pointer-events: none;
  }
  .fill.up {
    background: rgba(34, 197, 94, 0.07);
  }
  .fill.dn {
    background: rgba(239, 68, 68, 0.07);
  }
  .rank {
    position: relative;
    width: 17px;
    height: 17px;
    border-radius: 50%;
    background: var(--border-05);
    color: var(--dim-55);
    font-size: 9px;
    font-weight: var(--weight-bold);
    display: flex;
    align-items: center;
    justify-content: center;
    flex: none;
  }
  .rank.gold {
    background: #d4a017;
    color: #fff;
  }
  .rank.silver {
    background: #9aa0a6;
    color: #fff;
  }
  .rank.bronze {
    background: #b5713d;
    color: #fff;
  }
  .sym {
    position: relative;
    flex: none;
    min-width: 0;
    font-size: var(--text-xs);
    font-weight: var(--weight-bold);
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .tag {
    font-size: 9px;
    font-weight: var(--weight-semibold);
    color: var(--dim-45);
    background: var(--border-05);
    border-radius: 4px;
    padding: 1px 5px;
    margin-left: 6px;
  }
  .dates {
    position: relative;
    flex: 1;
    min-width: 0;
    font-size: var(--text-2xs);
    color: var(--dim-45);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .dates .arrow {
    color: var(--dim-45);
    opacity: 0.5;
    margin: 0 2px;
  }
  .pnl {
    position: relative;
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    font-variant-numeric: tabular-nums;
    flex: none;
  }
  .pnl.up {
    color: var(--up);
  }
  .pnl.dn {
    color: var(--dn);
  }

  .empty {
    color: var(--dim-55);
    text-align: center;
    padding: 40px 0;
    font-size: var(--text-sm);
  }
</style>
