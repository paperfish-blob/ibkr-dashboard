<script lang="ts">
  /**
   * How many positions were open at once, day by day -- across every
   * position in the current period (open AND closed), not just what's
   * open right now, so a stretch of overlapping positions still shows up
   * long after they've all since closed. A carry-in (unknown open date)
   * or a cash balance is excluded, same as Open Positions does, since
   * neither has a real "opened on this day" to place on the timeline.
   *
   * Split into two stacked layers around a fixed comfort threshold (a
   * starting placeholder, not yet a user setting) so the excess above it
   * reads as its own band rather than a bump in one plain line, plus a
   * one-line callout naming which symbols overlapped on the single worst
   * day -- "you overtraded in June" is a lot less useful than knowing
   * which positions actually did it.
   */
  import { onMount, onDestroy } from "svelte";
  import type { Chart as ChartType } from "chart.js";
  import { fmtDay, fmtFullDate, parseISODay } from "$lib/format";
  import type { Position } from "$lib/api";

  interface Props {
    positions: Position[];
  }
  let { positions }: Props = $props();

  const COMFORT_THRESHOLD = 3;

  function cssVar(name: string): string {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function toRgba(varName: string, alpha: number): string {
    return `rgba(${cssVar(varName)}, ${alpha})`;
  }
  function todayIso(): string {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }
  function addDays(iso: string, n: number): string {
    const d = parseISODay(iso);
    d.setDate(d.getDate() + n);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }

  interface DayCount {
    date: string;
    count: number;
  }
  interface Span {
    symbol: string;
    start: string;
    end: string; // inclusive
  }

  const spans = $derived.by((): Span[] =>
    positions
      .filter((p) => p.open_date && p.asset_category !== "CASH")
      .map((p) => ({
        symbol: p.symbol,
        start: p.open_date!,
        end: p.is_open ? todayIso() : (p.exit_date ?? p.open_date!),
      })),
  );

  // A sweep over +1-at-open / -1-the-day-after-close events, walked one
  // calendar day at a time from the earliest open date through today --
  // cheap even across a multi-year period (a few thousand loop iterations).
  const series = $derived.by((): DayCount[] => {
    if (spans.length === 0) return [];
    const deltas = new Map<string, number>();
    let minDate = spans[0].start;
    for (const { start, end } of spans) {
      if (start < minDate) minDate = start;
      deltas.set(start, (deltas.get(start) ?? 0) + 1);
      const dayAfter = addDays(end, 1);
      deltas.set(dayAfter, (deltas.get(dayAfter) ?? 0) - 1);
    }
    const out: DayCount[] = [];
    const today = todayIso();
    let count = 0;
    let cursor = minDate;
    while (cursor <= today) {
      if (deltas.has(cursor)) count += deltas.get(cursor)!;
      out.push({ date: cursor, count });
      cursor = addDays(cursor, 1);
    }
    return out;
  });

  const peak = $derived.by(() => {
    if (series.length === 0) return null;
    let best = series[0];
    for (const pt of series) if (pt.count > best.count) best = pt;
    if (best.count <= COMFORT_THRESHOLD) return null;
    const symbols = spans.filter((s) => s.start <= best.date && best.date <= s.end).map((s) => s.symbol);
    return { date: best.date, count: best.count, symbols };
  });

  let canvas = $state<HTMLCanvasElement | null>(null);
  let chart: ChartType | null = null;
  let ChartCtor: typeof ChartType | null = null;
  let chartReady = $state(false);

  function buildChart() {
    if (!canvas || !ChartCtor || series.length === 0) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    chart?.destroy();

    const labels = series.map((pt) => fmtDay(pt.date));
    const within = series.map((pt) => Math.min(pt.count, COMFORT_THRESHOLD));
    const total = series.map((pt) => pt.count);

    chart = new ChartCtor(canvas, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: `Within comfort (≤${COMFORT_THRESHOLD})`,
            data: within,
            borderColor: cssVar("--accent"),
            backgroundColor: cssVar("--accent-bg"),
            borderWidth: 1.4,
            fill: "origin",
            stepped: true,
            pointRadius: 0,
          },
          {
            label: "Excess above comfort",
            data: total,
            borderColor: cssVar("--amber"),
            backgroundColor: cssVar("--amber-bg"),
            borderWidth: 1.4,
            fill: "-1",
            stepped: true,
            pointRadius: 0,
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
          legend: {
            display: true,
            position: "bottom" as const,
            labels: { boxWidth: 8, boxHeight: 8, font: { size: 10 }, color: toRgba("--ink-rgb", 0.6) },
          },
          tooltip: {
            backgroundColor: cssVar("--surface"),
            titleColor: toRgba("--ink-rgb", 0.5),
            bodyColor: cssVar("--ink"),
            borderColor: toRgba("--ink-rgb", 0.12),
            borderWidth: 1,
            padding: 10,
            cornerRadius: 6,
            displayColors: false,
            filter: (c: { datasetIndex: number }) => c.datasetIndex === 1,
            callbacks: {
              label: (c: { dataIndex: number }) => `Open that day: ${series[c.dataIndex].count}`,
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            border: { color: "transparent" },
            ticks: { font: { size: 9 }, color: toRgba("--ink-rgb", 0.4), maxTicksLimit: 10, autoSkip: true },
          },
          y: {
            position: "right" as const,
            beginAtZero: true,
            grid: { color: toRgba("--ink-rgb", 0.06) },
            border: { color: "transparent" },
            ticks: { font: { size: 9 }, color: toRgba("--ink-rgb", 0.4), stepSize: 1, precision: 0 },
          },
        },
      },
    } as never);
  }

  $effect(() => {
    void series;
    if (chartReady) buildChart();
  });

  onMount(async () => {
    const { Chart, LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Legend, Tooltip } =
      await import("chart.js");
    Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Legend, Tooltip);
    ChartCtor = Chart;
    chartReady = true;
  });

  onDestroy(() => chart?.destroy());
</script>

<div class="panel">
  <div class="hd">
    <div class="hd-left">
      <div class="eyebrow">Open positions</div>
      <div class="title">Open positions per day</div>
      <div class="caption">
        Concurrent open-position count across this period &middot; blue = within a comfort level of {COMFORT_THRESHOLD},
        amber = the excess above it
      </div>
    </div>
  </div>
  <div class="body">
    {#if series.length === 0}
      <div class="empty">No positions with a known open date in this period.</div>
    {:else}
      <div class="chart-box">
        <canvas bind:this={canvas}></canvas>
      </div>
      {#if peak}
        <div class="callout">
          <b>{peak.count} concurrent</b> on {fmtFullDate(peak.date)} &mdash; {peak.symbols.join(", ")}
        </div>
      {/if}
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
  .caption {
    font-size: var(--text-2xs);
    color: var(--dim-45);
    letter-spacing: 0.01em;
    margin-top: 2px;
  }
  .body {
    padding: 14px 18px 18px;
  }
  .chart-box {
    position: relative;
    height: 220px;
  }
  .empty {
    color: var(--dim-55);
    text-align: center;
    padding: 40px 0;
    font-size: var(--text-sm);
  }
  .callout {
    margin-top: 12px;
    padding: 10px 14px;
    background: var(--amber-bg);
    border: 1px solid rgba(180, 83, 9, 0.16);
    border-radius: var(--radius-md);
    font-size: var(--text-xs);
    color: var(--dim-70);
  }
  .callout b {
    color: var(--amber);
  }
</style>
