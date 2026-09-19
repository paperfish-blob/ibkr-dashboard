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
  }
  let { symbol, name, bars, highlightMonth = null }: Props = $props();

  // When a specific year is selected in the period picker, every tile
  // (and the chart's own default view, via SymbolChart's own
  // "last bar in history" anchor) shifts to be relative to THAT year
  // instead of today -- "1Y" becomes ~that whole year, "YTD" becomes
  // Jan 1 of that year to its own year-end, and the price shown is that
  // year's own last close, not today's live price. Trims only the end
  // (bars after that year) so everything before it -- prior years, needed
  // for a trailing lookback or MA warmup near the start of the year --
  // stays intact. "All" (or anything not a bare year) is unchanged: bars
  // as fetched, anchored on today, exactly as before.
  const anchoredBars = $derived.by(() => {
    if (!/^\d{4}$/.test($period)) return bars;
    const cutoff = `${$period}-12-31`;
    let idx = -1;
    for (let i = 0; i < bars.length; i++) {
      if (bars[i].time <= cutoff) idx = i;
    }
    return idx === -1 ? bars : bars.slice(0, idx + 1);
  });

  interface Tf {
    k: "1MO" | "3MO" | "6MO" | "1Y" | "YTD";
    label: string;
    daysBack: number | null; // null for YTD, computed separately
  }
  const TFS: Tf[] = [
    { k: "1MO", label: "1M", daysBack: 21 },
    { k: "3MO", label: "3M", daysBack: 63 },
    { k: "6MO", label: "6M", daysBack: 126 },
    { k: "1Y", label: "1Y", daysBack: 252 },
    { k: "YTD", label: "YTD", daysBack: null },
  ];
  let activeTf = $state<Tf["k"]>("1Y");

  // Trading-day offsets, the same convention the position detail page's own
  // period tiles use -- not calendar days, so weekends/holidays don't skew
  // "1 month" short.
  function pctChangeAt(tradingDaysBack: number): number | null {
    const b = anchoredBars;
    if (b.length < 2) return null;
    const lastIdx = b.length - 1;
    const idx = lastIdx - tradingDaysBack;
    if (idx < 0) return null;
    const base = b[idx].close;
    if (base === 0) return null;
    return ((b[lastIdx].close - base) / base) * 100;
  }
  function pctChangeYTD(): number | null {
    const b = anchoredBars;
    if (b.length < 2) return null;
    const lastYear = b[b.length - 1].time.slice(0, 4);
    const idx = b.findIndex((x) => x.time.slice(0, 4) === lastYear);
    if (idx < 0) return null;
    const base = b[idx].close;
    if (base === 0) return null;
    return ((b[b.length - 1].close - base) / base) * 100;
  }
  function tfValue(tf: Tf): number | null {
    return tf.k === "YTD" ? pctChangeYTD() : pctChangeAt(tf.daysBack!);
  }

  const tfRows = $derived(TFS.map((tf) => ({ tf, value: tfValue(tf) })));
  const activeRow = $derived(tfRows.find((r) => r.tf.k === activeTf) ?? tfRows[0]);

  const visibleMonths = $derived.by((): number | undefined => {
    if (!anchoredBars.length) return undefined;
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

  const lastClose = $derived(anchoredBars.length ? anchoredBars[anchoredBars.length - 1].close : null);
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
      <SymbolChart history={anchoredBars} height={260} {visibleMonths} {highlightMonth} regimeBands apsPane extendedAlerts />

      <div class="idx-tfs">
        {#each tfRows as { tf, value } (tf.k)}
          <button class="tf" class:active={tf.k === activeTf} onclick={() => (activeTf = tf.k)}>
            <div class="tf-key">{tf.label}</div>
            <div class="tf-val {value === null ? '' : value >= 0 ? 'pos' : 'neg'}">
              {value === null ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`}
            </div>
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
