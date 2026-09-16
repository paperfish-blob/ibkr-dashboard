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
  import SymbolChart from "$lib/components/SymbolChart.svelte";
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
  import { api, findPositionByParams, type MarketDataResult, type OHLCVBar, type PositionLeg } from "$lib/api";
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

  // The chart is a separate, optional data source (see market_data.py) --
  // fetched once the position (and so its symbol) resolves, independent of
  // the position/transaction data's own refresh cycle.
  let marketData = $state<MarketDataResult | null>(null);
  let marketDataLoading = $state(false);
  $effect(() => {
    const symbol = position?.symbol;
    if (!symbol) return;
    marketDataLoading = true;
    api
      .marketDataOhlcv(symbol)
      .then((r) => (marketData = r))
      .catch(
        (e) =>
          (marketData = {
            ok: false,
            symbol,
            bars: [],
            error: e instanceof Error ? e.message : "Failed to load chart",
          }),
      )
      .finally(() => (marketDataLoading = false));
  });

  /** Trading-day lookback, not calendar days -- 21/63/126/252 approximate a
   *  month/quarter/half-year/year of sessions. Close enough for a summary
   *  tile; not meant to match any vendor's own period math exactly. */
  function pctChangeAt(bars: OHLCVBar[], tradingDaysBack: number): number | null {
    if (bars.length < 2) return null;
    const lastIdx = bars.length - 1;
    const idx = lastIdx - tradingDaysBack;
    if (idx < 0) return null;
    const base = bars[idx].close;
    if (base === 0) return null;
    return ((bars[lastIdx].close - base) / base) * 100;
  }
  function pctChangeYTD(bars: OHLCVBar[]): number | null {
    if (bars.length < 2) return null;
    const lastYear = bars[bars.length - 1].time.slice(0, 4);
    const idx = bars.findIndex((b) => b.time.slice(0, 4) === lastYear);
    if (idx < 0) return null;
    const base = bars[idx].close;
    if (base === 0) return null;
    return ((bars[bars.length - 1].close - base) / base) * 100;
  }
  const periodReturns = $derived.by(() => {
    const bars = marketData?.bars ?? [];
    return [
      { key: "1D", value: pctChangeAt(bars, 1) },
      { key: "5D", value: pctChangeAt(bars, 5) },
      { key: "1M", value: pctChangeAt(bars, 21) },
      { key: "3M", value: pctChangeAt(bars, 63) },
      { key: "6M", value: pctChangeAt(bars, 126) },
      { key: "1Y", value: pctChangeAt(bars, 252) },
      { key: "YTD", value: pctChangeYTD(bars) },
    ];
  });
  const headlineReturn = $derived(periodReturns.find((p) => p.key === "3M") ?? periodReturns[0]);

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
          <div>
            <span class="chart-title">1D</span>
            <span class="chart-sub">Daily Chart</span>
          </div>
          {#if marketData?.ok}
            <div class="chart-headline">
              <div class="chart-headline-val {toneOf(headlineReturn.value ?? 0)}">
                {headlineReturn.value !== null
                  ? `${headlineReturn.value >= 0 ? "+" : ""}${headlineReturn.value.toFixed(2)}%`
                  : EM_DASH}
              </div>
              <div class="chart-headline-sub">{headlineReturn.key}</div>
            </div>
          {/if}
        </div>

        {#if marketDataLoading}
          <SkeletonCard height={280} rows={0} />
        {:else if marketData?.ok}
          <SymbolChart history={marketData.bars} height={280} />
          <div class="ret-tiles">
            {#each periodReturns as { key, value } (key)}
              <div class="ret-tile" class:active={key === headlineReturn.key}>
                <div class="ret-key">{key}</div>
                <div class="ret-val {value !== null ? toneOf(value) : ''}">
                  {value !== null ? `${value >= 0 ? "+" : ""}${value.toFixed(1)}%` : EM_DASH}
                </div>
              </div>
            {/each}
          </div>
        {:else}
          <div class="chart-empty">
            <div class="chart-empty-title">No price chart available for {position.symbol}</div>
            <div class="chart-empty-body">
              {marketData?.error ||
                "This dashboard only fetches trade fills and P&L (Flex statements and IB Gateway) -- charting needs a separate market-data source, which isn't reachable right now."}
            </div>
          </div>
        {/if}
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
    align-items: flex-start;
    justify-content: space-between;
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
    margin-left: 6px;
  }
  .chart-headline {
    text-align: right;
  }
  .chart-headline-val {
    font-size: var(--text-2lg);
    font-weight: var(--weight-bold);
    letter-spacing: -0.01em;
    font-variant-numeric: tabular-nums;
  }
  .chart-headline-val.pos {
    color: var(--up);
  }
  .chart-headline-val.neg {
    color: var(--dn);
  }
  .chart-headline-val.flat {
    color: var(--text);
  }
  .chart-headline-sub {
    font-size: var(--text-2xs);
    color: var(--dim-45);
  }

  .ret-tiles {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 8px;
    padding: 14px 18px 18px;
  }
  .ret-tile {
    padding: 8px 10px;
    border-radius: var(--radius-md);
    background: var(--surface-02);
    border: 1px solid var(--border-05);
  }
  .ret-tile.active {
    background: var(--up-bg);
    border-color: var(--up);
  }
  .ret-key {
    font-size: var(--text-2xs);
    color: var(--dim-55);
    letter-spacing: 0.1em;
    font-weight: var(--weight-semibold);
  }
  .ret-val {
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    font-variant-numeric: tabular-nums;
    margin-top: 2px;
  }
  .ret-val.pos {
    color: var(--up);
  }
  .ret-val.neg {
    color: var(--dn);
  }
  .ret-val.flat {
    color: var(--text);
  }
  @media (max-width: 640px) {
    .ret-tiles {
      grid-template-columns: repeat(4, 1fr);
    }
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
