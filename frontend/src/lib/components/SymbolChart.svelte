<script lang="ts">
  /**
   * Daily candlestick chart with the same indicator set as ui-reference's
   * TickerChart: EMA9/EMA20/MA50/MA200 lines, an Absolute Price Strength
   * band, and climax/parabolic markers. Trimmed from the original -- no
   * TradingView iframe fallback (this app never had one) and no cross-chart
   * crosshair sync (this page only ever shows one chart at a time).
   */
  import { onDestroy } from "svelte";
  import {
    createChart,
    LineStyle,
    type IChartApi,
    type IPriceLine,
    type ISeriesApi,
    type SeriesMarker,
    type Time,
    CrosshairMode,
  } from "lightweight-charts";
  import type { OHLCVBar } from "$lib/api";
  import {
    calcEMA,
    calcSMA,
    regimeBands as calcRegimeBands,
    absolutePriceStrength,
    parabolicAlerts,
    APS_COLORS,
    PARABOLIC_COLORS,
  } from "$lib/indicators";

  interface TradeMarker {
    time: string;
    label: string;
    color: string;
    shape?: "arrowUp" | "arrowDown";
    position?: "aboveBar" | "belowBar";
  }

  interface Props {
    history: OHLCVBar[];
    height?: number;
    visibleMonths?: number;
    /** Entry/exit fills to annotate on the chart. */
    tradeMarkers?: TradeMarker[];
    /** Initial visible window, e.g. the trade's own entry-to-exit span with
     *  some padding -- takes priority over visibleMonths/fitContent. */
    focusRange?: { from: string; to: string };
    /** A single fill to call out with a horizontal price line, e.g. the
     *  transaction row the user just clicked. */
    selectedMarker?: { price: number; label: string; color: string } | null;
    /** "YYYY-MM" -- dims every bar outside this calendar month, e.g. synced
     *  from a hovered month in a P&L chart elsewhere on the page. */
    highlightMonth?: string | null;
    /** Paint the per-bar trend-regime background behind the candles. */
    regimeBands?: boolean;
    /** Absolute Price Strength columns along the bottom of the pane. */
    apsPane?: boolean;
    /** Climax ("C") and parabolic tier markers above the bars. */
    extendedAlerts?: boolean;
  }
  let {
    history,
    height = 280,
    visibleMonths,
    tradeMarkers,
    focusRange,
    selectedMarker,
    highlightMonth,
    regimeBands = false,
    apsPane = true,
    extendedAlerts = true,
  }: Props = $props();

  const showAlerts = $derived(extendedAlerts);

  let container: HTMLDivElement | undefined = $state();
  let chart: IChartApi | null = null;
  let candles: ISeriesApi<"Candlestick"> | null = null;
  let spotlight: ISeriesApi<"Histogram"> | null = null;
  // Bumped once the chart (re)builds, so the price-line effect below re-runs
  // and re-attaches after a rebuild, not just when selectedMarker changes.
  // Written from a plain counter, never read-then-incremented in place --
  // `chartVersion++` inside the same effect that sets it would make that
  // effect both read and write its own dependency, looping forever.
  let chartVersionCounter = 0;
  let chartVersion = $state(0);
  let resizeObs: ResizeObserver | null = null;

  let restoreView: (() => void) | null = null;
  // Exposed the same way restoreView is, so the highlightMonth effect below
  // can put the view back once a hover-driven zoom clears -- without also
  // resetting viewMoved/interacted the way restoreView does, since zooming
  // to a highlighted month isn't the user panning the chart themselves.
  let applyDefaultViewRef: (() => void) | null = null;
  let interactAbort: AbortController | null = null;
  let viewMoved = $state(false);

  // A hovered month gets a window this many days wider than the month
  // itself on each side, so there's context around it rather than the
  // month's own bars alone filling the whole plot edge to edge.
  const MONTH_ZOOM_PADDING_DAYS = 30;
  function zoomToMonth(monthKey: string) {
    if (!chart) return;
    const [y, m] = monthKey.split("-").map(Number);
    const from = new Date(y, m - 1, 1);
    from.setDate(from.getDate() - MONTH_ZOOM_PADDING_DAYS);
    const to = new Date(y, m, 1); // first of the following month
    to.setDate(to.getDate() + MONTH_ZOOM_PADDING_DAYS);
    chart.timeScale().setVisibleRange({
      from: Math.floor(from.getTime() / 1000) as unknown as Time,
      to: Math.floor(to.getTime() / 1000) as unknown as Time,
    });
  }

  $effect(() => {
    if (!container || !history?.length) return;
    const bars = history;

    viewMoved = false;

    if (chart) {
      chart.remove();
      chart = null;
      resizeObs?.disconnect();
      resizeObs = null;
    }

    chart = createChart(container, {
      width: container.clientWidth,
      height,
      layout: {
        background: { color: "#ffffff" },
        textColor: "rgba(12,13,16,0.55)",
        fontFamily: '"Inter Tight", "Inter", system-ui, sans-serif',
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "rgba(12,13,16,0.05)" },
        horzLines: { color: "rgba(12,13,16,0.05)" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "rgba(12,13,16,0.1)" },
      timeScale: {
        borderColor: "rgba(12,13,16,0.1)",
        timeVisible: true,
      },
    });

    if (regimeBands) {
      const colors = calcRegimeBands(bars);
      const band = chart.addHistogramSeries({
        priceScaleId: "regime",
        priceLineVisible: false,
        lastValueVisible: false,
      });
      chart.priceScale("regime").applyOptions({ scaleMargins: { top: 0, bottom: 0 } });
      band.setData(
        bars.map((b, i) => ({
          time: b.time as unknown as Time,
          value: 1,
          color: colors[i] ?? "rgba(0,0,0,0)",
        })),
      );
    }

    candles = chart.addCandlestickSeries({ priceLineVisible: false });
    candles.setData(
      bars.map((b) => ({
        time: b.time as unknown as Time,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    );

    const times = bars.map((b) => b.time as unknown as Time);
    const closes = bars.map((b) => b.close);

    const addMA = (values: (number | null)[], color: string) => {
      const series = chart!.addLineSeries({
        color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
        title: "",
      });
      const data = values
        .map((v, i) => (v !== null ? { time: times[i], value: v } : null))
        .filter((d): d is { time: Time; value: number } => d !== null);
      series.setData(data);
      return series;
    };

    addMA(calcEMA(closes, 9), "#a855f7");
    addMA(calcEMA(closes, 20), "#22c55e");
    addMA(calcSMA(closes, 50), "#3b82f6");
    addMA(calcSMA(closes, 200), "#ef4444");

    if (apsPane) {
      const { up, down } = absolutePriceStrength(bars);

      const addAPS = (levels: number[]) => {
        const series = chart!.addHistogramSeries({
          priceScaleId: "aps",
          priceLineVisible: false,
          lastValueVisible: false,
          base: 0,
          autoscaleInfoProvider: () => ({ priceRange: { minValue: -4, maxValue: 4 } }),
        });
        series.setData(
          bars.map((b, i) => ({
            time: b.time as unknown as Time,
            value: levels[i],
            color: APS_COLORS[levels[i]] ?? "rgba(0,0,0,0)",
          })),
        );
      };

      addAPS(up);
      addAPS(down);

      const zero = chart.addLineSeries({
        priceScaleId: "aps",
        color: "rgba(12,13,16,0.12)",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      zero.setData(bars.map((b) => ({ time: b.time as unknown as Time, value: 0 })));

      chart.priceScale("aps").applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });
    }

    const markers: SeriesMarker<Time>[] = [];

    if (showAlerts) {
      const { climax, tier } = parabolicAlerts(bars);
      bars.forEach((b, i) => {
        const time = b.time as unknown as Time;
        if (climax[i]) {
          markers.push({ time, position: "aboveBar", color: "#FF5252", shape: "arrowDown", text: "C" });
        }
        const t = tier[i];
        if (t !== null) {
          markers.push({ time, position: "aboveBar", color: PARABOLIC_COLORS[t], shape: "circle" });
        }
      });
    }

    if (tradeMarkers) {
      for (const m of tradeMarkers) {
        markers.push({
          time: m.time as unknown as Time,
          position: m.position ?? "aboveBar",
          color: m.color,
          shape: m.shape ?? "arrowDown",
          text: m.label,
        });
      }
    }

    if (markers.length) {
      markers.sort((a, z) => String(a.time).localeCompare(String(z.time)));
      candles.setMarkers(markers);
    }

    // Month-hover spotlight -- added last so it draws on top of the candles,
    // MAs and markers: a translucent white scrim over every bar outside
    // highlightMonth, which stays untouched. A tint drawn behind the candles
    // (tried first, on the regime scale) barely showed against the regime
    // colors already back there; dimming everything else reads unambiguously
    // regardless of what's underneath. Transparent (a no-op) when unset.
    spotlight = chart.addHistogramSeries({
      priceScaleId: "regime",
      priceLineVisible: false,
      lastValueVisible: false,
    });
    chart.priceScale("regime").applyOptions({ scaleMargins: { top: 0, bottom: 0 } });
    spotlight.setData(bars.map((b) => ({ time: b.time as unknown as Time, value: 1, color: "rgba(0,0,0,0)" })));

    const applyDefaultView = () => {
      if (!chart) return;
      if (focusRange) {
        chart.timeScale().setVisibleRange({
          from: Math.floor(new Date(focusRange.from).getTime() / 1000) as unknown as Time,
          to: Math.floor(new Date(focusRange.to).getTime() / 1000) as unknown as Time,
        });
      } else if (visibleMonths) {
        const to = new Date(bars[bars.length - 1].time);
        const from = new Date(bars[bars.length - 1].time);
        from.setMonth(from.getMonth() - visibleMonths);
        chart.timeScale().setVisibleRange({
          from: Math.floor(from.getTime() / 1000) as unknown as Time,
          to: Math.floor(to.getTime() / 1000) as unknown as Time,
        });
      } else {
        chart.timeScale().fitContent();
      }
    };

    applyDefaultView();
    applyDefaultViewRef = applyDefaultView;

    let interacted = false;
    let programmatic = false;
    const markInteracted = () => {
      interacted = true;
    };

    interactAbort?.abort();
    interactAbort = new AbortController();
    container.addEventListener("pointerdown", markInteracted, { capture: true, signal: interactAbort.signal });
    container.addEventListener("wheel", markInteracted, { capture: true, passive: true, signal: interactAbort.signal });

    restoreView = () => {
      programmatic = true;
      applyDefaultView();
      viewMoved = false;
      interacted = false;
      requestAnimationFrame(() => {
        programmatic = false;
      });
    };

    chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
      if (interacted && !programmatic) viewMoved = true;
    });

    resizeObs = new ResizeObserver(() => {
      if (container && chart) {
        chart.applyOptions({ width: container.clientWidth });
      }
    });
    resizeObs.observe(container);

    chartVersionCounter += 1;
    chartVersion = chartVersionCounter;
  });

  let priceLine: IPriceLine | null = null;
  $effect(() => {
    chartVersion;
    const marker = selectedMarker;
    if (!candles) return;
    if (priceLine) {
      candles.removePriceLine(priceLine);
      priceLine = null;
    }
    if (marker) {
      priceLine = candles.createPriceLine({
        price: marker.price,
        color: marker.color,
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: marker.label,
      });
    }
  });

  $effect(() => {
    chartVersion;
    const month = highlightMonth;
    if (!spotlight || !history?.length) return;
    spotlight.setData(
      history.map((b) => ({
        time: b.time as unknown as Time,
        value: 1,
        color: !month || b.time.startsWith(month) ? "rgba(0,0,0,0)" : "rgba(255,255,255,0.68)",
      })),
    );
    // Zoom into the highlighted month's own window rather than leaving the
    // chart at its wider default view, where one month can be a sliver a
    // few px wide -- then put the view back once the hover clears.
    if (month) {
      zoomToMonth(month);
    } else {
      applyDefaultViewRef?.();
    }
  });

  onDestroy(() => {
    resizeObs?.disconnect();
    chart?.remove();
    interactAbort?.abort();
    restoreView = null;
    applyDefaultViewRef = null;
  });
</script>

<div class="chart-wrap">
  <div class="legend" class:with-reset={viewMoved}>
    <span class="leg" style="color:#a855f7">── EMA 9</span>
    <span class="leg" style="color:#22c55e">── EMA 20</span>
    <span class="leg" style="color:#3b82f6">── MA 50</span>
    <span class="leg" style="color:#ef4444">── MA 200</span>
    {#if apsPane}
      <span class="leg" style="color:#39ff14">▮ APS</span>
    {/if}
    {#if showAlerts}
      <span class="leg" style="color:#9C27B0">● Extended</span>
    {/if}
  </div>
  {#if viewMoved}
    <button class="reset" onclick={() => restoreView?.()} title="Reset to the default view">
      <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M2.5 8a5.5 5.5 0 1 0 1.6-3.9" /><path d="M2.5 2v3h3" />
      </svg>
      Reset
    </button>
  {/if}
  <div bind:this={container} class="chart" style="height:{height}px"></div>
</div>

<style>
  .chart-wrap {
    position: relative;
  }
  .legend {
    position: absolute;
    top: 6px;
    left: 10px;
    right: 56px;
    z-index: 2;
    display: flex;
    flex-wrap: wrap;
    gap: 4px 14px;
    pointer-events: none;
  }
  .legend.with-reset {
    right: 124px;
  }
  .leg {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.02em;
    opacity: 0.85;
  }
  .reset {
    position: absolute;
    top: 4px;
    right: 58px;
    z-index: 3;
    pointer-events: auto;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 7px;
    border: 1px solid rgba(12, 13, 16, 0.12);
    border-radius: 4px;
    background: rgba(255, 255, 255, 0.92);
    color: rgba(12, 13, 16, 0.6);
    font-family: var(--font-sans);
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.04em;
    cursor: pointer;
    transition:
      color 0.15s,
      border-color 0.15s,
      background 0.15s;
  }
  .reset:hover {
    border-color: rgba(12, 13, 16, 0.24);
    color: var(--ink);
    background: #fff;
  }
  .chart {
    width: 100%;
  }
</style>
