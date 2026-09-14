<script lang="ts">
  /** The total realized P&L, plus today's contribution and where it came from. */
  import { fmtMoney, num, toneOf } from "$lib/format";
  import type { PnLResponse } from "$lib/api";

  interface Props {
    data: PnLResponse;
  }
  let { data }: Props = $props();

  const headline = $derived(num(data.headline));
  const today = $derived(num(data.today));
  const tone = $derived(toneOf(headline));
  const todayTone = $derived(toneOf(today));
</script>

<div class="panel">
  <div class="body">
    <div class="eyebrow">Total realized</div>
    <div class="big {tone}">{fmtMoney(headline, data.currency)}</div>

    {#if data.today_source === "none"}
      <div class="kicker">No realized P&amp;L today</div>
    {:else}
      <div class="kicker">
        Today <span class={todayTone}>{fmtMoney(today, data.currency)}</span>
      </div>
    {/if}
  </div>

  <div class="meta">
    <div class="meta-row">
      <span class="meta-label">Account</span>
      <span class="meta-val">{data.account_id || "—"}</span>
    </div>
    <div class="meta-row">
      <span class="meta-label">Realizing trades</span>
      <span class="meta-val">{data.trade_count.toLocaleString()}</span>
    </div>
    <div class="meta-row">
      <span class="meta-label">Currency</span>
      <span class="meta-val">{data.currency}</span>
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
    padding: 20px 22px;
  }

  .eyebrow {
    font-size: var(--text-2xs);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--dim-55);
  }

  .big {
    font-size: var(--text-5xl);
    font-weight: var(--weight-semibold);
    letter-spacing: -0.02em;
    line-height: 1;
    margin: 6px 0 2px;
    font-variant-numeric: tabular-nums;
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
    font-size: var(--text-md);
    color: var(--dim-70);
    margin-top: 2px;
    font-variant-numeric: tabular-nums;
  }
  .kicker .pos {
    color: var(--up);
    font-weight: var(--weight-semibold);
  }
  .kicker .neg {
    color: var(--dn);
    font-weight: var(--weight-semibold);
  }
  .kicker .flat {
    color: var(--text);
    font-weight: var(--weight-semibold);
  }

  .meta {
    border-left: 1px solid var(--border-05);
    padding: 20px 18px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    justify-content: center;
  }
  .meta-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
  }
  .meta-label {
    font-size: var(--text-2xs);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--dim-55);
  }
  .meta-val {
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    color: var(--text);
    font-variant-numeric: tabular-nums;
  }

  @media (max-width: 900px) {
    .panel {
      grid-template-columns: 1fr;
    }
    .meta {
      border-left: none;
      border-top: 1px solid var(--border-05);
    }
  }
</style>
