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
    posCarryInOnly,
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

  const carryInCount = $derived(($positions?.positions ?? []).filter((p) => p.is_carry_in).length);

  const filtered = $derived.by(() => {
    const all = $positions?.positions ?? [];
    const byStatus = all.filter((p) => {
      if ($posFilter === "open") return p.is_open;
      if ($posFilter === "closed") return !p.is_open;
      return true;
    });
    const bySymbol = $posSymbols.length
      ? byStatus.filter((p) => $posSymbols.includes(p.symbol))
      : byStatus;
    return $posCarryInOnly ? bySymbol.filter((p) => p.is_carry_in) : bySymbol;
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
      {#if carryInCount > 0}
        <button
          class="carry-toggle"
          class:active={$posCarryInOnly}
          onclick={() => posCarryInOnly.update((v) => !v)}
          title="Positions whose opening trade is outside the fetched date range"
        >
          <span class="box"></span>
          Carry-in only
          <span class="count">{carryInCount}</span>
        </button>
      {/if}
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
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 14px;
  }
  .carry-toggle {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 6px 11px;
    border-radius: var(--radius-pill);
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--dim-70);
    font-family: var(--font-sans);
    font-size: var(--text-xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.01em;
    cursor: pointer;
    white-space: nowrap;
  }
  .carry-toggle .box {
    width: 13px;
    height: 13px;
    border: 1.5px solid var(--border-12);
    border-radius: 3px;
    flex: none;
  }
  .carry-toggle .count {
    color: var(--dim-45);
    font-variant-numeric: tabular-nums;
  }
  .carry-toggle.active {
    background: var(--ink);
    color: var(--on-ink);
    border-color: var(--ink);
  }
  .carry-toggle.active .box {
    background: var(--on-ink);
    border-color: var(--on-ink);
    position: relative;
  }
  .carry-toggle.active .box::after {
    content: "";
    position: absolute;
    left: 2.5px;
    top: 1.5px;
    width: 6px;
    height: 3px;
    border-left: 1.5px solid var(--ink);
    border-bottom: 1.5px solid var(--ink);
    transform: rotate(-45deg);
  }
  .carry-toggle.active .count {
    color: rgba(255, 255, 255, 0.6);
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
