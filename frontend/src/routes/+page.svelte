<script lang="ts">
  import { onMount } from "svelte";
  import PageHeader from "$lib/components/PageHeader.svelte";
  import HeadlineStat from "$lib/components/HeadlineStat.svelte";
  import CumulativeChart from "$lib/components/CumulativeChart.svelte";
  import StatusBadges from "$lib/components/StatusBadges.svelte";
  import SkeletonCard from "$lib/components/SkeletonCard.svelte";
  import AlertBar from "$lib/components/AlertBar.svelte";
  import PeriodPicker from "$lib/components/PeriodPicker.svelte";
  import { pnl, pnlLoading, pnlError, refreshPnL } from "$lib/stores";

  const POLL_MS = 30_000;
  let refreshing = $state(false);

  // "All" merges only the years already downloaded, so it has to say which.
  const coverage = $derived.by(() => {
    const years = $pnl?.years_covered ?? [];
    if ($pnl?.period !== "all" || years.length <= 1) return null;
    return `Covering ${years.slice().sort().join(", ")} — add more on the History page.`;
  });

  async function handleRefresh() {
    refreshing = true;
    try {
      await refreshPnL();
    } finally {
      refreshing = false;
    }
  }

  onMount(() => {
    refreshPnL();
    const id = setInterval(() => refreshPnL(), POLL_MS);
    return () => clearInterval(id);
  });
</script>

<svelte:head><title>Overview · IBKR Realized P&L</title></svelte:head>

<div class="page">
  <PageHeader
    eyebrow="Account performance · Realized P&L"
    title="Overview"
    sticky
    onRefresh={handleRefresh}
    {refreshing}
  >
    {#snippet right()}
      <PeriodPicker />
      {#if $pnl}
        <StatusBadges
          gateway={$pnl.gateway}
          flexOk={$pnl.flex_ok}
          flexFetchedAt={$pnl.flex_fetched_at}
          tradeCount={$pnl.trade_count}
          todaySource={$pnl.today_source}
        />
      {/if}
    {/snippet}
  </PageHeader>

  <AlertBar messages={[$pnlError, $pnl?.flex_error, $pnl?.currency_warning]} />

  {#if coverage}
    <div class="coverage">{coverage}</div>
  {/if}

  {#if $pnlLoading && !$pnl}
    <SkeletonCard height={168} rows={2} />
    <div class="gap"></div>
    <SkeletonCard height={360} rows={4} />
  {:else if $pnl}
    <HeadlineStat data={$pnl} />
    <div class="gap"></div>
    <CumulativeChart series={$pnl.series} currency={$pnl.currency} />
  {:else}
    <div class="panel-empty">
      Could not load P&amp;L. Check that the backend is running on port 9001.
    </div>
  {/if}
</div>

<style>
  .page {
    padding: var(--page-py) var(--page-px);
    width: 100%;
  }
  .gap {
    height: 24px;
  }
  .coverage {
    font-size: var(--text-xs);
    color: var(--dim-55);
    margin-bottom: 12px;
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
