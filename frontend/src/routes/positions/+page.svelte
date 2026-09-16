<script lang="ts">
  import { onMount } from "svelte";
  import PageHeader from "$lib/components/PageHeader.svelte";
  import SegToggle from "$lib/components/SegToggle.svelte";
  import SymbolFilter from "$lib/components/SymbolFilter.svelte";
  import PositionsTable from "$lib/components/PositionsTable.svelte";
  import SkeletonCard from "$lib/components/SkeletonCard.svelte";
  import AlertBar from "$lib/components/AlertBar.svelte";
  import PeriodPicker from "$lib/components/PeriodPicker.svelte";
  import { fmtMoney, num, toneOf } from "$lib/format";
  import {
    positions,
    positionsLoading,
    positionsError,
    refreshPositions,
    posFilter,
    posSymbols,
    type PosFilter,
  } from "$lib/stores";

  const POLL_MS = 30_000;
  let refreshing = $state(false);

  const FILTERS = [
    { label: "All", value: "all" },
    { label: "Open only", value: "open" },
    { label: "Closed only", value: "closed" },
  ];

  // Every position shares the account's currency in practice; a genuinely
  // multi-currency statement is flagged by the backend's currency_warning
  // elsewhere (Overview / Transactions).
  const currency = $derived($positions?.positions[0]?.currency ?? "USD");

  const symbolCounts = $derived.by(() => {
    const m = new Map<string, number>();
    for (const p of $positions?.positions ?? []) m.set(p.symbol, (m.get(p.symbol) ?? 0) + 1);
    return m;
  });

  const filtered = $derived.by(() => {
    const all = $positions?.positions ?? [];
    const byStatus = all.filter((p) => {
      if ($posFilter === "open") return p.is_open;
      if ($posFilter === "closed") return !p.is_open;
      return true;
    });
    return $posSymbols.length ? byStatus.filter((p) => $posSymbols.includes(p.symbol)) : byStatus;
  });

  const total = $derived(
    filtered.reduce((sum, p) => sum + (p.realized_pnl === null ? 0 : num(p.realized_pnl)), 0),
  );

  async function handleRefresh() {
    refreshing = true;
    try {
      await refreshPositions();
    } finally {
      refreshing = false;
    }
  }

  onMount(() => {
    refreshPositions();
    const id = setInterval(() => refreshPositions(), POLL_MS);
    return () => clearInterval(id);
  });
</script>

<svelte:head><title>Positions · IBKR Realized P&L</title></svelte:head>

<div class="page">
  <PageHeader
    eyebrow="Round-trip P&amp;L · Flex statement"
    title="Positions"
    sticky
    onRefresh={handleRefresh}
    {refreshing}
  >
    {#snippet right()}
      {#if $positions}
        <span class="total {toneOf(total)}">{fmtMoney(total, currency)}</span>
      {/if}
      <PeriodPicker />
      <SegToggle
        options={FILTERS}
        active={$posFilter}
        onChange={(v) => posFilter.set(v as PosFilter)}
      />
    {/snippet}
  </PageHeader>

  <AlertBar messages={[$positionsError, $positions?.flex_error]} />

  {#if $positions}
    <div class="toolbar">
      <SymbolFilter
        counts={symbolCounts}
        active={$posSymbols}
        onChange={(next) => posSymbols.set(next)}
      />
    </div>
  {/if}

  {#if $positionsLoading && !$positions}
    <SkeletonCard height={480} rows={8} />
  {:else if $positions}
    <PositionsTable positions={filtered} {currency} />
  {:else}
    <div class="panel-empty">
      Could not load positions. Check that the backend is running on port 9001.
    </div>
  {/if}
</div>

<style>
  .page {
    padding: var(--page-py) var(--page-px);
    width: 100%;
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
  .toolbar {
    margin-bottom: 14px;
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
