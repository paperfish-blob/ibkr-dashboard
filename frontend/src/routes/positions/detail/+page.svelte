<script lang="ts">
  /**
   * One position's detail: entry/exit transaction history alongside a chart
   * of the symbol. No dynamic [param] route -- adapter-static prerenders
   * every route ahead of time, which can't work for an open-ended set of
   * symbols, so the identifying fields travel as a query string instead (see
   * positionDetailParams/findPositionByParams in $lib/api) and get resolved
   * against the same positions the list page already loaded.
   */
  import { onMount } from "svelte";
  import { page } from "$app/stores";
  import { goto } from "$app/navigation";
  import PageHeader from "$lib/components/PageHeader.svelte";
  import SkeletonCard from "$lib/components/SkeletonCard.svelte";
  import AlertBar from "$lib/components/AlertBar.svelte";
  import {
    fmtFullDate,
    fmtMoney,
    fmtPriceLike,
    fmtQty,
    grossAmount,
    num,
    sideClass,
    sideLabel,
    toneOf,
    EM_DASH,
  } from "$lib/format";
  import { findPositionByParams, type PositionLeg } from "$lib/api";
  import { positions, positionsLoading, positionsError, refreshPositions } from "$lib/stores";

  const POLL_MS = 30_000;
  let refreshing = $state(false);

  const position = $derived(
    $positions ? findPositionByParams($positions.positions, $page.url.searchParams) : undefined,
  );

  interface TxRow {
    kind: "entry" | "exit";
    leg: PositionLeg;
    n: number;
  }

  // Entry and exit legs interleaved into one newest-first list, matching the
  // rest of the app -- "Entry"/"Exit" numbering still counts each type in
  // the order it actually happened, same as the table's own exit numbering.
  const txRows = $derived.by((): TxRow[] => {
    if (!position) return [];
    const entries: TxRow[] = position.entry_legs.map((leg, i) => ({ kind: "entry", leg, n: i + 1 }));
    const exits: TxRow[] = position.exit_legs.map((leg, i) => ({ kind: "exit", leg, n: i + 1 }));
    return [...entries, ...exits].sort((a, b) =>
      `${b.leg.trade_date}T${b.leg.trade_time}`.localeCompare(`${a.leg.trade_date}T${a.leg.trade_time}`),
    );
  });

  const entryAmount = $derived(
    position
      ? grossAmount(position.entry_price, position.quantity, position.direction === "short" ? "SELL" : "BUY")
      : null,
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

<svelte:head><title>{position?.symbol ?? "Position"} · IBKR Realized P&L</title></svelte:head>

<div class="page">
  <div class="crumb">
    <a href="/positions">Positions</a>
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
      <path d="M6 4l4 4-4 4" />
    </svg>
    <span>{position?.symbol ?? ($positionsLoading ? "…" : "Not found")}</span>
  </div>

  <PageHeader
    eyebrow="Round-trip P&amp;L · Flex statement"
    title={position?.symbol ?? "Position"}
    sticky
    onRefresh={handleRefresh}
    {refreshing}
    onClose={() => goto("/positions")}
  >
    {#snippet right()}
      {#if position}
        <span class="dir {position.direction}">{position.direction.toUpperCase()}</span>
        {#if position.is_carry_in}
          <span
            class="badge"
            title="Opened before the fetched date range -- entry date, price and true position size are unknown"
          >
            CARRY-IN
          </span>
        {/if}
        <span class="total {position.realized_pnl === null ? '' : toneOf(num(position.realized_pnl))}">
          {position.realized_pnl === null ? "open" : fmtMoney(num(position.realized_pnl), position.currency)}
        </span>
      {/if}
    {/snippet}
  </PageHeader>

  <AlertBar messages={[$positionsError]} />

  {#if $positionsLoading && !$positions}
    <SkeletonCard height={480} rows={8} />
  {:else if position}
    <div class="layout">
      <div class="panel">
        <div class="stats">
          <div class="stat-grid">
            <div class="stat">
              <div class="lbl">Open</div>
              <div class="val full-date">{position.open_date ? fmtFullDate(position.open_date) : EM_DASH}</div>
            </div>
            <div class="stat">
              <div class="lbl">Time</div>
              <div class="val">{position.open_time || EM_DASH}</div>
            </div>
            <div class="stat">
              <div class="lbl">Entry Price</div>
              <div class="val">
                {position.entry_price !== null
                  ? fmtPriceLike(num(position.entry_price), position.currency, 4)
                  : EM_DASH}
              </div>
            </div>
            <div class="stat">
              <div class="lbl">Qty</div>
              <div class="val">{fmtQty(num(position.quantity))}</div>
            </div>
            <div class="stat">
              <div class="lbl">Exit Date</div>
              <div class="val full-date">{position.exit_date ? fmtFullDate(position.exit_date) : EM_DASH}</div>
            </div>
            <div class="stat">
              <div class="lbl">Exits #</div>
              <div class="val">{position.exit_count || EM_DASH}</div>
            </div>
            <div class="stat">
              <div class="lbl">Amount</div>
              <div class="val">{entryAmount !== null ? fmtPriceLike(entryAmount, position.currency, 2) : EM_DASH}</div>
            </div>
            <div class="stat">
              <div class="lbl">Comm.</div>
              <div class="val">
                {num(position.commission) !== 0
                  ? fmtPriceLike(Math.abs(num(position.commission)), position.currency, 2)
                  : EM_DASH}
              </div>
            </div>
          </div>
        </div>

        <div class="tx-hd">Transactions · newest first</div>
        <div class="tx-list">
          {#each txRows as { kind, leg, n } (kind + n)}
            {@const legAmount = grossAmount(leg.price, leg.quantity, leg.buy_sell)}
            <div class="tx-row">
              <div class="tx-left">
                <span class="tx-label">{kind === "entry" ? "Entry" : "Exit"} {n}</span>
                <span class="side {sideClass(leg.buy_sell)}">{sideLabel(leg.buy_sell)}</span>
                {#if leg.fill_count > 1}<span class="fills">×{leg.fill_count} fills</span>{/if}
              </div>
              <div class="tx-right">
                <div class="tx-px">
                  {fmtQty(num(leg.quantity))} @ {leg.price !== null ? fmtPriceLike(num(leg.price), position.currency, 4) : EM_DASH}
                  {#if legAmount !== null}
                    <span class="tx-amount">{fmtPriceLike(legAmount, position.currency, 2)}</span>
                  {/if}
                  {#if kind === "exit"}
                    <span class="tx-pnl {toneOf(num(leg.realized_pnl))}">{fmtMoney(num(leg.realized_pnl), position.currency)}</span>
                  {:else}
                    <span class="tx-pnl dash">{EM_DASH}</span>
                  {/if}
                </div>
                <div class="tx-meta">{fmtFullDate(leg.trade_date)}, {leg.trade_time || EM_DASH}</div>
              </div>
            </div>
          {/each}
        </div>
      </div>

      <div class="panel">
        <div class="chart-toolbar">
          <span class="chart-title">{position.symbol}</span>
          <span class="chart-sub">
            {position.open_date ? fmtFullDate(position.open_date) : "Unknown open"} –
            {position.exit_date ? fmtFullDate(position.exit_date) : "still open"}
          </span>
        </div>
        <div class="chart-empty">
          <div class="chart-empty-title">No price chart available yet</div>
          <div class="chart-empty-body">
            This dashboard only fetches trade fills and P&amp;L (Flex statements and IB Gateway) -- it has no
            market-data source to draw a price chart from. Gateway's own API does support historical bars, but
            Gateway needs a daily interactive login and is disconnected most of the time, so a chart wired to it
            would often show nothing anyway.
          </div>
        </div>
      </div>
    </div>
  {:else}
    <div class="panel-empty">
      Position not found. It may not exist in the currently selected period, or the link is stale.
    </div>
  {/if}
</div>

<style>
  .page {
    padding: var(--page-py) var(--page-px);
    width: 100%;
  }

  .crumb {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: var(--text-xs);
    color: var(--dim-55);
    /* PageHeader's sticky variant pulls itself up by --page-py to bleed
       edge-to-edge; without at least that much clearance below, it slides
       up over this row instead of sitting under it. */
    margin-bottom: var(--page-py);
  }
  .crumb a {
    color: var(--dim-55);
  }
  .crumb svg {
    width: 11px;
    height: 11px;
    flex: none;
  }

  .dir {
    display: inline-block;
    font-size: var(--text-2xs);
    font-weight: var(--weight-bold);
    letter-spacing: 0.04em;
    padding: 3px 9px;
    border-radius: var(--radius-pill);
    background: var(--accent-bg);
    color: var(--accent);
  }
  .dir.short {
    background: var(--ai-bg);
    color: var(--ai);
  }
  .badge {
    display: inline-block;
    font-size: var(--text-2xs);
    font-weight: var(--weight-bold);
    letter-spacing: 0.04em;
    padding: 3px 8px;
    border-radius: var(--radius-pill);
    background: transparent;
    color: var(--dim-45);
    border: 1px dashed var(--border);
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

  .layout {
    display: grid;
    grid-template-columns: 380px 1fr;
    gap: 18px;
    align-items: start;
  }
  @media (max-width: 900px) {
    .layout {
      grid-template-columns: 1fr;
    }
  }

  .panel {
    background: var(--surface);
    border: 1px solid var(--border-05);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }

  .stats {
    padding: 16px 18px;
    border-bottom: 1px solid var(--border-05);
  }
  .stat-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px 16px;
  }
  .stat .lbl {
    font-size: var(--text-2xs);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--dim-45);
    margin-bottom: 2px;
  }
  .stat .val {
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
    font-variant-numeric: tabular-nums;
  }
  .stat .val.full-date {
    font-size: var(--text-xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--dim-70);
  }

  .tx-hd {
    padding: 12px 18px 8px;
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--dim-55);
  }
  .tx-list {
    display: flex;
    flex-direction: column;
  }
  .tx-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
    padding: 9px 18px;
    border-top: 1px solid var(--border-05);
    font-size: var(--text-xs);
  }
  .tx-left {
    display: flex;
    align-items: center;
    gap: 7px;
    min-width: 0;
  }
  .tx-label {
    color: var(--dim-45);
    font-weight: var(--weight-semibold);
    white-space: nowrap;
  }
  .side {
    font-weight: var(--weight-semibold);
  }
  .side.buy {
    color: var(--accent);
  }
  .side.sell {
    color: var(--dn);
  }
  .fills {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    color: var(--accent);
  }
  .tx-right {
    text-align: right;
    flex: none;
  }
  .tx-px {
    font-variant-numeric: tabular-nums;
    color: var(--dim-70);
    font-size: var(--text-2xs);
  }
  .tx-amount {
    margin-left: 6px;
    color: var(--dim-45);
  }
  .tx-pnl {
    margin-left: 8px;
    font-weight: var(--weight-semibold);
    font-variant-numeric: tabular-nums;
  }
  .tx-pnl.pos {
    color: var(--up);
  }
  .tx-pnl.neg {
    color: var(--dn);
  }
  .tx-pnl.dash {
    color: var(--dim-35);
    font-weight: var(--weight-medium);
  }

  .chart-toolbar {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 12px 18px;
    border-bottom: 1px solid var(--border-05);
  }
  .chart-title {
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }
  .chart-sub {
    font-size: var(--text-2xs);
    color: var(--dim-45);
  }
  .chart-empty {
    padding: 60px 40px;
    text-align: center;
  }
  .chart-empty-title {
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    color: var(--text);
    margin-bottom: 8px;
  }
  .chart-empty-body {
    font-size: var(--text-xs);
    color: var(--dim-55);
    line-height: 1.6;
    max-width: 46ch;
    margin: 0 auto;
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
