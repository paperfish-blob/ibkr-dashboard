<script lang="ts">
  /**
   * Positions Overview's headline panel -- same shape as HeadlineStat, but
   * everything is derived client-side from the Positions feed rather than
   * read off a PnLResponse (positions have no gateway/today_source concept
   * of their own). The total and the closed-position count are the same
   * closed-position population regardless of groupBy -- only which day gets
   * credit for "today" changes with it.
   */
  import { fmtMoney, num, toneOf } from "$lib/format";
  import type { PositionsResponse } from "$lib/api";
  import type { PosGroupBy } from "$lib/stores";

  interface Props {
    data: PositionsResponse;
    groupBy: PosGroupBy;
    currency?: string;
  }
  let { data, groupBy, currency = "USD" }: Props = $props();

  const todayStr = new Date().toISOString().slice(0, 10);

  const closed = $derived(data.positions.filter((p) => !p.is_open));
  const total = $derived(closed.reduce((sum, p) => sum + num(p.realized_pnl), 0));
  const tone = $derived(toneOf(total));

  const todayClosed = $derived(closed.filter((p) => p.exit_date === todayStr));
  const todayClosedPnl = $derived(todayClosed.reduce((sum, p) => sum + num(p.realized_pnl), 0));
  const todayOpened = $derived(data.positions.filter((p) => p.open_date === todayStr));
</script>

<div class="panel">
  <div class="body">
    <div class="eyebrow">Total realized (closed positions)</div>
    <div class="big {tone}">{fmtMoney(total, currency)}</div>

    {#if groupBy === "exit"}
      {#if todayClosed.length === 0}
        <div class="kicker">No positions closed today</div>
      {:else}
        <div class="kicker">
          Today <span class={toneOf(todayClosedPnl)}>{fmtMoney(todayClosedPnl, currency)}</span>
          · {todayClosed.length} position{todayClosed.length === 1 ? "" : "s"} closed
        </div>
      {/if}
    {:else if todayOpened.length === 0}
      <div class="kicker">No positions opened today</div>
    {:else}
      <div class="kicker">
        {todayOpened.length} position{todayOpened.length === 1 ? "" : "s"} opened today
        <span class="dim">· not yet realized</span>
      </div>
    {/if}
  </div>

  <div class="meta">
    <div class="meta-row">
      <span class="meta-label">Account</span>
      <span class="meta-val">{data.account_id || "—"}</span>
    </div>
    <div class="meta-row">
      <span class="meta-label">Closed positions</span>
      <span class="meta-val">{closed.length.toLocaleString()}</span>
    </div>
    <div class="meta-row">
      <span class="meta-label">Currency</span>
      <span class="meta-val">{currency}</span>
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
  .kicker .dim {
    color: var(--dim-45);
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
