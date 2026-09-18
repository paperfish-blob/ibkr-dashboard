<script lang="ts">
  import { onMount } from "svelte";
  import { browser } from "$app/environment";
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import PageHeader from "$lib/components/PageHeader.svelte";
  import SegToggle from "$lib/components/SegToggle.svelte";
  import SymbolFilter from "$lib/components/SymbolFilter.svelte";
  import MonthFilter from "$lib/components/MonthFilter.svelte";
  import TransactionLedger from "$lib/components/TransactionLedger.svelte";
  import SkeletonCard from "$lib/components/SkeletonCard.svelte";
  import AlertBar from "$lib/components/AlertBar.svelte";
  import PeriodPicker from "$lib/components/PeriodPicker.svelte";
  import { fmtDay, fmtMoney, num, toneOf } from "$lib/format";
  import {
    transactions,
    transactionsLoading,
    transactionsError,
    refreshTransactions,
    period,
    setPeriod,
    txFilter,
    txSymbols,
    txMonths,
    txGroupFills,
    type TxFilter,
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
    if (filter === "all" || filter === "realized" || filter === "opening") txFilter.set(filter);

    const symbols = qs.get("symbols");
    if (symbols) txSymbols.set(symbols.split(",").filter(Boolean));

    const months = qs.get("months");
    if (months) txMonths.set(months.split(",").filter(Boolean));

    if (qs.get("group") === "1") txGroupFills.set(true);
  }

  // A month outside the active year can never match a trade -- "Jan 2026"
  // is meaningless once the year picker is on 2025. Rather than let that
  // combination sit there (and end up shareable in the URL), drop any
  // out-of-year months whenever the year changes, from any source: the
  // year picker, or a URL that named a mismatched year/months pair. Runs
  // once more after its own txMonths.set() with kept.length unchanged, so
  // it settles rather than looping.
  $effect(() => {
    if ($period === "all") return;
    const kept = $txMonths.filter((m) => m.startsWith(`${$period}-`));
    if (kept.length !== $txMonths.length) txMonths.set(kept);
  });

  // Keep the URL in sync with the filters, one-way (store -> URL). Only
  // reads the filter stores, never page.url, so it can't feed back into
  // itself via goto()'s own URL update.
  $effect(() => {
    const parts: string[] = [];
    if ($period !== "all") parts.push(`year=${$period}`);
    if ($txFilter !== "all") parts.push(`filter=${$txFilter}`);
    if ($txSymbols.length > 0) parts.push(`symbols=${$txSymbols.join(",")}`);
    if ($txMonths.length > 0) parts.push(`months=${$txMonths.join(",")}`);
    if ($txGroupFills) parts.push("group=1");

    const qs = parts.join("&");
    goto(qs ? `/transactions?${qs}` : "/transactions", {
      replaceState: true,
      noScroll: true,
      keepFocus: true,
    });
  });

  const FILTERS = [
    { label: "All trades", value: "all" },
    { label: "Realized only", value: "realized" },
    { label: "Opening only", value: "opening" },
  ];

  // Every trade shares the account's currency in practice; a genuinely
  // multi-currency statement is flagged by the backend's currency_warning.
  const currency = $derived($transactions?.days[0]?.trades[0]?.currency ?? "USD");
  const total = $derived(num($transactions?.total_realized ?? 0));

  const symbolCounts = $derived.by(() => {
    const m = new Map<string, number>();
    for (const d of $transactions?.days ?? []) {
      for (const t of d.trades) m.set(t.symbol, (m.get(t.symbol) ?? 0) + 1);
    }
    return m;
  });

  // "YYYY-MM" -> trade count, independent of any active filter -- same as
  // symbolCounts, the full universe for the period so the picker doesn't
  // shrink as filters get applied.
  const monthCounts = $derived.by(() => {
    const m = new Map<string, number>();
    for (const d of $transactions?.days ?? []) {
      const key = d.date.slice(0, 7);
      m.set(key, (m.get(key) ?? 0) + d.trades.length);
    }
    return m;
  });

  // Symbol and month filters narrow the trades within each day, so the
  // day's total has to be recomputed from what's left -- unlike the
  // realized-only filter, an excluded symbol/month's P&L is real money
  // leaving the sum, not an opening trade's guaranteed zero.
  const filteredDays = $derived.by(() => {
    const days = $transactions?.days ?? [];
    return days
      .filter((d) => $txMonths.length === 0 || $txMonths.includes(d.date.slice(0, 7)))
      .map((d) => {
        const trades = $txSymbols.length === 0 ? d.trades : d.trades.filter((t) => $txSymbols.includes(t.symbol));
        const total_pnl = String(trades.reduce((sum, t) => sum + num(t.realized_pnl), 0));
        return { ...d, trades, total_pnl };
      })
      .filter((d) => d.trades.length > 0);
  });

  // The toggle is only worth showing when the account's Flex Query actually
  // carries IB Order ID and at least one order really did fill in pieces --
  // otherwise it's a control with nothing to do.
  const hasPartialFills = $derived.by(() => {
    const counts = new Map<string, number>();
    for (const d of $transactions?.days ?? []) {
      for (const t of d.trades) {
        if (!t.ib_order_id) continue;
        counts.set(t.ib_order_id, (counts.get(t.ib_order_id) ?? 0) + 1);
      }
    }
    return [...counts.values()].some((n) => n > 1);
  });

  async function handleRefresh() {
    refreshing = true;
    try {
      await refreshTransactions();
    } finally {
      refreshing = false;
    }
  }

  onMount(() => {
    refreshTransactions();
    const id = setInterval(() => refreshTransactions(), POLL_MS);
    return () => clearInterval(id);
  });
