<script lang="ts">
  /**
   * Where the numbers came from and how fresh they are.
   *
   * Modelled on ui-reference's CacheFreshness: an inverted --ink fill so the
   * badge reads as a state marker rather than another button.
   *
   * IB Gateway needs an interactive login each day and is therefore down most
   * of the time. That is the normal state, not an error, so its badge stays
   * visually quiet -- a plain outline, never amber.
   */
  import { fmtTime } from "$lib/format";
  import type { GatewayState, TodaySource } from "$lib/api";

  interface Props {
    gateway: GatewayState;
    flexOk: boolean;
    flexFetchedAt: string | null;
    tradeCount: number;
    todaySource?: TodaySource;
  }
  let { gateway, flexOk, flexFetchedAt, tradeCount, todaySource }: Props = $props();
</script>

<div class="badges">
  <span class="badge" class:warn={!flexOk} title="Historical data from the Flex Web Service">
    <span class="badge-label">Flex</span>
    {#if flexOk}
      <span class="badge-val">{fmtTime(flexFetchedAt)}</span>
      <span class="badge-age">{tradeCount.toLocaleString()} trades</span>
    {:else}
      <span class="badge-val">unavailable</span>
    {/if}
  </span>

  <span
    class="badge ghost"
    class:live={gateway.connected}
    title={gateway.connected
      ? `Live P&L for account ${gateway.account}`
      : "IB Gateway is not running — today's figure falls back to Flex"}
  >
    <span class="badge-label">Gateway</span>
    <span class="badge-val">{gateway.connected ? fmtTime(gateway.updated_at) : "disconnected"}</span>
  </span>

  {#if todaySource}
    <span class="badge ghost" title="Which source today's figure came from">
      <span class="badge-label">Today</span>
      <span class="badge-val">{todaySource}</span>
    </span>
  {/if}
</div>

<style>
  .badges {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .badge {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 7px 12px;
    border: 1px solid var(--ink);
    border-radius: var(--radius-md);
    background: var(--ink);
    color: var(--on-ink);
    font-family: var(--font-sans);
    font-size: var(--text-xs);
    line-height: 1;
    white-space: nowrap;
  }

  .badge-label {
    font-size: var(--text-2xs);
    font-weight: var(--weight-bold);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .badge-val {
    font-weight: var(--weight-semibold);
    font-variant-numeric: tabular-nums;
  }
  .badge-age {
    font-weight: var(--weight-medium);
    font-variant-numeric: tabular-nums;
    opacity: 0.7;
  }

  /* Secondary state: outline only. Gateway being down is unremarkable, so it
     must not compete with the Flex badge for attention. */
  .badge.ghost {
    background: var(--surface);
    border-color: var(--border-08);
    color: var(--dim-55);
  }
  .badge.ghost .badge-val {
    color: var(--dim-70);
  }
  .badge.ghost.live {
    border-color: var(--up);
    color: var(--up);
  }
  .badge.ghost.live .badge-val {
    color: var(--up);
  }

  /* A failed Flex fetch is a real problem -- this one does get the warning. */
  .badge.warn {
    border-color: var(--amber);
  }
  .badge.warn .badge-val {
    color: var(--over);
    font-weight: var(--weight-bold);
  }
</style>
