<script lang="ts">
  import { onMount } from "svelte";
  import { browser } from "$app/environment";
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import PageHeader from "$lib/components/PageHeader.svelte";
  import SegToggle from "$lib/components/SegToggle.svelte";
  import SymbolFilter from "$lib/components/SymbolFilter.svelte";
  import MonthFilter from "$lib/components/MonthFilter.svelte";
  import PositionsTable from "$lib/components/PositionsTable.svelte";
  import SkeletonCard from "$lib/components/SkeletonCard.svelte";
  import AlertBar from "$lib/components/AlertBar.svelte";
  import PeriodPicker from "$lib/components/PeriodPicker.svelte";
  import { fmtMoney, num, toneOf } from "$lib/format";
  import type { Position } from "$lib/api";
  import {
    positions,
    positionsLoading,
    positionsError,
    refreshPositions,
    period,
    setPeriod,
    posFilter,
    posSymbols,
    posMonths,
    posCarryInOnly,
    posGroupBy,
    type PosFilter,
    type PosGroupBy,
  } from "$lib/stores";

  const POLL_MS = 30_000;
  let refreshing = $state(false);

  // Seed filters from the URL once, on load. Anything absent or invalid
  // leaves the store at whatever persisted() already restored from
  // localStorage. The sync effect below never reads the URL back, so
  // this can't loop with it.
  if (browser) {
    const qs = page.url.searchParams;

    const year = qs.get("year");
    if (year && /^(all|\d{4})$/.test(year)) setPeriod(year);

    const filter = qs.get("filter");
    if (filter === "all" || filter === "open" || filter === "closed") posFilter.set(filter);

    const symbols = qs.get("symbols");
    if (symbols) posSymbols.set(symbols.split(",").filter(Boolean));

    const months = qs.get("months");
    if (months) posMonths.set(months.split(",").filter(Boolean));

    if (qs.get("carryIn") === "1") posCarryInOnly.set(true);

    const groupBy = qs.get("groupBy");
    if (groupBy === "exit" || groupBy === "entry") posGroupBy.set(groupBy);
  }

  // A month outside the active year can never match a position -- same fix
  // as the Transactions page's own txMonths/period reconciliation. Runs
  // once more after its own posMonths.set() with kept.length unchanged, so
  // it settles rather than looping.
  $effect(() => {
    if ($period === "all") return;
    const kept = $posMonths.filter((m) => m.startsWith(`${$period}-`));
    if (kept.length !== $posMonths.length) posMonths.set(kept);
  });

  // Keep the URL in sync with the filters, one-way (store -> URL). Only
  // reads the filter stores, never page.url, so it can't feed back into
  // itself via goto()'s own URL update.
  $effect(() => {
    const parts: string[] = [];
    if ($period !== "all") parts.push(`year=${$period}`);
    if ($posFilter !== "all") parts.push(`filter=${$posFilter}`);
    if ($posSymbols.length > 0) parts.push(`symbols=${$posSymbols.join(",")}`);
    if ($posMonths.length > 0) parts.push(`months=${$posMonths.join(",")}`);
    if ($posCarryInOnly) parts.push("carryIn=1");
    if ($posGroupBy !== "exit") parts.push(`groupBy=${$posGroupBy}`);

    const qs = parts.join("&");
    goto(qs ? `/positions?${qs}` : "/positions", {
      replaceState: true,
      noScroll: true,
      keepFocus: true,
    });
  });

  const FILTERS = [
    { label: "All", value: "all" },
    { label: "Open only", value: "open" },
    { label: "Closed only", value: "closed" },
  ];

  const GROUP_BY = [
    { label: "Exit date", value: "exit" },
    { label: "Entry date", value: "entry" },
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

  // Keyed off whichever date posGroupBy currently keys the table's day bands
  // off -- a position without that date (a still-open position under "exit",
  // a carry-in under "entry") has no month to count toward.
  function groupDate(p: Position): string | null {
    return $posGroupBy === "exit" ? p.exit_date : p.open_date;
  }
  const monthCounts = $derived.by(() => {
    const m = new Map<string, number>();
    for (const p of $positions?.positions ?? []) {
      const d = groupDate(p);
      if (!d) continue;
      const key = d.slice(0, 7);
      m.set(key, (m.get(key) ?? 0) + 1);
    }
    return m;
  });

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
    const byMonth = $posMonths.length
      ? bySymbol.filter((p) => {
          const d = groupDate(p);
          return d !== null && $posMonths.includes(d.slice(0, 7));
        })
      : bySymbol;
    return $posCarryInOnly ? byMonth.filter((p) => p.is_carry_in) : byMonth;
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
      <div class="toolbar-left">
        <SymbolFilter
          counts={symbolCounts}
          active={$posSymbols}
          onChange={(next) => posSymbols.set(next)}
        />
        <MonthFilter
          counts={monthCounts}
          active={$posMonths}
          onChange={(next) => posMonths.set(next)}
        />
      </div>
      <div class="toolbar-right">
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
        <span class="group-label">Group by</span>
        <SegToggle
          options={GROUP_BY}
          active={$posGroupBy}
          onChange={(v) => posGroupBy.set(v as PosGroupBy)}
        />
      </div>
    </div>
  {/if}

  {#if $positionsLoading && !$positions}
    <SkeletonCard height={480} rows={8} />
  {:else if $positions}
    <PositionsTable positions={filtered} {currency} groupBy={$posGroupBy} />
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
  .toolbar-left {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  .toolbar-right {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .group-label {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--dim-45);
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
