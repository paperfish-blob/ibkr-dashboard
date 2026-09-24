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
  import SegToggle from "$lib/components/SegToggle.svelte";
  import PotentialPnlPanel from "$lib/components/PotentialPnlPanel.svelte";
  import type { PositionSeries } from "$lib/components/PotentialPnlPanel.svelte";
  import OpenPositionsSummary from "$lib/components/OpenPositionsSummary.svelte";
  import OpenPositionsList from "$lib/components/OpenPositionsList.svelte";
  import OpenPositionCountPanel from "$lib/components/OpenPositionCountPanel.svelte";
  import type { OpenPositionsRow } from "$lib/components/OpenPositionsList.svelte";
  import { api, type CumulativePoint, type OHLCVBar, type Position } from "$lib/api";
  import { daysSince, num, parseISODay } from "$lib/format";
  import { positions, positionsLoading, positionsError, refreshPositions, setPeriod } from "$lib/stores";

  const POLL_MS = 30_000;
  let refreshing = $state(false);

  // Independent of the app-wide Period picker (forced to "all" below) --
  // a floor on the position's own open year, for working around specific
  // years whose sync is known to be unreliable (2022, at the time this was
  // added) without hiding them from every other page too. "all" shows
  // everything; picking a year hides anything opened earlier. `null` means
  // "no explicit choice yet" -- effectiveFromYear below resolves that to
  // the newest year with an open position, rather than hardcoding a year
  // that would go stale.
  let fromYear = $state<string | null>(null);

  function handleReset(url: URL) {
    if (url.searchParams.get("reset") !== "1") return;
    setPeriod("all");
    fromYear = null;
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

  // Only offer years that actually have an open position -- same rule
  // PeriodPicker already follows for downloaded years, so choosing "2023"
  // never silently shows nothing just because nothing opened that year.
  // Newest first (the years someone's actually about to click), "All" last.
  const yearOptions = $derived.by(() => {
    const years = new Set(openPositions.filter((p) => p.open_date).map((p) => p.open_date!.slice(0, 4)));
    return [
      ...[...years].sort().reverse().map((y) => ({ label: y, value: y })),
      { label: "All", value: "all" },
    ];
  });

  // Default to the newest year with an open position rather than "all",
  // so the page opens already clear of older, less-reliable years without
  // needing to hardcode which year that is.
  const effectiveFromYear = $derived(fromYear ?? yearOptions.find((o) => o.value !== "all")?.value ?? "all");

  const yearFilteredPositions = $derived(
    effectiveFromYear === "all"
      ? openPositions
      : openPositions.filter((p) => p.open_date && p.open_date.slice(0, 4) >= effectiveFromYear),
  );
  const hiddenByFromYear = $derived(openPositions.length - yearFilteredPositions.length);

  // Full daily history per distinct symbol, back to that position's own
  // open date (not just a handful of recent days) -- needed for the
  // potential-P&L-over-time chart below, and its last bar doubles as the
  // "current price" the table itself uses. Cached for the session, same
  // OHLCV endpoint the detail page's own chart already uses.
  let historyBars = $state<Map<string, OHLCVBar[]>>(new Map());
  let historyFailed = $state<Set<string>>(new Set());

  $effect(() => {
    const wanted = yearFilteredPositions
      .filter((p) => p.open_date && !historyBars.has(p.symbol) && !historyFailed.has(p.symbol))
      .map((p) => ({ symbol: p.symbol, lookbackDays: daysSince(p.open_date!) + 5 }));
    if (wanted.length === 0) return;
    (async () => {
      for (const { symbol, lookbackDays } of wanted) {
        try {
          const res = await api.marketDataOhlcv(symbol, lookbackDays);
          if (res.ok && res.bars.length) {
            historyBars = new Map(historyBars).set(symbol, res.bars);
          } else {
            historyFailed = new Set(historyFailed).add(symbol);
          }
        } catch {
          historyFailed = new Set(historyFailed).add(symbol);
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
    const current = historyBars.get(p.symbol)?.at(-1)?.close ?? null;
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

  const rows = $derived(yearFilteredPositions.map(toRow));
  const totalUnrealized = $derived(rows.reduce((sum, r) => sum + (r.unrealized ?? 0), 0));
  const totalPartialRealized = $derived(rows.reduce((sum, r) => sum + (r.interim ?? 0), 0));
  const totalCost = $derived(rows.reduce((sum, r) => sum + r.costBasis, 0));
  const fullCount = $derived(rows.filter((r) => r.status === "full").length);
  const partialCount = $derived(rows.filter((r) => r.status === "partial").length);

  // Day-by-day "what would this position be worth if I closed it at that
  // day's close" -- cumulative realized P&L from any exits already taken
  // by that day, plus mark-to-market on whatever quantity was still open
  // as of that day (average cost of the open remainder, standard
  // average-cost accounting: an exit realizes P&L and reduces quantity but
  // never changes the remaining shares' average cost). A position with
  // more than one entry has a cost basis that isn't constant over its
  // life -- e.g. 1 share bought alone, then 12 more added two years
  // later -- so this replays the actual entry/exit legs in order rather
  // than applying the position's single overall (weighted, present-day)
  // entry price across its whole history.
  interface DayPoint {
    date: string;
    value: number;
    open: number;
    close: number;
  }
  function addOneDay(iso: string): string {
    const d = parseISODay(iso);
    d.setDate(d.getDate() + 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }
  function isWeekend(iso: string): boolean {
    const day = parseISODay(iso).getDay();
    return day === 0 || day === 6;
  }

  function potentialPnlSeries(p: Position, bars: OHLCVBar[]): DayPoint[] {
    const events = [
      ...p.entry_legs.map((leg) => ({
        date: leg.trade_date,
        qty: num(leg.quantity),
        price: leg.price === null ? null : num(leg.price),
        realized: 0,
        isExit: false,
      })),
      ...p.exit_legs.map((leg) => ({
        date: leg.trade_date,
        qty: num(leg.quantity),
        price: null,
        realized: num(leg.realized_pnl),
        isExit: true,
      })),
    ].sort((a, b) => a.date.localeCompare(b.date));

    // Only real, settled closes -- a bar still forming intraday (today,
    // before the close print) comes back with OHLC all null and only
    // volume ticking, and is treated exactly like a day Yahoo has no bar
    // for at all: forward-filled below rather than read as `null - avgCost`
    // coercing to `-avgCost`, which would read as "lost the entire cost
    // basis today."
    const barsByDate = new Map(bars.filter((b) => typeof b.close === "number").map((b) => [b.time, b]));
    if (!p.open_date || barsByDate.size === 0) return [];

    const dirSign = p.direction === "long" ? 1 : -1;
    let qty = 0;
    let avgCost = 0;
    let realizedSoFar = 0;
    let ei = 0;
    let lastOpen: number | null = null;
    let lastClose: number | null = null;
    const out: DayPoint[] = [];

    // Walked one weekday at a time from the entry date through the last
    // known bar, rather than only the calendar days `bars` happens to
    // contain -- Yahoo Finance sometimes has no daily bar at all for a
    // given weekday (seen live: a position opened 2026-09-21, Yahoo's
    // daily bars for that ticker jump straight from 09-21 to 09-23,
    // skipping 09-22 entirely). Iterating `bars` directly would silently
    // drop that day rather than gap-fill it, which read on the chart as a
    // smoothed line quietly skipping over a real day the position was
    // open. A day with no bar of its own forward-fills the last known
    // close (no market update = no assumed price change); before any
    // close is known yet, it marks at the position's own average cost
    // instead (exact, from IBKR, independent of a market data provider
    // having a candle for that day) -- zero unrealized since entry, plus
    // whatever's realized same-day.
    const lastBarDate = [...barsByDate.keys()].sort().at(-1)!;
    let cursor = p.open_date;
    while (cursor <= lastBarDate) {
      while (ei < events.length && events[ei].date <= cursor) {
        const e = events[ei];
        if (e.isExit) {
          realizedSoFar += e.realized;
          qty -= e.qty;
        } else if (e.price !== null) {
          const newQty = qty + e.qty;
          avgCost = newQty > 0 ? (avgCost * qty + e.price * e.qty) / newQty : e.price;
          qty = newQty;
        }
        ei += 1;
      }
      const bar = barsByDate.get(cursor);
      if (bar) {
        lastOpen = bar.open;
        lastClose = bar.close;
      }
      if (!isWeekend(cursor)) {
        const close = lastClose ?? avgCost;
        const open = lastOpen ?? avgCost;
        out.push({
          date: cursor,
          value: realizedSoFar + (close - avgCost) * qty * dirSign,
          open,
          close,
        });
      }
      cursor = addOneDay(cursor);
    }
    return out;
  }

  // Every open position's own day-by-day series, kept per-row (rather than
  // summed right away) so the Potential P&L panel can also chart one
  // position at a time or normalize them onto a shared axis -- see
  // PotentialPnlPanel.svelte.
  const positionSeries = $derived.by((): PositionSeries[] =>
    rows
      .map((row) => {
        const bars = historyBars.get(row.p.symbol);
        return bars ? { row, series: potentialPnlSeries(row.p, bars) } : null;
      })
      .filter((p): p is PositionSeries => p !== null && p.series.length > 0),
  );

  // Union of every position's own series, forward-filled per symbol so a
  // day one symbol didn't trade on (or hasn't opened as of yet) still
  // contributes its last-known value rather than a gap in the sum.
  const combinedSeries = $derived.by((): CumulativePoint[] => {
    const perPosition = positionSeries.map((p) => p.series);
    if (perPosition.length === 0) return [];

    const dateSet = new Set<string>();
    for (const series of perPosition) for (const pt of series) dateSet.add(pt.date);
    const dates = [...dateSet].sort();

    const pointers = perPosition.map(() => 0);
    const lastVals = perPosition.map(() => 0);
    return dates.map((date) => {
      let sum = 0;
      perPosition.forEach((series, i) => {
        while (pointers[i] < series.length && series[pointers[i]].date <= date) {
          lastVals[i] = series[pointers[i]].value;
          pointers[i] += 1;
        }
        sum += lastVals[i];
      });
      return { date, realized_pnl: "0", cumulative: String(sum), trade_count: 0 };
    });
  });
</script>

<svelte:head><title>Open Positions · IBKR Realized P&L</title></svelte:head>

<div class="page">
  <PageHeader
    eyebrow="Round-trip P&amp;L · Flex statement"
    title="Open Positions"
    sticky
    onRefresh={handleRefresh}
    {refreshing}
  >
    {#snippet right()}
      {#if yearOptions.length > 1}
        <SegToggle label="From year" options={yearOptions} active={effectiveFromYear} onChange={(v) => (fromYear = v)} />
      {/if}
    {/snippet}
  </PageHeader>
  <div class="excl-note">
    Showing Open (Full) and Open (Partial){effectiveFromYear === "all"
      ? ""
      : ` from ${effectiveFromYear} onward`} only · {carryInExcluded} carry-in position{carryInExcluded === 1
      ? ""
      : "s"} excluded (entry price/date unknown for those, so cost basis and unrealized P&amp;L can't be computed)
    {#if cashExcluded > 0}
      · {cashExcluded} cash balance{cashExcluded === 1 ? "" : "s"} excluded (no market price to mark against)
    {/if}
    {#if hiddenByFromYear > 0}
      <span class="year-badge"
        >{hiddenByFromYear} pre-{effectiveFromYear} position{hiddenByFromYear === 1 ? "" : "s"} hidden</span
      >
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
        {totalPartialRealized}
        {totalCost}
        openCount={rows.length}
        {fullCount}
        {partialCount}
        {carryInExcluded}
        {currency}
      />
      <div class="gap"></div>
      {#if positionSeries.length > 0}
        <PotentialPnlPanel positions={positionSeries} {combinedSeries} {currency} />
        <div class="gap"></div>
      {/if}
      <OpenPositionCountPanel positions={yearFilteredPositions} />
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
  .year-badge {
    display: inline-block;
    font-size: var(--text-2xs);
    font-weight: var(--weight-bold);
    letter-spacing: 0.04em;
    padding: 2px 7px;
    border-radius: var(--radius-pill);
    background: var(--amber-bg);
    color: var(--amber);
    margin-left: 6px;
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