</script>

<svelte:head><title>Transactions · IBKR Realized P&L</title></svelte:head>

<div class="page">
  <PageHeader
    eyebrow="Trade history · Flex statement"
    title="Transactions"
    sticky
    onRefresh={handleRefresh}
    {refreshing}
  >
    {#snippet right()}
      {#if $transactions}
        <span class="range">
          {#if $transactions.from_date && $transactions.to_date}
            {fmtDay($transactions.from_date)} – {fmtDay($transactions.to_date)}
          {/if}
        </span>
        <span class="total {toneOf(total)}">{fmtMoney(total, currency)}</span>
      {/if}
      <PeriodPicker />
      <SegToggle
        options={FILTERS}
        active={$txFilter}
        onChange={(v) => txFilter.set(v as TxFilter)}
      />
    {/snippet}
  </PageHeader>

  <AlertBar messages={[$transactionsError, $transactions?.flex_error]} />

  {#if $transactions}
    <div class="toolbar">
      <div class="filters-left">
        <SymbolFilter
          counts={symbolCounts}
          active={$txSymbols}
          onChange={(next) => txSymbols.set(next)}
        />
        <MonthFilter
          counts={monthCounts}
          active={$txMonths}
          onChange={(next) => txMonths.set(next)}
        />
      </div>
      {#if hasPartialFills}
        <button
          class="group-toggle"
          class:active={$txGroupFills}
          onclick={() => txGroupFills.update((v) => !v)}
          title="Collapse each order's partial fills into one row"
        >
          <span class="box"></span>
          Group fills
        </button>
      {/if}
    </div>
  {/if}

  {#if $transactionsLoading && !$transactions}
    <SkeletonCard height={480} rows={8} />
  {:else if $transactions}
    <TransactionLedger days={filteredDays} filter={$txFilter} groupFills={$txGroupFills} {currency} />
  {:else}
    <div class="panel-empty">
      Could not load transactions. Check that the backend is running on port 9001.
    </div>
  {/if}
</div>

<style>
  .page {
    padding: var(--page-py) var(--page-px);
    width: 100%;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 14px;
  }
  .filters-left {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  .group-toggle {
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
  .group-toggle .box {
    width: 13px;
    height: 13px;
    border: 1.5px solid var(--border-12);
    border-radius: 3px;
    flex: none;
  }
  .group-toggle.active {
    background: var(--ink);
    color: var(--on-ink);
    border-color: var(--ink);
  }
  .group-toggle.active .box {
    background: var(--on-ink);
    border-color: var(--on-ink);
    position: relative;
  }
  .group-toggle.active .box::after {
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
