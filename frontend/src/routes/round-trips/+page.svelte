<script lang="ts">
  import { onMount } from "svelte";
  import PageHeader from "$lib/components/PageHeader.svelte";
  import RoundTripLedger from "$lib/components/RoundTripLedger.svelte";
  import SkeletonCard from "$lib/components/SkeletonCard.svelte";
  import AlertBar from "$lib/components/AlertBar.svelte";
  import PeriodPicker from "$lib/components/PeriodPicker.svelte";
  import { fmtDay, fmtMoney, num, toneOf } from "$lib/format";
  import { roundTrips, roundTripsLoading, roundTripsError, refreshRoundTrips } from "$lib/stores";

  const POLL_MS = 30_000;
  let refreshing = $state(false);

  // Every round trip shares the account's currency in practice; a genuinely
  // multi-currency statement isn't specially flagged here the way Overview's
  // currency_warning does -- match the same graceful fallback Transactions
  // uses rather than inventing a second warning path for one more page.
  const currency = $derived($roundTrips?.round_trips[0]?.currency ?? "USD");
  const total = $derived(num($roundTrips?.total_realized ?? 0));

  async function handleRefresh() {
    refreshing = true;
    try {
      await refreshRoundTrips();
    } finally {
      refreshing = false;
    }
  }

  onMount(() => {
    refreshRoundTrips();
    const id = setInterval(() => refreshRoundTrips(), POLL_MS);
    return () => clearInterval(id);
  });
</script>

<svelte:head><title>Round Trips · IBKR Realized P&L</title></svelte:head>

<div class="page">
  <PageHeader
    eyebrow="FIFO-matched · Flex statement"
    title="Round Trips"
    sticky
    onRefresh={handleRefresh}
    {refreshing}
  >
    {#snippet right()}
      {#if $roundTrips}
        <span class="range">
          {#if $roundTrips.from_date && $roundTrips.to_date}
            {fmtDay($roundTrips.from_date)} – {fmtDay($roundTrips.to_date)}
          {/if}
        </span>
        <span class="total {toneOf(total)}">{fmtMoney(total, currency)}</span>
      {/if}
      <PeriodPicker />
    {/snippet}
  </PageHeader>

  <AlertBar messages={[$roundTripsError, $roundTrips?.flex_error]} />

  <div class="intro">
    Each row is one executed open matched against one executed close, FIFO --
    the same way IBKR's own realized P&amp;L is computed. A position that
    partially closes and later re-opens before closing out completely can
    span more than one row; see Transactions for the raw execution-by-
    execution list this is built from.
  </div>

  {#if $roundTripsLoading && !$roundTrips}
    <SkeletonCard height={480} rows={8} />
  {:else if $roundTrips}
    <RoundTripLedger roundTrips={$roundTrips.round_trips} {currency} />
  {:else}
    <div class="panel-empty">
      Could not load round trips. Check that the backend is running on port 9001.
    </div>
  {/if}
</div>

<style>
  .page {
    padding: var(--page-py) var(--page-px);
    width: 100%;
  }
  .range {
    font-size: var(--text-xs);
    color: var(--dim-55);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .total {
    font-size: var(--text-2lg);
    font-weight: var(--weight-semibold);
    letter-spacing: -0.01em;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .total.pos {
    color: var(--up);
  }
  .total.neg {
    color: var(--dn);
  }
  .total.flat {
    color: var(--text);
  }
  .intro {
    max-width: 760px;
    margin: 0 0 16px;
    font-size: var(--text-sm);
    line-height: 1.5;
    color: var(--dim-70);
  }
  .panel-empty {
    padding: 40px 18px;
    text-align: center;
    border: 1px solid var(--border-05);
    border-radius: var(--radius-lg);
    background: var(--surface);
    color: var(--dim-55);
    font-size: var(--text-sm);
  }
</style>
