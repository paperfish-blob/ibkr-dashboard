<script lang="ts">
  /**
   * Open Positions' "Potential P&L" panel -- one card holding both the
   * over-time chart and the per-position breakdown, so the two read as one
   * component rather than two stacked panels.
   *
   * The chart itself has three views, picked from the same underlying
   * day-by-day series computed in +page.svelte's potentialPnlSeries():
   *  - Combined: the summed series across every open position (unchanged
   *    from the original single-line chart).
   *  - By position: the selected position's own $ series.
   *  - Normalized: every position's series rescaled onto a shared 0-100%
   *    "holding period elapsed" x-axis, $ P&L on the y-axis unchanged --
   *    so a 2-day-old position and a 5-year-old one both span the full
   *    width instead of the young one being an invisible sliver at the
   *    right edge of a calendar axis.
   *  - Daily Δ: day-over-day $ change in the Combined series (consecutive
   *    differences, not the running total) -- a bar chart so a single rough
   *    day, or the day a position's average cost got rebased by a new
   *    entry, shows up as one tall bar instead of a step in a line you
   *    could easily scroll past.
   */
  import { onMount, onDestroy } from "svelte";
  import type { Chart as ChartType } from "chart.js";
  import SegToggle from "./SegToggle.svelte";
  import PositionSparkCard from "./PositionSparkCard.svelte";
  import type { OpenPositionsRow } from "./OpenPositionsList.svelte";
  import type { CumulativePoint } from "$lib/api";
  import { fmtDay, fmtMoney, fmtPriceLike, toneOf, num } from "$lib/format";

  export interface DayPoint {
    date: string;
    value: number;
    open: number;
    close: number;
  }
  export interface PositionSeries {
    row: OpenPositionsRow;
    series: DayPoint[];
  }

  interface Props {
    positions: PositionSeries[];
    combinedSeries: CumulativePoint[];
    currency?: string;
  }
  let { positions, combinedSeries, currency = "USD" }: Props = $props();

  const CHART_H = 220;
  const NORM_PALETTE = ["--accent", "--ai", "--amber", "--up", "--dn"];

  type View = "combined" | "byposition" | "normalized" | "daily";
  const VIEW_OPTIONS: { label: string; value: View }[] = [
    { label: "Combined", value: "combined" },
    { label: "By position", value: "byposition" },
    { label: "Normalized", value: "normalized" },
    { label: "Daily Δ", value: "daily" },
  ];
  let view = $state<View>("combined");
  let selectedSymbol = $state<string | null>(null);

  const bySymbol = $derived([...positions].sort((a, b) => b.row.costBasis - a.row.costBasis));
  const symOptions = $derived(bySymbol.map((p) => p.row.p.symbol));
  const activeSymbol = $derived(selectedSymbol ?? bySymbol[0]?.row.p.symbol ?? null);
  const activePosition = $derived(bySymbol.find((p) => p.row.p.symbol === activeSymbol) ?? bySymbol[0] ?? null);

  function cssVar(name: string): string {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function toRgba(varName: string, alpha: number): string {
    return `rgba(${cssVar(varName)}, ${alpha})`;
  }
  function compactFmt(v: number): string {
    return new Intl.NumberFormat("en-US", { notation: "compact" }).format(v);
  }

  let canvas = $state<HTMLCanvasElement | null>(null);
  let chart: ChartType | null = null;
  let ChartCtor: typeof ChartType | null = null;
  let chartReady = $state(false);

  function baseOptions(opts: {
    xType?: "category" | "linear";
    xTickFmt?: (v: number) => string;
    yTickFmt: (v: number) => string;
    tooltipFmt: (v: number) => string;
    legend?: boolean;
    /** Extra tooltip lines (e.g. that day's open/close) below the main
     *  value line, keyed by the hovered point's index into the dataset. */
    afterLabel?: (index: number) => string[];
  }) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300, easing: "easeInOutQuart" },
      interaction: { mode: "index", intersect: false },
      layout: { padding: { top: 6, right: 4, bottom: 0, left: 0 } },
      plugins: {
        legend: opts.legend
          ? {
              display: true,
              position: "bottom" as const,
              labels: { boxWidth: 8, boxHeight: 8, font: { size: 10 }, color: toRgba("--ink-rgb", 0.6) },
            }
          : { display: false },
        tooltip: {
          backgroundColor: cssVar("--surface"),
          titleColor: toRgba("--ink-rgb", 0.5),
          bodyColor: cssVar("--ink"),
          borderColor: toRgba("--ink-rgb", 0.12),
          borderWidth: 1,
          padding: 10,
          cornerRadius: 6,
          displayColors: false,
          callbacks: {
            label: (c: { parsed: { y: number }; dataset: { label?: string } }) =>
              (opts.legend && c.dataset.label ? `${c.dataset.label}: ` : "") + opts.tooltipFmt(c.parsed.y),
            afterLabel: opts.afterLabel ? (c: { dataIndex: number }) => opts.afterLabel!(c.dataIndex) : undefined,
          },
        },
      },
      scales: {
        x: {
          type: opts.xType ?? "category",
          min: opts.xType === "linear" ? 0 : undefined,
          max: opts.xType === "linear" ? 100 : undefined,
          grid: { display: false },
          border: { color: "transparent" },
          ticks: {
            font: { size: 9 },
            color: toRgba("--ink-rgb", 0.4),
            maxTicksLimit: 10,
            autoSkip: true,
            callback: opts.xTickFmt ? (v: number) => opts.xTickFmt!(Number(v)) : undefined,
          },
        },
        y: {
          position: "right" as const,
          grid: { color: toRgba("--ink-rgb", 0.06) },
          border: { color: "transparent" },
          ticks: {
            font: { size: 9 },
            color: toRgba("--ink-rgb", 0.4),
            maxTicksLimit: 6,
            callback: (v: string | number) => opts.yTickFmt(Number(v)),
          },
        },
      },
    };
  }

  function moneySeriesDataset(values: number[], gradientHeight: number, ctx: CanvasRenderingContext2D) {
    const negative = values[values.length - 1] < 0;
    const line = negative ? cssVar("--dn") : cssVar("--up");
    const fillRgb = negative ? "--dn-rgb" : "--up-rgb";
    const gradient = ctx.createLinearGradient(0, 0, 0, gradientHeight);
    gradient.addColorStop(0, toRgba(fillRgb, 0.18));
    gradient.addColorStop(1, toRgba(fillRgb, 0));
    return {
      data: values,
      borderColor: line,
      backgroundColor: gradient,
      borderWidth: 2,
      fill: true,
      tension: 0.2,
      pointRadius: 0,
      pointHoverRadius: 4,
      pointHoverBackgroundColor: line,
    };
  }

  function buildChart() {
    if (!canvas || !ChartCtor) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    chart?.destroy();
    chart = null;

    if (view === "combined") {
      if (combinedSeries.length === 0) return;
      const values = combinedSeries.map((p) => num(p.cumulative));
      const labels = combinedSeries.map((p) => fmtDay(p.date));
      chart = new ChartCtor(canvas, {
        type: "line",
        data: { labels, datasets: [moneySeriesDataset(values, CHART_H, ctx)] },
        options: baseOptions({ yTickFmt: compactFmt, tooltipFmt: (v) => fmtMoney(v, currency) }),
      } as never);
    } else if (view === "byposition") {
      if (!activePosition || activePosition.series.length === 0) return;
      const series = activePosition.series;
      const values = series.map((p) => p.value);
      const labels = series.map((p) => fmtDay(p.date));
      chart = new ChartCtor(canvas, {
        type: "line",
        data: { labels, datasets: [moneySeriesDataset(values, CHART_H, ctx)] },
        options: baseOptions({
          yTickFmt: compactFmt,
          tooltipFmt: (v) => fmtMoney(v, currency),
          afterLabel: (i) => [
            `Open: ${fmtPriceLike(series[i].open, currency, 2)}`,
            `Close: ${fmtPriceLike(series[i].close, currency, 2)}`,
          ],
        }),
      } as never);
    } else if (view === "daily") {
      if (combinedSeries.length < 2) return;
      const labels: string[] = [];
      const deltas: number[] = [];
      for (let i = 1; i < combinedSeries.length; i++) {
        deltas.push(num(combinedSeries[i].cumulative) - num(combinedSeries[i - 1].cumulative));
        labels.push(fmtDay(combinedSeries[i].date));
      }
      const upColor = cssVar("--up");
      const dnColor = cssVar("--dn");
      chart = new ChartCtor(canvas, {
        type: "bar",
        data: {
          labels,
          datasets: [
            {
              data: deltas,
              backgroundColor: deltas.map((v) => (v >= 0 ? upColor : dnColor)),
              borderRadius: 2,
              barPercentage: 0.9,
              categoryPercentage: 0.85,
            },
          ],
        },
        options: baseOptions({ yTickFmt: compactFmt, tooltipFmt: (v) => fmtMoney(v, currency) }),
      } as never);
    } else {
      const datasets = bySymbol
        .filter((p) => p.series.length > 1)
        .map((p, i) => {
          const n = p.series.length;
          const color = cssVar(NORM_PALETTE[i % NORM_PALETTE.length]);
          return {
            label: p.row.p.symbol,
            data: p.series.map((pt, idx) => ({
              x: (idx / (n - 1)) * 100,
              y: pt.value,
            })),
            borderColor: color,
            backgroundColor: color,
            borderWidth: 1.8,
            fill: false,
            tension: 0.15,
            pointRadius: 0,
            pointHoverRadius: 3,
            pointHoverBackgroundColor: color,
          };
        });
      if (datasets.length === 0) return;
      chart = new ChartCtor(canvas, {
        type: "line",
        data: { datasets },
        options: baseOptions({
          xType: "linear",
          xTickFmt: (v) => `${v}%`,
          yTickFmt: compactFmt,
          tooltipFmt: (v) => fmtMoney(v, currency),
          legend: true,
        }),
      } as never);
    }
  }

  $effect(() => {
    void view;
    void selectedSymbol;
    void positions;
    void combinedSeries;
    void currency;
    if (chartReady) buildChart();
  });

  onMount(async () => {
    const {
      Chart,
      LineController,
      LineElement,
      PointElement,
      BarController,
      BarElement,
      LinearScale,
      CategoryScale,
      Filler,
      Legend,
      Tooltip,
    } = await import("chart.js");
    Chart.register(
      LineController,
      LineElement,
      PointElement,
      BarController,
      BarElement,
      LinearScale,
      CategoryScale,
      Filler,
      Legend,
      Tooltip,
    );
    ChartCtor = Chart;
    chartReady = true;
  });

  onDestroy(() => chart?.destroy());
