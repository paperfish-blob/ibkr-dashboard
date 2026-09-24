<script lang="ts">
  /**
   * How many of the given positions were open at once, day by day. The
   * caller decides what "the given positions" means: Positions Overview
   * passes every position in the current period, open AND closed, so a
   * stretch of overlapping positions still shows up long after they've
   * all since closed; Open Positions passes only what's open today (under
   * its own "From year" floor), so this instead traces how today's actual
   * holdings built up. Either way, a carry-in (unknown open date) or a
   * cash balance is excluded, since neither has a real "opened on this
   * day" to place on the timeline.
   *
   * Split into two stacked layers around a fixed comfort threshold (a
   * starting placeholder, not yet a user setting) so the excess above it
   * reads as its own band rather than a bump in one plain line, plus a
   * one-line callout naming which symbols overlapped on the single worst
   * day -- "you overtraded in June" is a lot less useful than knowing
   * which positions actually did it.
   *
   * A second, smaller chart underneath answers a different question:
   * concurrency (above) is a level, this is a flow -- how many positions
   * were newly opened on a given day, volume-strip style under the main
   * chart, sharing the same day-by-day x-axis so a tall bar down here and
   * a step up above line up visually. A burst of same-day opens is the
   * thing that actually drives overtrading, and it can show up here even
   * on a day the running total above wasn't at its own peak yet.
   *
   * `showRangeSelector` (Positions Overview only -- Open Positions' own
   * window is already just a handful of days, too short for this to help)
   * adds a compressed overview strip below both charts, same drag-to-pan/
   * drag-edges-to-resize pattern Streak Flow already has: both charts
   * above zoom to whatever the selection window currently covers, while
   * the peak-day and busiest-new-open-day callouts keep reading the whole
   * period regardless of zoom, since those are facts about the account,
   * not about whatever's currently in view.
   */
  import { onMount, onDestroy } from "svelte";
  import type { Chart as ChartType } from "chart.js";
  import { fmtDay, fmtFullDate, parseISODay } from "$lib/format";
  import type { Position } from "$lib/api";

  interface Props {
    positions: Position[];
    showRangeSelector?: boolean;
  }
  let { positions, showRangeSelector = false }: Props = $props();

  const COMFORT_THRESHOLD = 3;
  const NEW_OPEN_THRESHOLD = 2;
  const DEFAULT_WINDOW_DAYS = 90;

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
  // The same symbol can legitimately appear more than once in a day's list
  // (e.g. TSLA opened, closed, and opened again as a separate round trip) --
  // collapsed to "SYM ×N" instead of repeating the name N times.
  function formatSymbolCounts(symbols: string[]): string {
    const counts = new Map<string, number>();
    const order: string[] = [];
    for (const s of symbols) {
      if (!counts.has(s)) order.push(s);
      counts.set(s, (counts.get(s) ?? 0) + 1);
    }
    return order.map((s) => (counts.get(s)! > 1 ? `${s} ×${counts.get(s)}` : s)).join(", ");
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
    return { date: best.date, count: best.count, symbolsLabel: formatSymbolCounts(symbols) };
  });

  // symbol(s) newly opened on each date -- a position's own open_date is
  // already exactly "the day it was newly opened," no separate event log
  // needed.
  const newOpensByDate = $derived.by(() => {
    const m = new Map<string, string[]>();
    for (const s of spans) m.set(s.start, [...(m.get(s.start) ?? []), s.symbol]);
    return m;
  });
  const busiestNewOpenDay = $derived.by(() => {
    let bestDate: string | null = null;
    let bestSymbols: string[] = [];
    for (const [date, symbols] of newOpensByDate) {
      if (symbols.length > bestSymbols.length) {
        bestDate = date;
        bestSymbols = symbols;
      }
    }
    if (!bestDate || bestSymbols.length <= 1) return null;
    return { date: bestDate, count: bestSymbols.length, symbolsLabel: formatSymbolCounts(bestSymbols) };
  });

  // Selection window, as fractions of the full `series` -- defaults to the
  // trailing DEFAULT_WINDOW_DAYS (not the full range) whenever the
  // underlying data actually changes (a new `series` reference only happens
  // from a `positions` prop change, e.g. switching Period; dragging never
  // touches `series` itself). A full-width default would leave nothing for
  // the pan handle to do -- both edges are already at the boundary, so
  // there's no room to drag until the user first shrinks it manually.
  // Short histories that don't exceed the window just show everything.
  let selStart = $state(0);
  let selEnd = $state(1);
  $effect(() => {
    const n = series.length;
    if (n > DEFAULT_WINDOW_DAYS) {
      selStart = 1 - DEFAULT_WINDOW_DAYS / n;
      selEnd = 1;
    } else {
      selStart = 0;
      selEnd = 1;
    }
  });

  const windowedSeries = $derived.by((): DayCount[] => {
    if (!showRangeSelector || series.length === 0) return series;
    const n = series.length;
    const startIdx = Math.max(0, Math.min(n - 1, Math.floor(selStart * n)));
    const endIdx = Math.max(startIdx + 1, Math.min(n, Math.ceil(selEnd * n)));
    return series.slice(startIdx, endIdx);
  });
  const windowedNewOpenCounts = $derived(
    windowedSeries.map((pt) => newOpensByDate.get(pt.date)?.length ?? 0),
  );

  // A hand-drawn step path (not Chart.js) for the compressed overview strip
  // -- cheap, and matches Streak Flow's own minimap, which is also plain
  // SVG rather than a second full chart instance.
  function stepPath(values: number[], w: number, h: number, padTop: number, padBot: number, maxVal: number): string {
    if (values.length === 0) return "";
    const barW = w / values.length;
    const yOf = (v: number) => padTop + (1 - v / maxVal) * (h - padTop - padBot);
    const pts: [number, number][] = [];
    values.forEach((v, i) => {
      const y = yOf(v);
      pts.push([i * barW, y]);
      pts.push([(i + 1) * barW, y]);
    });
    return "M" + pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" L");
  }

  const MINI_W = 1180;
  const MINI_H = 56;
  const miniShape = $derived.by(() => {
    if (!showRangeSelector || series.length === 0) return null;
    const maxVal = Math.max(COMFORT_THRESHOLD, ...series.map((pt) => pt.count));
    const within = series.map((pt) => Math.min(pt.count, COMFORT_THRESHOLD));
    const total = series.map((pt) => pt.count);
    const withinPath = stepPath(within, MINI_W, MINI_H, 2, 4, maxVal);
    const totalPath = stepPath(total, MINI_W, MINI_H, 2, 4, maxVal);
    const baseline = 2 + (MINI_H - 2 - 4);
    return {
      withinPath,
      totalPath,
      withinFill: `${withinPath} L${MINI_W},${baseline} L0,${baseline} Z`,
      selX: selStart * MINI_W,
      selW: Math.max(6, (selEnd - selStart) * MINI_W),
    };
  });

  let miniSvg = $state<SVGSVGElement | null>(null);
  let dragMode: "pan" | "left" | "right" | null = null;
  let dragOriginX = 0;
  let dragOrigStart = 0;
  let dragOrigEnd = 0;

  function startDrag(mode: "pan" | "left" | "right", e: MouseEvent) {
    e.preventDefault();
    dragMode = mode;
    dragOriginX = e.clientX;
    dragOrigStart = selStart;
    dragOrigEnd = selEnd;
    window.addEventListener("mousemove", handleDragMove);
    window.addEventListener("mouseup", endDrag);
  }
  function handleDragMove(e: MouseEvent) {
    if (!dragMode || !miniSvg) return;
    const rect = miniSvg.getBoundingClientRect();
    const dx = (e.clientX - dragOriginX) / rect.width;
    const clamp = (v: number) => Math.max(0, Math.min(1, v));
    if (dragMode === "pan") {
      const width = dragOrigEnd - dragOrigStart;
      let ns = dragOrigStart + dx;
      let ne = dragOrigEnd + dx;
      if (ns < 0) {
        ns = 0;
        ne = width;
      }
      if (ne > 1) {
        ne = 1;
        ns = 1 - width;
      }
      selStart = clamp(ns);
      selEnd = clamp(ne);
    } else if (dragMode === "left") {
      selStart = Math.min(clamp(dragOrigStart + dx), selEnd - 0.02);
    } else if (dragMode === "right") {
      selEnd = Math.max(clamp(dragOrigEnd + dx), selStart + 0.02);
    }
  }
  function endDrag() {
    dragMode = null;
    window.removeEventListener("mousemove", handleDragMove);
    window.removeEventListener("mouseup", endDrag);
  }

  let canvas = $state<HTMLCanvasElement | null>(null);
  let chart: ChartType | null = null;
  let newOpensCanvas = $state<HTMLCanvasElement | null>(null);
  let newOpensChart: ChartType | null = null;
  let ChartCtor: typeof ChartType | null = null;
  let chartReady = $state(false);

  function buildChart() {
    if (!canvas || !ChartCtor || windowedSeries.length === 0) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    chart?.destroy();

    const view = windowedSeries;
    const labels = view.map((pt) => fmtDay(pt.date));
    const within = view.map((pt) => Math.min(pt.count, COMFORT_THRESHOLD));
    const total = view.map((pt) => pt.count);

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
              label: (c: { dataIndex: number }) => `Open that day: ${view[c.dataIndex].count}`,
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

  function buildNewOpensChart() {
    if (!newOpensCanvas || !ChartCtor || windowedSeries.length === 0) return;
    const ctx = newOpensCanvas.getContext("2d");
    if (!ctx) return;
    newOpensChart?.destroy();

    const view = windowedSeries;
    const counts = windowedNewOpenCounts;
    const labels = view.map((pt) => fmtDay(pt.date));
    const normal = cssVar("--accent");
    const above = cssVar("--amber");

    newOpensChart = new ChartCtor(newOpensCanvas, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            data: counts,
            backgroundColor: counts.map((c) => (c > NEW_OPEN_THRESHOLD ? above : normal)),
            borderRadius: 1.5,
            barPercentage: 0.85,
            categoryPercentage: 0.9,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300, easing: "easeInOutQuart" },
        interaction: { mode: "index", intersect: false },
        layout: { padding: { top: 2, right: 4, bottom: 0, left: 0 } },
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
              label: (c: { dataIndex: number }) => {
                const syms = newOpensByDate.get(view[c.dataIndex].date);
                return syms?.length
                  ? `${syms.length} new: ${formatSymbolCounts(syms)}`
                  : "No new positions";
              },
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            border: { color: "transparent" },
            ticks: { display: false },
          },
          y: {
            position: "right" as const,
            beginAtZero: true,
            grid: { display: false },
            border: { color: "transparent" },
            ticks: { display: false },
          },
        },
      },
    } as never);
  }

  $effect(() => {
    void windowedSeries;
    void windowedNewOpenCounts;
    if (chartReady) {
      buildChart();
      buildNewOpensChart();
    }
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

  onDestroy(() => {
    chart?.destroy();
    newOpensChart?.destroy();
    window.removeEventListener("mousemove", handleDragMove);
    window.removeEventListener("mouseup", endDrag);
  });
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
    {#if showRangeSelector && windowedSeries.length > 0 && windowedSeries.length < series.length}
      <div class="range-pill">{windowedSeries.length} of {series.length} days</div>
    {/if}
  </div>
  <div class="body">
    {#if series.length === 0}
      <div class="empty">No positions with a known open date in this period.</div>
    {:else}
      <div class="chart-box">
        <canvas bind:this={canvas}></canvas>
      </div>
      <div class="sub-label">New positions opened, per day</div>
      <div class="sub-chart-box">
        <canvas bind:this={newOpensCanvas}></canvas>
      </div>
      {#if showRangeSelector && miniShape}
        <div class="mini-label">Drag to explore &middot; full period</div>
        <div class="mini-wrap">
          <svg bind:this={miniSvg} viewBox="0 0 {MINI_W} {MINI_H}" preserveAspectRatio="none">
            <path d={miniShape.withinFill} fill="var(--accent)" fill-opacity="0.3" stroke="none" />
            <path d={miniShape.withinPath} fill="none" stroke="var(--accent)" stroke-width="1" />
            <path d={miniShape.totalPath} fill="none" stroke="var(--amber)" stroke-width="1" />
            <rect
              x={miniShape.selX}
              y="1"
              width={miniShape.selW}
              height={MINI_H - 2}
              rx="4"
              class="mini-selection"
              onmousedown={(e) => startDrag("pan", e)}
            />
            <rect
              x={miniShape.selX}
              y="1"
              width="6"
              height={MINI_H - 2}
              rx="2"
              class="mini-handle"
              onmousedown={(e) => startDrag("left", e)}
            />
            <rect
              x={Math.max(6, miniShape.selX + miniShape.selW - 6)}
              y="1"
              width="6"
              height={MINI_H - 2}
              rx="2"
              class="mini-handle"
              onmousedown={(e) => startDrag("right", e)}
            />
          </svg>
        </div>
      {/if}
      {#if peak}
        <div class="callout">
          <b>{peak.count} concurrent</b> on {fmtFullDate(peak.date)} &mdash; {peak.symbolsLabel}
        </div>
      {/if}
      {#if busiestNewOpenDay}
        <div class="callout accent">
          <b>{busiestNewOpenDay.count} positions opened</b> on {fmtFullDate(busiestNewOpenDay.date)} &mdash; {busiestNewOpenDay.symbolsLabel}
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
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
  }
  .range-pill {
    font-size: var(--text-2xs);
    font-weight: var(--weight-bold);
    color: var(--accent);
    background: var(--accent-bg);
    padding: 4px 10px;
    border-radius: var(--radius-pill);
    white-space: nowrap;
    flex-shrink: 0;
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
  .sub-label {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--dim-45);
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px dashed var(--border-05);
  }
  .sub-chart-box {
    position: relative;
    height: 60px;
    margin-top: 6px;
  }
  .mini-label {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--dim-45);
    margin-top: 12px;
    padding-top: 10px;
    border-top: 1px dashed var(--border-05);
    margin-bottom: 6px;
  }
  .mini-wrap svg {
    display: block;
    width: 100%;
    height: 56px;
  }
  .mini-selection {
    fill: var(--accent-bg);
    stroke: var(--accent);
    stroke-width: 1.5;
    cursor: grab;
  }
  .mini-selection:active {
    cursor: grabbing;
  }
  .mini-handle {
    fill: var(--accent);
    cursor: ew-resize;
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
  .callout.accent {
    background: var(--accent-bg);
    border-color: rgba(91, 108, 255, 0.16);
    margin-top: 8px;
  }
  .callout.accent b {
    color: var(--accent);
  }
</style>
