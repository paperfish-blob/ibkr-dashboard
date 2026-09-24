<script lang="ts">
  /**
   * Same three panels as the main Overview page (headline, cumulative chart,
   * monthly panel + QQQ benchmark), but built from the Positions feed
   * instead of the daily realized-P&L series -- bucketed by either a
   * position's exit date or its entry date, via the same posGroupBy store
   * the Positions list page's table already groups its day bands by.
   *
   * Scoped to closed positions only (a still-open position has nothing
   * realized to bucket yet), same as PositionHeadlineStat's total.
   */
  import { onMount } from "svelte";
  import { browser } from "$app/environment";
  import { afterNavigate, goto } from "$app/navigation";
  import { page } from "$app/state";
  import PageHeader from "$lib/components/PageHeader.svelte";
  import SegToggle from "$lib/components/SegToggle.svelte";
  import PositionHeadlineStat from "$lib/components/PositionHeadlineStat.svelte";
  import CumulativeChart from "$lib/components/CumulativeChart.svelte";
  import OpenPositionCountPanel from "$lib/components/OpenPositionCountPanel.svelte";
  import MonthlyPnL from "$lib/components/MonthlyPnL.svelte";
  import IndexBenchmark from "$lib/components/IndexBenchmark.svelte";
  import TopPositions from "$lib/components/TopPositions.svelte";
  import SkeletonCard from "$lib/components/SkeletonCard.svelte";
  import AlertBar from "$lib/components/AlertBar.svelte";
  import PeriodPicker from "$lib/components/PeriodPicker.svelte";
  import { api, type OHLCVBar, type CumulativePoint, type Position } from "$lib/api";
  import { num } from "$lib/format";
  import {
    positions,
    positionsLoading,
    positionsError,
    refreshPositions,
    setPeriod,
    posGroupBy,
    type PosGroupBy,
    monthlyPnlView,
    type MonthlyPnlView,
  } from "$lib/stores";

  const POLL_MS = 30_000;
  let refreshing = $state(false);

  // The top-nav "Positions Overview" link carries this to land on a clean
  // view -- same idea as the Positions page's own nav-reset. Handled both
  // at mount and via afterNavigate: a click while already on this page is
  // a same-route navigation, which SvelteKit serves by reusing this
  // component instance rather than remounting it, so a plain one-time
  // check would miss it.
  function handleReset(url: URL) {
    if (url.searchParams.get("reset") !== "1") return;
    // The current year, not "All" -- this page's own charts (cumulative
    // P&L, the Monthly panel) are dense enough over a full multi-year
    // history that starting scoped to what's actually still in progress
    // reads better than starting on everything at once.
    setPeriod(String(new Date().getFullYear()));
    // Entry date, not exit -- unlike the Positions page (which defaults to
    // exit, matching money actually realized that day), this page's own
    // chart/table already reads better bucketed by when a position was
    // opened, so that's the view arriving here should always start on.
    posGroupBy.set("entry");
    monthlyPnlView.set("charts");
    // Nothing else rewrites this page's URL, so `reset=1` would otherwise
    // sit in the address bar forever -- unlike Transactions/Positions,
    // which already have a store->URL sync effect that naturally drops it.
    goto("/positions/overview", { replaceState: true, noScroll: true, keepFocus: true });
  }
  if (browser) handleReset(page.url);
  afterNavigate(({ to }) => {
    if (to) handleReset(to.url);
  });

  const GROUP_BY = [
    { label: "Entry date", value: "entry" },
    { label: "Exit date", value: "exit" },
  ];

  let hoveredMonth = $state<string | null>(null);
  let topN = $state<5 | 10 | 20>(10);

  const IDX_LOOKBACK_MIN_DAYS = 765;
  let qqqBars = $state<OHLCVBar[]>([]);
  let qqqLookbackDays = $state(IDX_LOOKBACK_MIN_DAYS);

  const coverage = $derived.by(() => {
    const years = $positions?.years_covered ?? [];
    if ($positions?.period !== "all" || years.length <= 1) return null;
    return `Covering ${years.slice().sort().join(", ")} — add more on the History page.`;
  });

  const currency = $derived($positions?.positions[0]?.currency ?? "USD");

  // Closed positions only, bucketed by exit_date or open_date depending on
  // groupBy, shaped exactly like PnLResponse's own daily series so
  // CumulativeChart and MonthlyPnL need no changes to consume it -- a
  // position without the relevant date (a still-open position has no
  // exit_date; a carry-in has no open_date) is dropped rather than guessed.
  function buildSeries(all: Position[], groupBy: PosGroupBy): CumulativePoint[] {
    const dateOf = groupBy === "exit" ? (p: Position) => p.exit_date : (p: Position) => p.open_date;
    const buckets = new Map<string, { pnl: number; count: number }>();
    for (const p of all) {
      if (p.is_open) continue;
      const d = dateOf(p);
      if (!d) continue;
      const b = buckets.get(d) ?? { pnl: 0, count: 0 };
      b.pnl += num(p.realized_pnl);
      b.count += 1;
      buckets.set(d, b);
    }
    let cumulative = 0;
    return [...buckets.keys()].sort().map((date) => {
      const b = buckets.get(date)!;
      cumulative += b.pnl;
      return {
        date,
        realized_pnl: String(b.pnl),
        cumulative: String(cumulative),
        trade_count: b.count,
      };
    });
  }

  const series = $derived($positions ? buildSeries($positions.positions, $posGroupBy) : []);

  // "YYYY-MM" -> wins/total among that month's closed positions, under the
  // same date/groupBy rules as buildSeries above (dropped rather than
  // guessed when the relevant date is unknown) -- kept separate from
  // `series` since win rate isn't a sum like P&L or a count, it needs the
  // raw win/total pair to combine into an accurate overall rate later.
  function buildWinRates(all: Position[], groupBy: PosGroupBy): Map<string, { wins: number; total: number }> {
    const dateOf = groupBy === "exit" ? (p: Position) => p.exit_date : (p: Position) => p.open_date;
    const rates = new Map<string, { wins: number; total: number }>();
    for (const p of all) {
      if (p.is_open) continue;
      const d = dateOf(p);
      if (!d) continue;
      const key = d.slice(0, 7);
      const b = rates.get(key) ?? { wins: 0, total: 0 };
      b.total += 1;
      if (num(p.realized_pnl) > 0) b.wins += 1;
      rates.set(key, b);
    }
    return rates;
  }

  const winRates = $derived($positions ? buildWinRates($positions.positions, $posGroupBy) : new Map());

  // "YYYY-MM" -> aggregate win/loss dollars among that month's closed
  // positions, under the same date/groupBy rules as buildWinRates above --
  // kept as sums+counts rather than a pre-divided ratio so the panel can
  // compute both the per-month and the overall (weighted, not averaged)
  // avg-win/avg-loss ratio from the same numbers.
  function buildRRStats(
    all: Position[],
    groupBy: PosGroupBy,
  ): Map<string, { winSum: number; winCount: number; lossSum: number; lossCount: number }> {
    const dateOf = groupBy === "exit" ? (p: Position) => p.exit_date : (p: Position) => p.open_date;
    const stats = new Map<string, { winSum: number; winCount: number; lossSum: number; lossCount: number }>();
    for (const p of all) {
      if (p.is_open) continue;
      const d = dateOf(p);
      if (!d) continue;
      const key = d.slice(0, 7);
      const b = stats.get(key) ?? { winSum: 0, winCount: 0, lossSum: 0, lossCount: 0 };
      const pnl = num(p.realized_pnl);
      if (pnl > 0) {
        b.winSum += pnl;
        b.winCount += 1;
      } else if (pnl < 0) {
        b.lossSum += -pnl;
        b.lossCount += 1;
      }
      stats.set(key, b);
    }
    return stats;
  }

  const rrStats = $derived($positions ? buildRRStats($positions.positions, $posGroupBy) : new Map());

  // "YYYY-MM" -> the longest run of consecutive winning positions and the
  // longest run of consecutive losing positions within that month, walked
  // in the order those positions actually closed (or opened, under
  // "entry") -- a flat ($0) position breaks both streaks rather than
  // extending either, same as it counting toward neither win nor loss in
  // buildWinRates above. Same date field as every other monthly build here,
  // but grouped into per-month position lists first since a streak (unlike
  // a sum or a count) depends on order, not just membership.
  function buildStreaks(
    all: Position[],
    groupBy: PosGroupBy,
  ): Map<string, { maxWinStreak: number; maxLossStreak: number }> {
    const dateOf = groupBy === "exit" ? (p: Position) => p.exit_date : (p: Position) => p.open_date;
    const timeOf =
      groupBy === "exit"
        ? (p: Position) => p.exit_legs[p.exit_legs.length - 1]?.trade_time ?? ""
        : (p: Position) => p.open_time;

    const byMonth = new Map<string, Position[]>();
    for (const p of all) {
      if (p.is_open) continue;
      const d = dateOf(p);
      if (!d) continue;
      const key = d.slice(0, 7);
      const list = byMonth.get(key) ?? [];
      list.push(p);
      byMonth.set(key, list);
    }

    const result = new Map<string, { maxWinStreak: number; maxLossStreak: number }>();
    for (const [key, monthPositions] of byMonth) {
      const sorted = monthPositions.slice().sort((a, b) => {
        const da = dateOf(a)!;
        const db = dateOf(b)!;
        if (da !== db) return da < db ? -1 : 1;
        const ta = timeOf(a);
        const tb = timeOf(b);
        return ta < tb ? -1 : ta > tb ? 1 : 0;
      });
      let win = 0;
      let loss = 0;
      let maxWinStreak = 0;
      let maxLossStreak = 0;
      for (const p of sorted) {
        const pnl = num(p.realized_pnl);
        if (pnl > 0) {
          win += 1;
          loss = 0;
          maxWinStreak = Math.max(maxWinStreak, win);
        } else if (pnl < 0) {
          loss += 1;
          win = 0;
          maxLossStreak = Math.max(maxLossStreak, loss);
        } else {
          win = 0;
          loss = 0;
        }
      }
      result.set(key, { maxWinStreak, maxLossStreak });
    }
    return result;
  }

  const streaks = $derived($positions ? buildStreaks($positions.positions, $posGroupBy) : new Map());

  // Same reasoning as the main Overview page: hovering a month older than
  // what's been fetched has no bars for the QQQ chart to zoom to, so the
  // window grows to cover this page's own earliest bucketed date (which
  // shifts with posGroupBy) once it's known.
  $effect(() => {
    const earliest = series[0]?.date;
    if (!earliest) return;
    const daysSince = Math.ceil((Date.now() - new Date(earliest).getTime()) / 86_400_000);
    const needed = daysSince + 400;
    if (needed > qqqLookbackDays) qqqLookbackDays = needed;
  });

  let qqqFetchId = 0;
  $effect(() => {
    const lookback = qqqLookbackDays;
    const id = ++qqqFetchId;
    api
      .marketDataOhlcv("QQQ", lookback)
      .then((r) => {
        if (id === qqqFetchId && r.ok) qqqBars = r.bars;
      })
      .catch(() => {});
  });

  const monthCaption = $derived(
    `Gross, before commission · closed positions only, bucketed by ${$posGroupBy} date`,
  );
  const cumCaption = $derived(
    `Gross, before commission · one point per day a position ${$posGroupBy === "exit" ? "closed" : "opened"} · closed positions only, bucketed by ${$posGroupBy} date`,
  );

  // A clicked month drills into the Positions page instead of Transactions --
  // these months are round-trips, not executions -- filtered to that month
  // under the same groupBy dimension its own bucket was built from, and to
  // closed positions only, matching what's actually pictured here. As a
  // date range rather than Positions' old separate month filter, so there's
  // exactly one "which dates" mechanism to land on over there.
  function positionsMonthLink(key: string): string {
    const [y, m] = key.split("-").map(Number);
    const lastDay = new Date(y, m, 0).getDate();
    const dateFrom = `${key}-01`;
    const dateTo = `${key}-${String(lastDay).padStart(2, "0")}`;
    return `/positions?year=${y}&filter=closed&dateFrom=${dateFrom}&dateTo=${dateTo}&groupBy=${$posGroupBy}`;
  }

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

