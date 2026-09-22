<script lang="ts">
  /**
   * Currently-open holdings only -- Open (Full) and Open (Partial), never
   * Closed, and carry-in positions are excluded outright (their entry price
   * and date are unknown by definition, so cost basis and unrealized P&L
   * can't be computed for them). Forces period="all" on entry so a position
   * opened in an earlier year than whatever's selected elsewhere doesn't
   * silently disappear from a page whose whole point is "what am I holding
   * right now."
   */
  import { onMount } from "svelte";
  import { browser } from "$app/environment";
  import { afterNavigate, goto } from "$app/navigation";
  import { page } from "$app/state";
  import PageHeader from "$lib/components/PageHeader.svelte";
  import SkeletonCard from "$lib/components/SkeletonCard.svelte";
  import AlertBar from "$lib/components/AlertBar.svelte";
  import OpenPositionsSummary from "$lib/components/OpenPositionsSummary.svelte";
  import OpenPositionsList from "$lib/components/OpenPositionsList.svelte";
  import type { OpenPositionsRow } from "$lib/components/OpenPositionsList.svelte";
  import { api, type Position } from "$lib/api";
  import { daysSince, num } from "$lib/format";
  import { positions, positionsLoading, positionsError, refreshPositions, setPeriod } from "$lib/stores";

  const POLL_MS = 30_000;
  let refreshing = $state(false);

  function handleReset(url: URL) {
    if (url.searchParams.get("reset") !== "1") return;
    setPeriod("all");
    goto("/positions/open", { replaceState: true, noScroll: true, keepFocus: true });
  }
  if (browser) handleReset(page.url);
  afterNavigate(({ to }) => {
    if (to) handleReset(to.url);
  });

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

  const currency = $derived($positions?.positions[0]?.currency ?? "USD");

  // A cash/currency balance (asset_category "CASH", e.g. a forex pair like
  // USD.SGD) has no market price to mark against -- it isn't a tradable
  // holding this page's unrealized-P&L framing applies to, so it's
  // excluded the same as a carry-in rather than shown with a permanent
  // dash in every price column.
  const openPositions = $derived(
    ($positions?.positions ?? []).filter((p) => p.is_open && !p.is_carry_in && p.asset_category !== "CASH"),
  );
  const carryInExcluded = $derived(
    ($positions?.positions ?? []).filter((p) => p.is_open && p.is_carry_in).length,
  );
  const cashExcluded = $derived(
    ($positions?.positions ?? []).filter((p) => p.is_open && !p.is_carry_in && p.asset_category === "CASH").length,
  );

  // One latest-close fetch per distinct symbol, cached for the session --
  // small N in practice (only currently-open symbols), and cheap since
  // it's the same OHLCV endpoint the detail page's own chart already uses.
  let currentPrices = $state<Map<string, number>>(new Map());
  let priceFailed = $state<Set<string>>(new Set());

  $effect(() => {
    const symbols = [...new Set(openPositions.map((p) => p.symbol))];
    const missing = symbols.filter((s) => !currentPrices.has(s) && !priceFailed.has(s));
    if (missing.length === 0) return;
    (async () => {
      for (const symbol of missing) {
        try {
          const res = await api.marketDataOhlcv(symbol, 5);
          const last = res.ok ? res.bars.at(-1) : undefined;
          if (last) {
            currentPrices = new Map(currentPrices).set(symbol, last.close);
          } else {
            priceFailed = new Set(priceFailed).add(symbol);
          }
        } catch {
          priceFailed = new Set(priceFailed).add(symbol);
        }
      }
    })();
  });

  function toRow(p: Position): OpenPositionsRow {
    // For an open, non-carry-in position the backend already nets exits
    // out of quantity (src/ibkr_pnl/positions.py: entry_total - exit_total)
    // -- it's the remaining size, not the original entry size, so it's used
    // as-is rather than subtracting exit_legs again.
    const qtyOpen = num(p.quantity);
    const entryPrice = num(p.entry_price);
    const costBasis = qtyOpen * entryPrice;
    const current = currentPrices.get(p.symbol) ?? null;
    const unrealized =
      current === null ? null : (p.direction === "long" ? current - entryPrice : entryPrice - current) * qtyOpen;
    return {
      p,
      status: p.exit_count > 0 ? "partial" : "full",
      qtyOpen,
      entryPrice,
      costBasis,
      current,
      unrealized,
      interim: p.exit_count > 0 ? num(p.realized_pnl) : null,
      daysHeld: p.open_date ? daysSince(p.open_date) : null,
    };
  }

  const rows = $derived(openPositions.map(toRow));
  const totalUnrealized = $derived(rows.reduce((sum, r) => sum + (r.unrealized ?? 0), 0));
  const totalCost = $derived(rows.reduce((sum, r) => sum + r.costBasis, 0));
  const fullCount = $derived(rows.filter((r) => r.status === "full").length);
  const partialCount = $derived(rows.filter((r) => r.status === "partial").length);
</script>

<svelte:head><title>Open Positions · IBKR Realized P&L</title></svelte:head>

<div class="page">
  <PageHeader
    eyebrow="Round-trip P&amp;L · Flex statement"
    title="Open Positions"
    sticky
    onRefresh={handleRefresh}
    {refreshing}
  />
  <div class="excl-note">
    Showing Open (Full) and Open (Partial) only · {carryInExcluded} carry-in position{carryInExcluded === 1
      ? ""
      : "s"} excluded (entry price/date unknown for those, so cost basis and unrealized P&amp;L can't be computed)
    {#if cashExcluded > 0}
      · {cashExcluded} cash balance{cashExcluded === 1 ? "" : "s"} excluded (no market price to mark against)
    {/if}
  </div>

  <AlertBar messages={[$positionsError, $positions?.flex_error]} />

  {#if $positionsLoading && !$positions}
    <SkeletonCard height={140} rows={2} />
    <div class="gap"></div>
    <SkeletonCard height={360} rows={6} />
  {:else if $positions}
    {#if rows.length === 0}
      <div class="panel-empty">No open positions right now.</div>
    {:else}
      <OpenPositionsSummary
        {totalUnrealized}
        {totalCost}
        openCount={rows.length}
        {fullCount}
        {partialCount}
        {carryInExcluded}
        {currency}
      />
      <div class="gap"></div>
      <OpenPositionsList {rows} {currency} />
    {/if}
  {:else}
    <div class="panel-empty">Could not load positions. Check that the backend is running on port 9001.</div>
  {/if}
</div>

<style>
  .page {
    padding: var(--page-py) var(--page-px);
    width: 100%;
  }
  .excl-note {
    font-size: var(--text-xs);
    color: var(--dim-45);
    margin-top: -8px;
    margin-bottom: 16px;
  }
  .gap {
    height: 16px;
  }
  .panel-empty {
    padding: 40px 18px;
    text-align: center;
    color: var(--dim-55);
    background: var(--surface);
    border: 1px solid var(--border-05);
    border-radius: var(--radius-lg);
  }
</style>
