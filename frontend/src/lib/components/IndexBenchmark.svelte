<script lang="ts">
  /**
   * A benchmark index's price chart -- ui-reference's TickerHero, unchanged:
   * same SymbolChart (regime bands on, unlike the position detail page's
   * default), same 1M/3M/6M/1Y/YTD tile row. Meant to sit above MonthlyPnL
   * on the Overview page so the two can be visually compared; `highlightMonth`
   * is threaded straight through to SymbolChart so a month hovered in
   * MonthlyPnL spotlights the same month here too.
   */
  import { fmtPriceLike, num } from "$lib/format";
  import type { OHLCVBar } from "$lib/api";
  import { period } from "$lib/stores";
  import SymbolChart from "./SymbolChart.svelte";

  interface Props {
    symbol: string;
    name: string;
    bars: OHLCVBar[];
    highlightMonth?: string | null;
    /** The page's own date filter, as "YYYY-MM-DD" (either end null for
     *  open). Passing it -- even as {from: null, to: null} -- switches the
     *  panel into range mode: the chart opens on that window with a shaded
     *  band, a "Range" tile (selected by default) shows the index's move
     *  across exactly it, and 1M-YTD are measured back from the window's
     *  end. Left undefined (Overview), none of that applies. */
    range?: { from: string | null; to: string | null };
  }
  let { symbol, name, bars, highlightMonth = null, range }: Props = $props();
  const rangeMode = $derived(range !== undefined);

  // When a specific year is selected in the period picker, every tile
  // (and the chart's own default view, via SymbolChart's own
  // "last bar in history" anchor) shifts to be relative to THAT year
  // instead of today -- "1Y" becomes ~that whole year, "YTD" becomes
  // Jan 1 of that year to its own year-end, and the price shown is that
  // year's own last close, not today's live price. Trims only the end
  // (bars after that year) so everything before it -- prior years, needed
  // for a trailing lookback or MA warmup near the start of the year --
  // stays intact. "All" (or anything not a bare year) is unchanged: bars
  // as fetched, anchored on today, exactly as before. Range mode skips
  // this: its own window decides what the end is, and bars past it stay
  // visible as context around the shaded band.
  const anchoredBars = $derived.by(() => {
    if (rangeMode || !/^\d{4}$/.test($period)) return bars;
    const cutoff = `${$period}-12-31`;
    let idx = -1;
    for (let i = 0; i < bars.length; i++) {
      if (bars[i].time <= cutoff) idx = i;
    }
    return idx === -1 ? bars : bars.slice(0, idx + 1);
  });

  interface Tf {
    k: "RANGE" | "1MO" | "3MO" | "6MO" | "1Y" | "YTD";
    label: string;
    daysBack: number | null; // null for YTD (and RANGE), computed separately
  }
  const TFS: Tf[] = [
    { k: "1MO", label: "1M", daysBack: 21 },
    { k: "3MO", label: "3M", daysBack: 63 },
    { k: "6MO", label: "6M", daysBack: 126 },
    { k: "1Y", label: "1Y", daysBack: 252 },
    { k: "YTD", label: "YTD", daysBack: null },
  ];
  const RANGE_TF: Tf = { k: "RANGE", label: "Range", daysBack: null };
  let activeTf = $state<Tf["k"]>("1Y");

  // Range mode: indexes of the filtered window within anchoredBars. endIdx
  // is the last bar on or before range.to (the last bar overall when it's
  // open-ended); fromIdx the first on or after range.from. In every other
  // mode endIdx is simply the last bar, so the helpers below behave
  // exactly as before.
  const win = $derived.by(() => {
    const b = anchoredBars;
    if (!b.length) return { fromIdx: 0, endIdx: -1 };
    let endIdx = b.length - 1;
    let fromIdx = 0;
    if (rangeMode && range) {
      if (range.to) {
        endIdx = -1;
        for (let i = 0; i < b.length; i++) if (b[i].time <= range.to) endIdx = i;
      }
      if (range.from) {
        const f = b.findIndex((x) => x.time >= range.from!);
        fromIdx = f === -1 ? b.length : f;
      }
    }
    return { fromIdx, endIdx };
  });
  const endIdx = $derived(win.endIdx);

  // Landing on a different filter puts the Range tile back in front.
  $effect(() => {
    if (!rangeMode) return;
    range?.from;
    range?.to;
    activeTf = "RANGE";
  });

  // Trading-day offsets, the same convention the position detail page's own
  // period tiles use -- not calendar days, so weekends/holidays don't skew
  // "1 month" short.
  function pctChangeAt(tradingDaysBack: number): number | null {
    const b = anchoredBars;
    if (b.length < 2 || endIdx < 0) return null;
    const idx = endIdx - tradingDaysBack;
    if (idx < 0) return null;
    const base = b[idx].close;
    if (base === 0) return null;
    return ((b[endIdx].close - base) / base) * 100;
  }
  function ytdStartIdx(): number {
    const b = anchoredBars;
    if (b.length < 2 || endIdx < 0) return -1;
    const lastYear = b[endIdx].time.slice(0, 4);
    return b.findIndex((x) => x.time.slice(0, 4) === lastYear);
  }
  function pctChangeYTD(): number | null {
    const b = anchoredBars;
    const idx = ytdStartIdx();
    if (idx < 0) return null;
    const base = b[idx].close;
    if (base === 0) return null;
    return ((b[endIdx].close - base) / base) * 100;
  }
  // The close just before the window opens, so the first day's own move
  // counts -- or the first bar when the window starts before the data does.
  function pctChangeRange(): number | null {
    const b = anchoredBars;
    if (endIdx < 0 || win.fromIdx > endIdx) return null;
    const base = b[Math.max(0, win.fromIdx - 1)].close;
    if (base === 0) return null;
    return ((b[endIdx].close - base) / base) * 100;
  }
  function tfValue(tf: Tf): number | null {
    if (tf.k === "RANGE") return pctChangeRange();
    return tf.k === "YTD" ? pctChangeYTD() : pctChangeAt(tf.daysBack!);
  }

  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function shortDate(d: string): string {
    const [, m, day] = d.split("-").map(Number);
    return `${MON[m - 1]} ${day}`;
  }
  function tfSub(tf: Tf): string | null {
    if (tf.k !== "RANGE" || endIdx < 0 || win.fromIdx > endIdx) return null;
    return `${shortDate(anchoredBars[win.fromIdx].time)} → ${shortDate(anchoredBars[endIdx].time)}`;
  }

  const tfRows = $derived(
    (rangeMode ? [RANGE_TF, ...TFS] : TFS).map((tf) => ({ tf, value: tfValue(tf), sub: tfSub(tf) })),
  );
  const activeRow = $derived(tfRows.find((r) => r.tf.k === activeTf) ?? tfRows[0]);

  const visibleMonths = $derived.by((): number | undefined => {
    if (rangeMode || !anchoredBars.length) return undefined;
    switch (activeTf) {
      case "1MO":
        return 1;
      case "3MO":
        return 3;
      case "6MO":
        return 6;
      case "1Y":
        return 12;
      case "YTD":
        return new Date(anchoredBars[anchoredBars.length - 1].time).getMonth() + 1;
    }
  });

  // Range mode's own visible window: the filtered range with just enough
  // context either side (a couple of bars, ~4% of its length) for the
  // shaded band's edges to read as edges -- any more and a short filter
  // opens weeks before its own start date -- or a tile's lookback ending
  // just past the window's end.
  const focusRange = $derived.by((): { from: string; to: string } | undefined => {
    const b = anchoredBars;
    if (!rangeMode || endIdx < 0 || !b.length) return undefined;
    if (activeTf === "RANGE") {
      if (win.fromIdx > endIdx) return undefined;
      const pad = Math.max(2, Math.round((endIdx - win.fromIdx) * 0.04));
      return { from: b[Math.max(0, win.fromIdx - pad)].time, to: b[Math.min(b.length - 1, endIdx + pad)].time };
    }
    const back =
      activeTf === "YTD" ? endIdx - ytdStartIdx() : (TFS.find((t) => t.k === activeTf)?.daysBack ?? 252);
    return { from: b[Math.max(0, endIdx - back)].time, to: b[Math.min(b.length - 1, endIdx + 3)].time };
  });

  const bandRange = $derived.by(() => {
    if (!rangeMode || !range || !anchoredBars.length) return null;
    return { from: range.from ?? anchoredBars[0].time, to: range.to ?? anchoredBars[anchoredBars.length - 1].time };
  });

  const lastClose = $derived(endIdx >= 0 ? anchoredBars[endIdx].close : null);
