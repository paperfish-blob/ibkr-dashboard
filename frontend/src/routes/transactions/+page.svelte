<script lang="ts">
  import { onMount } from "svelte";
  import PageHeader from "$lib/components/PageHeader.svelte";
  import SegToggle from "$lib/components/SegToggle.svelte";
  import TransactionLedger from "$lib/components/TransactionLedger.svelte";
  import SkeletonCard from "$lib/components/SkeletonCard.svelte";
  import AlertBar from "$lib/components/AlertBar.svelte";
  import { fmtDay, fmtMoney, num, toneOf } from "$lib/format";
  import {
    transactions,
    transactionsLoading,
    transactionsError,
    refreshTransactions,
    txFilter,
    type TxFilter,
  } from "$lib/stores";

  const POLL_MS = 30_000;
  let refreshing = $state(false);

  const FILTERS = [
    { label: "All trades", value: "all" },
    { label: "Realized only", value: "realized" },
  ];

  // Every trade shares the account's currency in practice; a genuinely
  // multi-currency statement is flagged by the backend's currency_warning.
  const currency = $derived($transactions?.days[0]?.trades[0]?.currency ?? "USD");
  const total = $derived(num($transactions?.total_realized ?? 0));

  async function handleRefresh() {
    refreshing = true;
    try {
      await refreshTransactions(true);
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
      <SegToggle
        options={FILTERS}
        active={$txFilter}
        onChange={(v) => txFilter.set(v as TxFilter)}
      />
    {/snippet}
  </PageHeader>

  <AlertBar messages={[$transactionsError, $transactions?.flex_error]} />

  {#if $transactionsLoading && !$transactions}
    <SkeletonCard height={480} rows={8} />
  {:else if $transactions}
    <TransactionLedger days={$transactions.days} filter={$txFilter} {currency} />
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
