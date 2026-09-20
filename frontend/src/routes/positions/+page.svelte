<script lang="ts">
  import { onMount } from "svelte";
  import { browser } from "$app/environment";
  import { goto, afterNavigate } from "$app/navigation";
  import { page } from "$app/state";
  import PageHeader from "$lib/components/PageHeader.svelte";
  import SegToggle from "$lib/components/SegToggle.svelte";
  import SymbolFilter from "$lib/components/SymbolFilter.svelte";
  import AdvancedFilters from "$lib/components/AdvancedFilters.svelte";
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
    posCarryInOnly,
    posGroupBy,
    posSide,
    posDateFrom,
    posDateTo,
    posAssetCategories,
    type PosFilter,
    type PosGroupBy,
  } from "$lib/stores";

  const POLL_MS = 30_000;
  let refreshing = $state(false);

  // Every field a URL can seed onto this page's filters, applied on top of
  // whatever's already there -- absent or invalid leaves a store at
  // whatever persisted() already restored from localStorage.
  function applyFiltersFromUrl(qs: URLSearchParams) {
    const year = qs.get("year");
    if (year && /^(all|\d{4})$/.test(year)) setPeriod(year);

    const filter = qs.get("filter");
    if (filter === "all" || filter === "open" || filter === "closed") posFilter.set(filter);

    const symbols = qs.get("symbols");
    if (symbols) posSymbols.set(symbols.split(",").filter(Boolean));

    if (qs.get("carryIn") === "1") posCarryInOnly.set(true);

    const groupBy = qs.get("groupBy");
    if (groupBy === "exit" || groupBy === "entry") posGroupBy.set(groupBy);

    const side = qs.get("side");
    if (side === "all" || side === "long" || side === "short") posSide.set(side);

    const dateFrom = qs.get("dateFrom");
    if (dateFrom && /^\d{4}-\d{2}-\d{2}$/.test(dateFrom)) posDateFrom.set(dateFrom);

    const dateTo = qs.get("dateTo");
    if (dateTo && /^\d{4}-\d{2}-\d{2}$/.test(dateTo)) posDateTo.set(dateTo);

    const assetCat = qs.get("assetCat");
    if (assetCat) posAssetCategories.set(assetCat.split(",").filter(Boolean));
  }

  function resetAllFilters() {
    setPeriod("all");
    posFilter.set("all");
    posSymbols.set([]);
    posCarryInOnly.set(false);
    posGroupBy.set("exit");
    posSide.set("all");
    posDateFrom.set(null);
    posDateTo.set(null);
    posAssetCategories.set([]);
  }

  // Seed filters from the URL once, on load. The sync effect below never
  // reads the URL back, so this can't loop with it.
  if (browser) {
    const qs = page.url.searchParams;
    if (qs.get("reset") === "1") resetAllFilters();
    applyFiltersFromUrl(qs);
  }

  // The block above only runs once, when this component is first created --
  // but the top-nav link into this page (which carries `reset=1` to land on
  // a clean view regardless of whatever filters were left set) is a link to
  // this same route, so clicking it while already on /positions is a
  // same-route navigation that SvelteKit serves by reusing this exact
  // component instance rather than remounting it. afterNavigate fires on
  // every navigation that lands here, mount included, so it catches that
  // case too -- gated on `reset` so it's a no-op for the sync effect's own
  // goto() calls below, which never set it.
  afterNavigate(({ to }) => {
    const qs = to?.url.searchParams;
    if (qs?.get("reset") === "1") {
      resetAllFilters();
      applyFiltersFromUrl(qs);
    }
  });

  // A date range outside the active year can never match a position --
  // same fix as the Transactions page's own txMonths/period reconciliation
  // used to apply to months here too, before "which dates" collapsed onto
  // this one range instead of two overlapping filters. Runs once more
  // after its own .set() calls with nothing left to change, so it settles
  // rather than looping.
  $effect(() => {
    if ($period === "all") return;
    const yearStart = `${$period}-01-01`;
    const yearEnd = `${$period}-12-31`;
    // Entirely outside the new year -- nothing left to clip to, so clear
    // both ends rather than collapse them onto one meaningless boundary.
    if (($posDateTo && $posDateTo < yearStart) || ($posDateFrom && $posDateFrom > yearEnd)) {
      if ($posDateFrom !== null) posDateFrom.set(null);
      if ($posDateTo !== null) posDateTo.set(null);
    } else {
      if ($posDateFrom && $posDateFrom < yearStart) posDateFrom.set(yearStart);
      if ($posDateTo && $posDateTo > yearEnd) posDateTo.set(yearEnd);
    }
  });

  // Keep the URL in sync with the filters, one-way (store -> URL). Only
  // reads the filter stores, never page.url, so it can't feed back into
  // itself via goto()'s own URL update.
  $effect(() => {
    const parts: string[] = [];
    if ($period !== "all") parts.push(`year=${$period}`);
    if ($posFilter !== "all") parts.push(`filter=${$posFilter}`);
    if ($posSymbols.length > 0) parts.push(`symbols=${$posSymbols.join(",")}`);
    if ($posCarryInOnly) parts.push("carryIn=1");
    if ($posGroupBy !== "exit") parts.push(`groupBy=${$posGroupBy}`);
    if ($posSide !== "all") parts.push(`side=${$posSide}`);
    if ($posDateFrom) parts.push(`dateFrom=${$posDateFrom}`);
    if ($posDateTo) parts.push(`dateTo=${$posDateTo}`);
    if ($posAssetCategories.length > 0) parts.push(`assetCat=${$posAssetCategories.join(",")}`);

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

  const categoryCounts = $derived.by(() => {
    const m = new Map<string, number>();
    for (const p of $positions?.positions ?? []) m.set(p.asset_category, (m.get(p.asset_category) ?? 0) + 1);
    return m;
  });

  // Keyed off whichever date posGroupBy currently keys the table's day bands
  // off -- a position without that date (a still-open position under "exit",
  // a carry-in under "entry") has no month to count toward.
  function groupDate(p: Position): string | null {
    return $posGroupBy === "exit" ? p.exit_date : p.open_date;
  }

  // Keeps a manually-picked date inside whichever year is currently
  // selected -- the reconciling $effect above only reacts to $period
  // itself changing, so a date typed in while a specific year is already
  // active needs this instead to land inside it right away.
  function clipToPeriod(d: string | null): string | null {
    if (!d || $period === "all") return d;
    const yearStart = `${$period}-01-01`;
    const yearEnd = `${$period}-12-31`;
    if (d < yearStart) return yearStart;
    if (d > yearEnd) return yearEnd;
    return d;
  }

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
    const byDateRange =
      $posDateFrom || $posDateTo
        ? bySymbol.filter((p) => {
            const d = groupDate(p);
            if (d === null) return false;
            if ($posDateFrom && d < $posDateFrom) return false;
            if ($posDateTo && d > $posDateTo) return false;
            return true;
          })
        : bySymbol;
    const bySide = $posSide === "all" ? byDateRange : byDateRange.filter((p) => p.direction === $posSide);
    const byCategory = $posAssetCategories.length
      ? bySide.filter((p) => $posAssetCategories.includes(p.asset_category))
      : bySide;
    return $posCarryInOnly ? byCategory.filter((p) => p.is_carry_in) : byCategory;
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
      </div>
      <div class="toolbar-right">
        <AdvancedFilters
          dateFrom={$posDateFrom}
          dateTo={$posDateTo}
          onDateChange={(from, to) => {
            posDateFrom.set(clipToPeriod(from));
            posDateTo.set(clipToPeriod(to));
          }}
          side={$posSide}
          onSideChange={(v) => posSide.set(v)}
          categories={categoryCounts}
          activeCategories={$posAssetCategories}
          onCategoriesChange={(next) => posAssetCategories.set(next)}
          matchCount={filtered.length}
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