</script>

<div class="panel">
  <div class="idx-body">
    <div class="idx-top">
      <div class="idx-title-row">
        <span class="idx-ticker">{symbol}</span>
        <span class="idx-name">{name}</span>
        {#if lastClose !== null}
          <span class="idx-price">{fmtPriceLike(num(lastClose), "USD", 2)}</span>
        {/if}
      </div>
      <div class="idx-big">
        <div class="idx-big-val {activeRow.value === null ? '' : activeRow.value >= 0 ? 'pos' : 'neg'}">
          {activeRow.value === null ? "—" : `${activeRow.value >= 0 ? "+" : ""}${activeRow.value.toFixed(2)}%`}
        </div>
        <div class="idx-big-sub">{activeRow.tf.label}</div>
      </div>
    </div>

    {#if anchoredBars.length}
      <SymbolChart
        history={anchoredBars}
        height={260}
        {visibleMonths}
        {focusRange}
        {bandRange}
        {highlightMonth}
        regimeBands
        apsPane
        extendedAlerts
      />

      <div class="idx-tfs" class:six={rangeMode}>
        {#each tfRows as { tf, value, sub } (tf.k)}
          <button class="tf" class:active={tf.k === activeTf} onclick={() => (activeTf = tf.k)}>
            <div class="tf-key">{tf.label}</div>
            <div class="tf-val {value === null ? '' : value >= 0 ? 'pos' : 'neg'}">
              {value === null ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`}
            </div>
            {#if sub}<div class="tf-sub">{sub}</div>{/if}
          </button>
        {/each}
      </div>
    {:else}
      <div class="idx-empty">No price history available for {symbol}.</div>
    {/if}
  </div>
</div>

<style>
  .panel {
    background: var(--surface);
    border: 1px solid var(--border-05);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }
  .idx-body {
    padding: 18px 22px 20px;
  }
  .idx-top {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    margin-bottom: 10px;
    gap: 12px;
  }
  .idx-title-row {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
  }
  .idx-ticker {
    font-variant-numeric: tabular-nums;
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
    letter-spacing: 0.01em;
    color: var(--text);
  }
  .idx-name {
    font-size: var(--text-md);
    color: var(--dim-55);
  }
  .idx-price {
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    font-variant-numeric: tabular-nums;
    color: var(--dim-70);
  }
  .idx-big {
    text-align: right;
    flex: none;
  }
  .idx-big-val {
    font-variant-numeric: tabular-nums;
    font-size: var(--text-2xl);
    font-weight: var(--weight-bold);
    letter-spacing: -0.02em;
    color: var(--text);
  }
  .idx-big-val.pos {
    color: var(--up);
  }
  .idx-big-val.neg {
    color: var(--dn);
  }
  .idx-big-sub {
    font-size: var(--text-xs);
    color: var(--dim-55);
  }

  .idx-tfs {
    margin-top: 10px;
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 8px;
  }
  .idx-tfs.six {
    grid-template-columns: 1.25fr repeat(5, 1fr);
  }
  .tf {
    padding: 8px 10px;
    border-radius: var(--radius-md);
    background: var(--surface-02);
    border: 1px solid var(--border-05);
    cursor: pointer;
    font: inherit;
    text-align: left;
    width: 100%;
  }
  .tf:hover:not(.active) {
    background: var(--surface-04);
    border-color: var(--border-12);
  }
  .tf.active {
    background: var(--up-bg);
    border-color: var(--up);
  }
  .tf-key {
    font-size: var(--text-2xs);
    color: var(--dim-55);
    letter-spacing: 0.14em;
    font-weight: var(--weight-semibold);
  }
  .tf-val {
    font-variant-numeric: tabular-nums;
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    margin-top: 2px;
    color: var(--text);
  }
  .tf-sub {
    font-size: 9.5px;
    font-weight: var(--weight-medium);
    color: var(--dim-45);
    margin-top: 1px;
  }
  .tf-val.pos {
    color: var(--up);
  }
  .tf-val.neg {
    color: var(--dn);
  }

  .idx-empty {
    padding: 40px 0;
    text-align: center;
    color: var(--dim-55);
    font-size: var(--text-sm);
  }

  @media (max-width: 640px) {
    .idx-tfs {
      grid-template-columns: repeat(3, 1fr);
    }
    .idx-top {
      flex-direction: column;
      align-items: flex-start;
      gap: 6px;
    }
    .idx-big {
      text-align: left;
    }
  }
</style>
