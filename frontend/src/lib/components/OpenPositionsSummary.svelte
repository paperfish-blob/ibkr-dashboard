<script lang="ts">
  /**
   * Headline panel for the Open Positions page -- four equal-weight stat
   * tiles (Unrealized P&L, Partial Realised P&L, Total Cost Basis, Total
   * Open) rather than one hero number with the rest demoted to a small
   * side panel, so Cost Basis and the open count get the same visual
   * attention as P&L does. A fifth Total Closed tile joins them when
   * "Include realized" has actual closed rows to report -- same shape as
   * Total Open (a count leads, with the $ figure demoted to a chip below)
   * since "how many positions closed" is the headline question there, same
   * as "how many are open" is for its neighbor.
   */
  import { fmtDayYear, fmtMoney, toneOf } from "$lib/format";

  interface Props {
    totalUnrealized: number;
    totalPartialRealized: number;
    totalCost: number;
    openCount: number;
    fullCount: number;
    partialCount: number;
    carryInExcluded: number;
    closedCount?: number;
    realizedClosedTotal?: number;
    closedSinceDate?: string | null;
    currency?: string;
  }
  let {
    totalUnrealized,
    totalPartialRealized,
    totalCost,
    openCount,
    fullCount,
    partialCount,
    carryInExcluded,
    closedCount = 0,
    realizedClosedTotal = 0,
    closedSinceDate = null,
    currency = "USD",
  }: Props = $props();

  const showClosed = $derived(closedCount > 0);
</script>

<div class="panel" class:five={showClosed}>
  <div class="tile">
    <div class="eyebrow">Unrealized P&amp;L</div>
    <div class="big {toneOf(totalUnrealized)}">{fmtMoney(totalUnrealized, currency)}</div>
    <div class="kicker">Mark-to-market, latest close</div>
  </div>

  <div class="tile">
    <div class="eyebrow">Partial Realised P&amp;L</div>
    <div class="big {toneOf(totalPartialRealized)}">{fmtMoney(totalPartialRealized, currency)}</div>
    <div class="kicker">
      {#if partialCount > 0}
        Locked in on exits already taken &middot; {partialCount} partial position{partialCount === 1 ? "" : "s"}
      {:else}
        No partial exits yet
      {/if}
    </div>
  </div>

  <div class="tile">
    <div class="eyebrow">Total Cost Basis</div>
    <div class="big ink">{fmtMoney(totalCost, currency).replace("+", "")}</div>
    <div class="kicker">Across every open position</div>
  </div>

  <div class="tile">
    <div class="eyebrow">Total Open</div>
    <div class="open-line">
      <span class="open-num">{openCount}</span>
      <span class="open-unit">open</span>
    </div>
    <div class="breakdown">
      <span class="chip full">{fullCount} Full</span>
      <span class="chip partial">{partialCount} Partial</span>
    </div>
    <div class="foot">{carryInExcluded} carry-in excluded</div>
  </div>

  {#if showClosed}
    <div class="tile">
      <div class="eyebrow">Total Closed</div>
      <div class="open-line">
        <span class="open-num">{closedCount}</span>
        <span class="open-unit">closed</span>
      </div>
      <div class="breakdown">
        <span class="chip {toneOf(realizedClosedTotal)}">{fmtMoney(realizedClosedTotal, currency)} realized</span>
      </div>
      {#if closedSinceDate}
        <div class="foot">Opened on/after {fmtDayYear(closedSinceDate)}</div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .panel {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    background: var(--surface);
    border: 1px solid var(--border-05);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }
  .panel.five {
    grid-template-columns: repeat(5, 1fr);
  }
  .tile {
    padding: 20px 24px;
    border-left: 1px solid var(--border-05);
  }
  .tile:first-child {
    border-left: none;
  }
  .eyebrow {
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--dim-55);
  }
  .big {
    font-size: var(--text-3xl);
    font-weight: var(--weight-bold);
    letter-spacing: -0.02em;
    margin-top: 4px;
    font-variant-numeric: tabular-nums;
  }
  .big.pos {
    color: var(--up);
  }
  .big.neg {
    color: var(--dn);
  }
  .big.flat,
  .big.ink {
    color: var(--text);
  }
  .kicker {
    font-size: var(--text-xs);
    color: var(--dim-55);
    margin-top: 8px;
  }
  .open-line {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin-top: 4px;
  }
  .open-num {
    font-size: var(--text-4xl);
    font-weight: var(--weight-bold);
    letter-spacing: -0.03em;
    line-height: 1;
    color: var(--text);
    font-variant-numeric: tabular-nums;
  }
  .open-unit {
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    color: var(--text);
  }
  .breakdown {
    display: flex;
    gap: 8px;
    margin-top: 8px;
  }
  .chip {
    font-size: var(--text-2xs);
    font-weight: var(--weight-bold);
    padding: 3px 9px;
    border-radius: var(--radius-pill);
  }
  .chip.full {
    color: var(--accent);
    background: var(--accent-bg);
  }
  .chip.partial {
    color: var(--amber);
    background: var(--amber-bg);
  }
  .chip.pos {
    color: var(--up);
    background: var(--up-bg);
  }
  .chip.neg {
    color: var(--dn);
    background: var(--dn-bg);
  }
  .chip.flat {
    color: var(--text);
    background: var(--surface-04);
  }
  .foot {
    font-size: var(--text-2xs);
    color: var(--dim-45);
    margin-top: 8px;
  }
</style>