</script>

<div class="panel">
  <div class="hd">
    <div class="hd-left">
      <div class="eyebrow">Open positions</div>
      <div class="title">Potential P&amp;L over time</div>
      <div class="caption">
        {#if view === "combined"}
          What closing everything at that day's close would have looked like, summed across every position currently
          open &middot; includes realized P&amp;L already locked in by any partial exits
        {:else if view === "byposition"}
          Same day-by-day calculation, one position at a time
        {:else if view === "normalized"}
          Each position's own $ P&amp;L, stretched to a shared 0&ndash;100% of its own holding period (x-axis only) so a
          2-day-old and a 5-year-old position line up side by side
        {:else}
          Day-over-day change in the Combined series &middot; how much moved on a given day, not the running total
        {/if}
      </div>
    </div>
    <SegToggle options={VIEW_OPTIONS} active={view} onChange={(v) => (view = v as View)} />
  </div>

  {#if view === "byposition" && symOptions.length > 1}
    <div class="symtabs">
      <SegToggle options={symOptions} active={activeSymbol ?? ""} onChange={(s) => (selectedSymbol = s)} />
    </div>
  {/if}

  <div class="body">
    <div class="chart-box" style="height:{CHART_H}px">
      <canvas bind:this={canvas}></canvas>
    </div>
  </div>

  <div class="hd divider">
    <div class="hd-left">
      <div class="eyebrow">Open positions</div>
      <div class="title">Potential P&amp;L by position</div>
      <div class="caption">
        Same day-by-day calculation as the chart above, one card per position on its own time scale &middot; click a
        card to open that position's detail page
      </div>
    </div>
  </div>
  <div class="grid">
    {#each bySymbol as p (p.row.p.symbol + p.row.p.open_date + p.row.p.open_time)}
      <PositionSparkCard {p} {currency} />
    {/each}
  </div>
</div>

<style>
  .panel {
    background: var(--surface);
    border: 1px solid var(--border-05);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }
  .hd {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    padding: 14px 22px;
    border-bottom: 1px solid var(--border-05);
  }
  .hd.divider {
    border-top: 1px solid var(--border-05);
  }
  .hd-left {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .eyebrow {
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--dim-55);
  }
  .title {
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    letter-spacing: -0.01em;
    color: var(--text);
  }
  .caption {
    font-size: var(--text-2xs);
    color: var(--dim-45);
    letter-spacing: 0.01em;
    margin-top: 2px;
    max-width: 620px;
  }

  .symtabs {
    padding: 12px 22px 0;
  }

  .body {
    padding: 14px 18px 18px;
  }
  .chart-box {
    position: relative;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 1px;
    background: var(--border-05);
  }
</style>
