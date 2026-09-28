<script lang="ts">
  /** Headline card for the Open Positions page when "Include realized" is
   *  on -- the one number that answers "how did everything I've touched
   *  since {year} actually turn out," combining the open-positions panel's
   *  unrealized/partial figures with realized P&L folded in from closed
   *  positions. Sits above OpenPositionsSummary rather than replacing it,
   *  so the existing open-only breakdown stays intact underneath. */
  import { fmtMoney, toneOf } from "$lib/format";

  interface Props {
    total: number;
    unrealized: number;
    partial: number;
    realizedClosed: number;
    closedCount: number;
    currency?: string;
  }
  let { total, unrealized, partial, realizedClosed, closedCount, currency = "USD" }: Props = $props();
</script>

<div class="hero">
  <div class="hero-left">
    <div class="hero-eyebrow">Total P&amp;L, realized included</div>
    <div class="hero-big {toneOf(total)}">{fmtMoney(total, currency)}</div>
    <div class="hero-sub">Open positions marked to latest close, plus every closed position folded into the window</div>
  </div>
  <div class="hero-breakdown">
    <div class="hb-chip">
      <span class="hb-label">Unrealized</span>
      <span class="hb-val {toneOf(unrealized)}">{fmtMoney(unrealized, currency)}</span>
    </div>
    <span class="hb-plus">+</span>
    <div class="hb-chip">
      <span class="hb-label">Partial realized</span>
      <span class="hb-val {toneOf(partial)}">{fmtMoney(partial, currency)}</span>
    </div>
    <span class="hb-plus">+</span>
    <div class="hb-chip">
      <span class="hb-label">Closed positions</span>
      <span class="hb-val {toneOf(realizedClosed)}">{fmtMoney(realizedClosed, currency)} over {closedCount}</span>
    </div>
  </div>
</div>

<style>
  .hero {
    background: linear-gradient(180deg, var(--accent-bg), transparent 140%), var(--surface);
    border: 1px solid rgba(91, 108, 255, 0.28);
    border-radius: var(--radius-lg);
    padding: 22px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
    flex-wrap: wrap;
  }
  .hero-left {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .hero-eyebrow {
    font-size: var(--text-2xs);
    font-weight: var(--weight-bold);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--accent);
  }
  .hero-big {
    font-size: var(--text-4xl);
    font-weight: var(--weight-bold);
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
  }
  .hero-big.pos {
    color: var(--up);
  }
  .hero-big.neg {
    color: var(--dn);
  }
  .hero-big.flat {
    color: var(--text);
  }
  .hero-sub {
    font-size: var(--text-xs);
    color: var(--dim-55);
  }
  .hero-breakdown {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }
  .hb-chip {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 10px 14px;
    border-radius: var(--radius-md);
    background: var(--surface);
    border: 1px solid var(--border-05);
    min-width: 128px;
  }
  .hb-chip .hb-label {
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--dim-55);
  }
  .hb-chip .hb-val {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    font-variant-numeric: tabular-nums;
  }
  .hb-chip .hb-val.pos {
    color: var(--up);
  }
  .hb-chip .hb-val.neg {
    color: var(--dn);
  }
  .hb-chip .hb-val.flat {
    color: var(--text);
  }
  .hb-plus {
    align-self: center;
    color: var(--dim-35);
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  @media (max-width: 620px) {
    .hero {
      flex-direction: column;
      align-items: stretch;
    }
  }
</style>
