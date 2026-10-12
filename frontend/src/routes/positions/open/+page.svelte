<script lang="ts">
  /**
   * Currently-open holdings -- Open (Full) and Open (Partial) -- plus,
   * when "Include realized" is on, every closed position folded in back
   * to the earliest still-open position in the selected from-year (see
   * boundaryDate below). Carry-in positions are excluded outright (their
   * entry price and date are unknown by definition, so cost basis and
   * unrealized P&L can't be computed for them). Forces period="all" on
   * entry so a position opened in an earlier year than whatever's
   * selected elsewhere doesn't silently disappear from a page whose whole
   * point is "what am I holding right now."
   */
  import { onMount } from "svelte";
  import { browser } from "$app/environment";
  import { afterNavigate, goto } from "$app/navigation";
  import { page } from "$app/state";
  import PageHeader from "$lib/components/PageHeader.svelte";
  import SkeletonCard from "$lib/components/SkeletonCard.svelte";
  import AlertBar from "$lib/components/AlertBar.svelte";
  import SegToggle from "$lib/components/SegToggle.svelte";
  import Switch from "$lib/components/Switch.svelte";
  import StatusBadges from "$lib/components/StatusBadges.svelte";
  import PotentialPnlPanel from "$lib/components/PotentialPnlPanel.svelte";
  import type { PositionSeries } from "$lib/components/PotentialPnlPanel.svelte";
  import OpenPositionsSummary from "$lib/components/OpenPositionsSummary.svelte";
  import PositionExposurePanel from "$lib/components/PositionExposurePanel.svelte";
  import OpenPositionsList from "$lib/components/OpenPositionsList.svelte";
  import OpenPositionCountPanel from "$lib/components/OpenPositionCountPanel.svelte";
  import type { OpenPositionsRow } from "$lib/components/OpenPositionsList.svelte";
  import TotalPnlHero from "$lib/components/TotalPnlHero.svelte";
  import ClosedPositionsList from "$lib/components/ClosedPositionsList.svelte";
  import type { ClosedPositionsRow } from "$lib/components/ClosedPositionsList.svelte";
  import CombinedPositionsList from "$lib/components/CombinedPositionsList.svelte";
  import { api, type CumulativePoint, type OHLCVBar, type Position } from "$lib/api";
  import { daysSince, fmtDayYear, num, parseISODay } from "$lib/format";
  import {
    positions,
    positionsLoading,
    positionsError,
    refreshPositions,
    setPeriod,
    posIncludeRealized,
  } from "$lib/stores";

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

  // Separate (today's two stacked tables) vs Combined (one table, entry
  // date ascending, merging open + closed rows) -- only meaningful once
  // "Include realized" has actually produced closed rows to combine with.
  let tableView = $state<"separate" | "combined">("separate");

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
      await Promise.all([refreshPositions(), refreshMarketData()]);
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
  // "current price" the table itself uses. Same OHLCV endpoint the detail
  // page's own chart already uses -- now cached 60s server-side (see
  // market_data.py) so this page's own polling below doesn't multiply into
  // real Yahoo Finance load per browser tab.
  let historyBars = $state<Map<string, OHLCVBar[]>>(new Map());
  let historyFailed = $state<Set<string>>(new Set());
  let marketFetchedAt = $state<string | null>(null);

  // Deliberately not $state -- this exists only to stop fetchOneSymbol from
  // firing a duplicate request for a symbol that's already in flight; it
  // shouldn't itself be a reason for the effect below to re-run. Without
  // this guard, each symbol's fetch resolving mutates historyBars, which
  // re-triggers the effect, which recomputes "wanted" and still includes
  // every symbol that hasn't resolved *yet* -- spawning a new overlapping
  // fetch loop on top of the one still running, cascading into several
  // duplicate requests for whichever symbol happens to resolve last.
  const pendingSymbols = new Set<string>();

  async function fetchOneSymbol(symbol: string, lookbackDays: number): Promise<void> {
    if (pendingSymbols.has(symbol)) return;
    pendingSymbols.add(symbol);
    try {
      const res = await api.marketDataOhlcv(symbol, lookbackDays);
      if (res.ok && res.bars.length) {
        historyBars = new Map(historyBars).set(symbol, res.bars);
        if (historyFailed.has(symbol)) {
          const next = new Set(historyFailed);
          next.delete(symbol);
          historyFailed = next;
        }
        marketFetchedAt = new Date().toISOString();
      } else {
        historyFailed = new Set(historyFailed).add(symbol);
      }
    } catch {
      historyFailed = new Set(historyFailed).add(symbol);
    } finally {
      pendingSymbols.delete(symbol);
    }
  }

  // The deepest lookback any position sharing a symbol actually needs --
  // historyBars is keyed by symbol alone, so if e.g. a closed PURRn position
  // from three weeks ago and a currently-open PURRn opened yesterday both
  // fetched under their own, different lookbackDays, whichever fetched
  // second would just reuse the first's (possibly too-shallow) bars rather
  // than fetching its own. Fetching once per symbol at the widest window
  // any of its positions need avoids that -- extra leading history is
  // harmless, since potentialPnlSeries only walks forward from each
  // position's own open_date anyway.
  function maxLookbackPerSymbol(positionsList: Position[]): Map<string, number> {
    const result = new Map<string, number>();
    for (const p of positionsList) {
      if (!p.open_date) continue;
      const lookback = daysSince(p.open_date) + 5;
      const existing = result.get(p.symbol);
      if (existing === undefined || lookback > existing) result.set(p.symbol, lookback);
    }
    return result;
  }

  $effect(() => {
    // Closed positions' bars are only needed once "Include realized" is on
    // -- their value never changes once fetched (fully closed = no more
    // mark-to-market, no need for the periodic refresh below to touch them).
    const relevant = $posIncludeRealized ? [...yearFilteredPositions, ...closedInWindow] : yearFilteredPositions;
    const wanted = [...maxLookbackPerSymbol(relevant)]
      .filter(([symbol]) => !historyBars.has(symbol) && !historyFailed.has(symbol) && !pendingSymbols.has(symbol))
      .map(([symbol, lookbackDays]) => ({ symbol, lookbackDays }));
    if (wanted.length === 0) return;
    (async () => {
      for (const { symbol, lookbackDays } of wanted) {
        await fetchOneSymbol(symbol, lookbackDays);
      }
    })();
  });

  // Re-fetches every symbol currently on the page -- not just newly-seen
  // ones, unlike the effect above -- so Current Price / Unrealized P&L
  // don't sit frozen at whatever they were on load for the length of a
  // session. Open Positions is the only page that polls market data at
  // all; it's the only one where a live-ish current price actually
  // matters. Fixed at 5 minutes rather than user-configurable -- fast
  // enough to matter, slow enough to stay well inside what an unofficial
  // Yahoo Finance API can be trusted to absorb (see market_data.py's
  // cache, which this still benefits from if other tabs/pages poll too).
  const MARKET_POLL_SEC = 5 * 60;
  let marketSecondsLeft = $state(MARKET_POLL_SEC);
  let marketRefreshing = $state(false);

  async function refreshMarketData(): Promise<void> {
    marketRefreshing = true;
    try {
      for (const [symbol, lookbackDays] of maxLookbackPerSymbol(yearFilteredPositions)) {
        await fetchOneSymbol(symbol, lookbackDays);
      }
    } finally {
      marketRefreshing = false;
      marketSecondsLeft = MARKET_POLL_SEC;
    }
  }

  onMount(() => {
    const id = setInterval(() => {
      if (marketSecondsLeft > 0) marketSecondsLeft -= 1;
      if (marketSecondsLeft === 0) refreshMarketData();
    }, 1000);
    return () => clearInterval(id);
  });

  const marketCountdownLabel = $derived.by(() => {
    const m = Math.floor(marketSecondsLeft / 60);
    const s = marketSecondsLeft % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  });
  const marketProgressPct = $derived((marketSecondsLeft / MARKET_POLL_SEC) * 100);

  function toRow(p: Position): OpenPositionsRow {
    // For an open, non-carry-in position the backend already nets exits
    // out of quantity (src/ibkr_pnl/positions.py: entry_total - exit_total)
    // -- it's the remaining size, not the original entry size, so it's used
    // as-is rather than subtracting exit_legs again.
    const qtyOpen = num(p.quantity);
    // Original size = what's left + everything already sold off. Rounded
    // so fractional quantities don't pick up float noise from the sum. A
    // carry-in's true original size is unknown (its opening trade is
    // outside the fetched range), so it gets neither figure.
    const qtySold = p.exit_legs.reduce((sum, l) => sum + Math.abs(num(l.quantity)), 0);
    const qtyInitial = p.is_carry_in ? null : Number((qtyOpen + qtySold).toFixed(6));
    const pctSold = qtyInitial === null ? null : qtyInitial > 0 ? (qtySold / qtyInitial) * 100 : 0;
    const entryPrice = num(p.entry_price);
    const costBasis = qtyOpen * entryPrice;
    const current = historyBars.get(p.symbol)?.at(-1)?.close ?? null;
    const unrealized =
      current === null ? null : (p.direction === "long" ? current - entryPrice : entryPrice - current) * qtyOpen;
    return {
      p,
      status: p.exit_count > 0 ? "partial" : "full",
      qtyOpen,
      qtyInitial,
      pctSold,
      entryPrice,
      costBasis,
      current,
      unrealized,
      interim: p.exit_count > 0 ? num(p.realized_pnl) : null,
      daysHeld: p.open_date ? daysSince(p.open_date) : null,
    };
  }

  // Entry date ascending by default (oldest open position first), open_time
  // as a same-day tiebreaker -- same ordering key as boundaryPosition below.
  const rows = $derived(
    [...yearFilteredPositions]
      .sort((a, b) => ((a.open_date ?? "") + a.open_time).localeCompare((b.open_date ?? "") + b.open_time))
      .map(toRow),
  );
  const totalUnrealized = $derived(rows.reduce((sum, r) => sum + (r.unrealized ?? 0), 0));
  const totalPartialRealized = $derived(rows.reduce((sum, r) => sum + (r.interim ?? 0), 0));
  const totalCost = $derived(rows.reduce((sum, r) => sum + r.costBasis, 0));
  const fullCount = $derived(rows.filter((r) => r.status === "full").length);
  const partialCount = $derived(rows.filter((r) => r.status === "partial").length);

  // -- Realized P&L, folded in when "Include realized" is on --------------
  //
  // Every fully closed, non-carry-in position -- the same $positions feed
  // the open rows above come from, just the opposite is_open branch.
  const closedPositions = $derived(($positions?.positions ?? []).filter((p) => !p.is_open && !p.is_carry_in));

  // The window's boundary: the earliest still-OPEN position in the
  // selected from-year, by open_date then open_time to break a same-day
  // tie (see e.g. two positions opened the same morning). yearFilteredPositions
  // is already every open position from effectiveFromYear onward, so its
  // own earliest entry is exactly "the first position from that year I'm
  // still holding" -- not the first position of any status, since a
  // closed one from earlier in the year shouldn't move the anchor.
  const boundaryPosition = $derived(
    yearFilteredPositions.length === 0
      ? null
      : yearFilteredPositions.reduce((earliest, p) =>
          (p.open_date ?? "") + p.open_time < (earliest.open_date ?? "") + earliest.open_time ? p : earliest,
        ),
  );
  const boundaryDate = $derived(boundaryPosition?.open_date ?? null);

  // Closed positions count toward the window by their own entry date,
  // exactly like the open positions above -- never by when they happened
  // to realize. A position that closed today but opened before the
  // boundary won't show up until an earlier from-year is selected.
  const closedInWindow = $derived(
    boundaryDate === null ? [] : closedPositions.filter((p) => p.open_date && p.open_date >= boundaryDate),
  );

  function toClosedRow(p: Position): ClosedPositionsRow {
    const daysHeld =
      p.open_date && p.exit_date
        ? Math.round((parseISODay(p.exit_date).getTime() - parseISODay(p.open_date).getTime()) / 86_400_000)
        : null;
    // A fully closed position's quantity is its original entry size (exit
    // total == entry total by definition, unlike an open position's netted
    // remainder -- see toRow's comment above) -- so it's used as-is for
    // cost basis, the same qty * entryPrice as an open row.
    const qty = num(p.quantity);
    const entryPrice = num(p.entry_price);
    return { p, realized: num(p.realized_pnl), daysHeld, entryPrice, qty, costBasis: qty * entryPrice };
  }
  const closedRows = $derived(closedInWindow.map(toClosedRow));
  const realizedClosedTotal = $derived(closedRows.reduce((sum, r) => sum + r.realized, 0));
  const totalPnl = $derived(totalUnrealized + totalPartialRealized + realizedClosedTotal);

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
  // PotentialPnlPanel.svelte. Stays open-only (never includes closed
  // positions) -- it feeds the By position/Normalized tabs and the
  // per-position card grid, which are about current holdings, not history.
  const positionSeries = $derived.by((): PositionSeries[] =>
    rows
      .map((row) => {
        const bars = historyBars.get(row.p.symbol);
        return bars ? { row, series: potentialPnlSeries(row.p, bars) } : null;
      })
      .filter((p): p is PositionSeries => p !== null && p.series.length > 0),
  );

  // Closed positions' own day-by-day series, same calculation as open ones
  // -- once a position's fully exited, potentialPnlSeries naturally
  // flattens at its final realized value (qty drops to 0, so the
  // mark-to-market term zeroes out) rather than needing separate handling.
  // Only computed once "Include realized" is on, matching TotalPnlHero and
  // OpenPositionsSummary's own gating. Not wrapped as PositionSeries (no
  // OpenPositionsRow to put in `row`) since this only ever feeds the
  // combined sum below, never the by-position views.
  const closedSeriesList = $derived.by((): DayPoint[][] =>
    $posIncludeRealized
      ? closedInWindow
          .map((p) => {
            const bars = historyBars.get(p.symbol);
            return bars ? potentialPnlSeries(p, bars) : [];
          })
          .filter((series) => series.length > 0)
      : [],
  );

  // Union of every open position's series, plus every closed position's
  // when included, forward-filled per symbol so a day one symbol didn't
  // trade on (or hasn't opened as of yet) still contributes its last-known
  // value rather than a gap in the sum.
  const combinedSeries = $derived.by((): CumulativePoint[] => {
    const perPosition = [...positionSeries.map((p) => p.series), ...closedSeriesList];
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
      {#if $positions}
        <StatusBadges flexOk={$positions.flex_ok} flexFetchedAt={$positions.flex_fetched_at} {marketFetchedAt} />
      {/if}
      <Switch
        checked={$posIncludeRealized}
        label="Include realized"
        ariaLabel="Include realized P&amp;L since the selected year"
        onChange={(v) => posIncludeRealized.set(v)}
      />
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
    {#if $posIncludeRealized && boundaryDate}
      <div class="realized-note">
        Plus {closedRows.length} closed position{closedRows.length === 1 ? "" : "s"} opened on or after {fmtDayYear(
          boundaryDate,
        )} ({boundaryPosition?.symbol}, the first position {effectiveFromYear === "all"
          ? "on record"
          : `from ${effectiveFromYear}`} still open) &middot; closed positions count by entry date, same as the filter
        above.
      </div>
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
      <div class="market-poll-row">
        <span class="market-poll-label">Current prices auto-refresh every 5 min &middot; this page only</span>
        <span class="market-poll-countdown">{marketRefreshing ? "Refreshing…" : `Next refresh in ${marketCountdownLabel}`}</span>
      </div>
      <div class="market-poll-bar">
        <div class="market-poll-fill" style="width: {marketRefreshing ? 100 : marketProgressPct}%"></div>
      </div>
      <div class="gap"></div>
      {#if $posIncludeRealized}
        <TotalPnlHero
          total={totalPnl}
          unrealized={totalUnrealized}
          partial={totalPartialRealized}
          realizedClosed={realizedClosedTotal}
          closedCount={closedRows.length}
          {currency}
        />
        <div class="gap"></div>
      {/if}
      <OpenPositionsSummary
        {totalUnrealized}
        {totalPartialRealized}
        {totalCost}
        openCount={rows.length}
        {fullCount}
        {partialCount}
        {carryInExcluded}
        closedCount={$posIncludeRealized ? closedRows.length : 0}
        {realizedClosedTotal}
        closedSinceDate={boundaryDate}
        {currency}
      />
      <div class="gap"></div>
      {#if positionSeries.length > 0}
        <PotentialPnlPanel positions={positionSeries} {combinedSeries} includesClosed={$posIncludeRealized} {currency} />
        <div class="gap"></div>
      {/if}
      <OpenPositionCountPanel positions={yearFilteredPositions} showRangeSelector />
      <div class="gap"></div>
      <PositionExposurePanel {rows} {currency} />
      <div class="gap"></div>
      {#if $posIncludeRealized && closedRows.length > 0}
        <div class="table-view-row">
          <SegToggle
            label="Table view"
            options={[
              { label: "Separate", value: "separate" },
              { label: "Combined", value: "combined" },
            ]}
            active={tableView}
            onChange={(v) => (tableView = v as "separate" | "combined")}
          />
        </div>
        <div class="gap"></div>
        {#if tableView === "combined"}
          <CombinedPositionsList openRows={rows} {closedRows} {currency} />
        {:else}
          <ClosedPositionsList rows={closedRows} {currency} />
          <div class="gap"></div>
          <OpenPositionsList {rows} {currency} />
        {/if}
      {:else}
        <OpenPositionsList {rows} {currency} />
      {/if}
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
  .table-view-row {
    display: flex;
    justify-content: flex-end;
  }
  .excl-note {
    font-size: var(--text-xs);
    color: var(--dim-45);
    margin-top: -8px;
    margin-bottom: 16px;
  }
  .realized-note {
    font-size: var(--text-2xs);
    color: var(--dim-45);
    margin-top: 6px;
    padding-left: 14px;
    border-left: 2px solid var(--border-08);
    line-height: 1.6;
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
  .market-poll-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .market-poll-label {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--dim-55);
  }
  .market-poll-countdown {
    font-size: var(--text-xs);
    font-weight: var(--weight-bold);
    font-variant-numeric: tabular-nums;
    color: var(--accent);
    white-space: nowrap;
  }
  .market-poll-bar {
    margin-top: 6px;
    height: 3px;
    border-radius: var(--radius-pill);
    background: var(--accent-bg);
    overflow: hidden;
  }
  .market-poll-fill {
    height: 100%;
    border-radius: var(--radius-pill);
    background: var(--accent);
    transition: width 1s linear;
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