<svelte:head><title>Positions Overview · IBKR Realized P&L</title></svelte:head>

<div class="page">
  <PageHeader
    eyebrow="Round-trip P&amp;L · Flex statement"
    title="Positions Overview"
    sticky
    onRefresh={handleRefresh}
    {refreshing}
  >
    {#snippet right()}
      <SegToggle
        label="Group by"
        options={GROUP_BY}
        active={$posGroupBy}
        onChange={(v) => posGroupBy.set(v as PosGroupBy)}
      />
      <PeriodPicker />
    {/snippet}
  </PageHeader>

  <AlertBar messages={[$positionsError, $positions?.flex_error]} />

  {#if coverage}
    <div class="coverage">{coverage}</div>
  {/if}

  {#if $positionsLoading && !$positions}
    <SkeletonCard height={168} rows={2} />
    <div class="gap"></div>
    <SkeletonCard height={360} rows={4} />
  {:else if $positions}
    <PositionHeadlineStat data={$positions} groupBy={$posGroupBy} {currency} />
    <div class="gap"></div>
    <CumulativeChart {series} {currency} caption={cumCaption} />
    <div class="gap"></div>
    <OpenPositionCountPanel positions={$positions.positions} showRangeSelector />
    <div class="gap"></div>
    <div class="side-grid">
      <MonthlyPnL
        {series}
        {currency}
        unit="position"
        caption={monthCaption}
        monthLink={positionsMonthLink}
        {winRates}
        {rrStats}
        {streaks}
        onHoverMonth={(m) => (hoveredMonth = m)}
        view={$monthlyPnlView}
        onViewChange={(v: MonthlyPnlView) => monthlyPnlView.set(v)}
      />
      <IndexBenchmark symbol="QQQ" name="Nasdaq 100" bars={qqqBars} highlightMonth={hoveredMonth} />
    </div>
    <div class="gap"></div>
    <div class="side-grid">
      <TopPositions positions={$positions.positions} {currency} mode="win" {topN} onTopNChange={(n) => (topN = n)} />
      <TopPositions
        positions={$positions.positions}
        {currency}
        mode="loss"
        {topN}
        onTopNChange={(n) => (topN = n)}
        showControl={false}
      />
    </div>
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
  .gap {
    height: 24px;
  }
  .side-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 18px;
    align-items: start;
  }
  @media (max-width: 900px) {
    .side-grid {
      grid-template-columns: 1fr;
    }
  }
  .coverage {
    font-size: var(--text-xs);
    color: var(--dim-55);
    margin-bottom: 12px;
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
