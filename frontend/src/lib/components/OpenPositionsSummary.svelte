<script lang="ts">
  /**
   * Headline panel for the Open Positions page -- unrealized P&L (mark-to-
   * market against each symbol's latest close) as the hero figure, same
   * grid shape as PositionHeadlineStat, with the Full/Partial/Carry-in
   * breakdown as the meta side.
   */
  import { fmtMoney, toneOf } from "$lib/format";

  interface Props {
    totalUnrealized: number;
    totalCost: number;
    openCount: number;
    fullCount: number;
    partialCount: number;
    carryInExcluded: number;
    currency?: string;
  }
  let { totalUnrealized, totalCost, openCount, fullCount, partialCount, carryInExcluded, currency = "USD" }: Props =
    $props();
</script>

<div class="panel">
  <div class="body">
    <div class="eyebrow">Unrealized P&amp;L (mark-to-market, latest close)</div>
    <div class="big {toneOf(totalUnrealized)}">{fmtMoney(totalUnrealized, currency)}</div>
    <div class="kicker">{openCount} position{openCount === 1 ? "" : "s"} currently open</div>
  </div>

  <div class="meta">
    <div class="meta-row hero">
      <span class="meta-label">Total Cost Basis</span>
      <span class="meta-val">{fmtMoney(totalCost, currency).replace("+", "")}</span>
    </div>
    <div class="meta-row">
      <span class="meta-label">Open (Full)</span>
      <span class="meta-val">{fullCount}</span>
    </div>
    <div class="meta-row">
      <span class="meta-label">Open (Partial)</span>
      <span class="meta-val">{partialCount}</span>
    </div>
    <div class="meta-row">
      <span class="meta-label">Carry-in (excluded)</span>
      <span class="meta-val">{carryInExcluded}</span>
    </div>
  </div>
</div>

<style>
  .panel {
    display: grid;
    grid-template-columns: 1fr 260px;
    background: var(--surface);
    border: 1px solid var(--border-05);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }
  .body {
    padding: 20px 24px;
  }
  .eyebrow {
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--dim-55);
  }
  .big {
    font-size: var(--text-5xl);
    font-weight: var(--weight-semibold);
    letter-spacing: -0.02em;
    margin-top: 4px;
  }
  .big.pos {
    color: var(--up);
  }
  .big.neg {
    color: var(--dn);
  }
  .big.flat {
    color: var(--text);
  }
  .kicker {
    font-size: var(--text-xs);
    color: var(--dim-55);
    margin-top: 8px;
  }

  .meta {
    border-left: 1px solid var(--border-05);
    padding: 20px 24px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    justify-content: center;
  }
  .meta-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    font-size: var(--text-xs);
  }
  .meta-row.hero {
    padding-bottom: 10px;
    margin-bottom: 2px;
    border-bottom: 1px solid var(--border-05);
  }
  .meta-label {
    color: var(--dim-45);
  }
  .meta-val {
    font-weight: var(--weight-semibold);
    color: var(--text);
    font-variant-numeric: tabular-nums;
  }
  .meta-row.hero .meta-val {
    font-size: var(--text-lg);
  }
</style>
