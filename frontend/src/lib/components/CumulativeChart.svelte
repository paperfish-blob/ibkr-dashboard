<script lang="ts">
  /**
   * Cumulative realized P&L over time.
   *
   * Follows the Chart.js pattern from ui-reference's GapRegimePanel: colours
   * read out of the CSS custom properties at build time, controllers
   * registered lazily inside onMount, and the chart rebuilt rather than
   * updated on every input change.
   */
  import { onMount, onDestroy } from "svelte";
  import type { Chart as ChartType } from "chart.js";
  import { fmtDay, fmtMoney, num } from "$lib/format";
  import type { CumulativePoint } from "$lib/api";

  interface Props {
    series: CumulativePoint[];
    currency?: string;
    height?: number;
  }
  let { series, currency = "USD", height = 280 }: Props = $props();

  function cssVar(name: string): string {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function toRgba(varName: string, alpha: number): string {
    return `rgba(${cssVar(varName)}, ${alpha})`;
  }

  let canvas = $state<HTMLCanvasElement | null>(null);
  let chart: ChartType | null = null;
  let ChartCtor: typeof ChartType | null = null;
  let chartReady = $state(false);

  function buildChart() {
    if (!canvas || !ChartCtor || series.length === 0) return;

    const values = series.map((p) => num(p.cumulative));
    const labels = series.map((p) => fmtDay(p.date));
    const negative = values[values.length - 1] < 0;
    const line = negative ? cssVar("--dn") : cssVar("--up");
    const fillRgb = negative ? "--dn-rgb" : "--up-rgb";

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, toRgba(fillRgb, 0.18));
    gradient.addColorStop(1, toRgba(fillRgb, 0));

    chart?.destroy();
    chart = new ChartCtor(canvas, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            data: values,
            borderColor: line,
            backgroundColor: gradient,
            borderWidth: 2,
            fill: true,
            tension: 0.2,
            pointRadius: 0,
            pointHoverRadius: 4,
            pointHoverBackgroundColor: line,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300, easing: "easeInOutQuart" },
        interaction: { mode: "index", intersect: false },
        layout: { padding: { top: 6, right: 4, bottom: 0, left: 0 } },
        plugins: {
          legend: { display: false },
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
              label: (c: { parsed: { y: number } }) => fmtMoney(c.parsed.y, currency),
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            border: { color: "transparent" },
            ticks: {
              font: { size: 9 },
              color: toRgba("--ink-rgb", 0.4),
              maxTicksLimit: 10,
              autoSkip: true,
            },
          },
          y: {
            position: "right",
            grid: { color: toRgba("--ink-rgb", 0.06) },
            border: { color: "transparent" },
            ticks: {
              font: { size: 9 },
              color: toRgba("--ink-rgb", 0.4),
              maxTicksLimit: 6,
              callback: (v: string | number) =>
                new Intl.NumberFormat("en-US", { notation: "compact" }).format(Number(v)),
            },
          },
        },
      },
    } as never);
  }

  $effect(() => {
    // Touched so a data change rebuilds; they're read inside the
    // non-reactive buildChart(), which would not register them otherwise.
    void series;
    void currency;
    if (chartReady) buildChart();
  });

  onMount(async () => {
    // Imported here rather than at module scope so Chart.js never loads during
    // prerendering, where there is no document to measure.
    const {
      Chart,
      LineController,
      LineElement,
      PointElement,
      LinearScale,
      CategoryScale,
      Filler,
      Tooltip,
    } = await import("chart.js");
    Chart.register(
      LineController,
      LineElement,
      PointElement,
      LinearScale,
      CategoryScale,
      Filler,
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
      <div class="eyebrow">Running total</div>
      <div class="title">Cumulative realized P&amp;L</div>
    </div>
  </div>

  <div class="body">
    {#if series.length === 0}
      <div class="empty">No realizing trades in this statement period.</div>
    {:else}
      <div class="chart-box" style="height:{height}px">
        <canvas bind:this={canvas}></canvas>
      </div>
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
  .hd {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 14px 22px;
    border-bottom: 1px solid var(--border-05);
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
  .body {
    padding: 14px 18px 18px;
  }
  .chart-box {
    position: relative;
  }
  .empty {
    color: var(--dim-55);
    text-align: center;
    padding: 40px 0;
    font-size: var(--text-sm);
  }
</style>
