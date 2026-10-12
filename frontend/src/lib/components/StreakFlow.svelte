<script lang="ts">
  /**
   * One diverging bar per run of consecutive same-outcome positions, in the
   * order they actually closed -- a win streak climbs up in green, a loss
   * streak drops down in red, and the bar's height is the streak length.
   * Same visual grammar as the P&L bar charts elsewhere in the app, just
   * one bar per run instead of one per month.
   *
   * Bar width has a floor (MIN_BAR_W) below which bars stay legible instead
   * of shrinking further -- "All" can easily produce 200+ runs. Past that
   * floor the chart's own width grows past the panel and scrolls, rather
   * than clipping the overflow (which used to silently drop the most
   * recent runs -- including the current streak -- off the right edge).
   */
  import { fmtMoney, toneOf } from "$lib/format";
  import type { StreakLossLines } from "$lib/stores";

  export interface StreakRun {
    outcome: "win" | "loss";
    length: number;
    start: string; // "YYYY-MM-DD", first position in the run
    end: string; // "YYYY-MM-DD", last position in the run
    total: number; // summed realized P&L across the run
    partials: string[]; // symbols of partially-closed positions in the run
  }

  interface Props {
    runs: StreakRun[];
    currency?: string;
    /** Which date the runs were ordered by -- only drives the caption's
     *  wording; the caller already did the ordering. */
    groupBy?: "exit" | "entry";
    /** Whether partially-closed positions are counted in `runs` -- the
     *  caller owns the filtering; this only drives the toggle's state. */
    includePartial?: boolean;
    /** How many partials in the current view the toggle governs. */
    partialCount?: number;
    onTogglePartial?: (include: boolean) => void;
    /** Yellow/orange dashed lines at these loss-run lengths. */
    lossLines?: StreakLossLines;
    onLossLinesChange?: (next: StreakLossLines) => void;
    /** The Positions page's own date-range filter, so a run whose
     *  start/end exactly matches it can render as selected -- this stays
     *  in sync even when that range was set some other way (the Filters
     *  popover, a URL param), not only by clicking a bar here. */
    selectedFrom?: string | null;
    selectedTo?: string | null;
    /** Fired with a run's [start, end], or [null, null] to clear -- the
     *  caller owns the actual date-range filter; this component only ever
     *  proposes what it should be set to. */
    onSelectRun?: (from: string | null, to: string | null) => void;
  }
  let { runs, currency = "USD", groupBy = "exit", includePartial = true, partialCount = 0, onTogglePartial, lossLines = { on: false, caution: 3, alert: 5 }, onLossLinesChange, selectedFrom = null, selectedTo = null, onSelectRun }: Props = $props();

  const maxWinStreak = $derived(Math.max(0, ...runs.filter((r) => r.outcome === "win").map((r) => r.length)));
  const maxLossStreak = $derived(Math.max(0, ...runs.filter((r) => r.outcome === "loss").map((r) => r.length)));
  const cautionHits = $derived(
    runs.filter((r) => r.outcome === "loss" && r.length >= lossLines.caution).length,
  );
  const alertHits = $derived(runs.filter((r) => r.outcome === "loss" && r.length >= lossLines.alert).length);
  const currentRun = $derived(runs.length ? runs[runs.length - 1] : null);
  const selectedIndex = $derived(
    selectedFrom && selectedTo ? runs.findIndex((r) => r.start === selectedFrom && r.end === selectedTo) : -1,
  );

  function selectRun(i: number) {
    if (!onSelectRun) return;
    if (i === selectedIndex) {
      onSelectRun(null, null);
    } else {
      onSelectRun(runs[i].start, runs[i].end);
    }
  }

  // Month + year, not month + day -- this account's history can span
  // several years, and a bare day/month risks two genuinely different
  // years landing on the same calendar day at the axis's two endpoints.
  function fmtDate(d: string): string {
    const [y, m] = d.split("-").map(Number);
    return new Date(y, m - 1, 1).toLocaleDateString("en-US", { month: "short", year: "numeric" });
  }
  function fmtDateFull(d: string): string {
    const [y, m, day] = d.split("-").map(Number);
    return new Date(y, m - 1, day).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  }

  // ---- bar geometry -- same shared-column approach as MonthlyPnL's own
  // charts, just keyed by run index instead of month. ----
  const PAD_L = 6;
  const PAD_R = 6;
  const PAD_T = 16;
  const PAD_B = 22;
  const GAP = 3;
  const CHART_H = 160;
  const MIN_BAR_W = 10;
  const OVERVIEW_H = 30;

  let box: HTMLDivElement | undefined = $state();
  let scrollEl: HTMLDivElement | undefined = $state();
  let overviewEl: HTMLDivElement | undefined = $state();
  let availW = $state(860);

  const layout = $derived.by(() => {
    if (!runs.length) return null;
    const n = runs.length;
    const plotW = Math.max(0, availW - PAD_L - PAD_R);
    const naturalBarW = (plotW - GAP * (n - 1)) / n;
    // Below MIN_BAR_W, stop shrinking bars to fit and grow the chart's own
    // width instead -- the wrapping .bars-scroll takes it from there.
    const scrolling = naturalBarW < MIN_BAR_W;
    const barW = scrolling ? MIN_BAR_W : Math.max(1, naturalBarW);
    const contentW = scrolling ? PAD_L + PAD_R + n * (barW + GAP) - GAP : availW;
    const xs = runs.map((_, i) => PAD_L + i * (barW + GAP));
    const plotH = CHART_H - PAD_T - PAD_B;
    const zeroY = PAD_T + plotH * 0.5;
    const upScale = (plotH * 0.5) / (maxWinStreak || 1);
    const downScale = (plotH * 0.5) / (maxLossStreak || 1);
    return { barW, xs, zeroY, upScale, downScale, contentW, scrolling };
  });

  function barPath(x: number, y: number, w: number, h: number, up: boolean, r: number): string {
    if (h <= 0.5) return "";
    return up
      ? `M${x},${y + r} a${r},${r} 0 0 1 ${r},${-r} h${w - 2 * r} a${r},${r} 0 0 1 ${r},${r} v${h - r} h${-w} Z`
      : `M${x},${y} h${w} v${h - r} a${r},${r} 0 0 1 ${-r},${r} h${-(w - 2 * r)} a${r},${r} 0 0 1 ${-r},${-r} Z`;
  }

  interface Bar extends StreakRun {
    x: number;
    y: number;
    w: number;
    h: number;
    d: string;
    isRecord: boolean;
  }

  const bars = $derived.by((): Bar[] | null => {
    if (!layout) return null;
    const { barW, xs, zeroY, upScale, downScale } = layout;
    return runs.map((r, i) => {
      const up = r.outcome === "win";
      const h = r.length * (up ? upScale : downScale);
      const y = up ? zeroY - h : zeroY;
      const radius = Math.min(3, barW / 2, h);
      const isRecord = up
        ? maxWinStreak > 0 && r.length === maxWinStreak
        : maxLossStreak > 0 && r.length === maxLossStreak;
      return { ...r, x: xs[i], y, w: barW, h, d: barPath(xs[i], y, barW, h, up, radius), isRecord };
    });
  });

  // Only the record streak(s) and the hovered bar keep their numeral once
  // bars get thin enough to scroll -- a wall of "1"s otherwise drowns out
  // the runs actually worth reading.
  function showLabel(bar: Bar, i: number): boolean {
    return hoveredIndex === i || bar.isRecord || !layout?.scrolling || bar.length >= 3;
  }

  let hoveredIndex = $state<number | null>(null);
  let tooltipEl: HTMLDivElement | undefined = $state();
  let barEls: (SVGPathElement | undefined)[] = [];

  function tooltipPos(bar: SVGGraphicsElement | undefined) {
    if (!box || !bar) return null;
    const barRect = bar.getBoundingClientRect();
    const boxRect = box.getBoundingClientRect();
    return { x: barRect.left + barRect.width / 2 - boxRect.left, y: barRect.top - boxRect.top - 8 };
  }
  // hoveredIndex can briefly point past the end of a just-shrunk `runs`
  // (filtering to a hovered bar's own range, a period/group-by change while
  // hovering) -- runs[hoveredIndex] is checked directly rather than trusted
  // to still exist, so a stale index degrades to "no tooltip" instead of a
  // crash reading .start/.end off undefined.
  const tooltip = $derived(
    hoveredIndex === null || !runs[hoveredIndex] ? null : tooltipPos(barEls[hoveredIndex]),
  );

  // Centered on the hovered bar by default (via the CSS translateX(-50%)),
  // which overflows the panel's own clipped bounds for a bar near either
  // edge once there are enough runs to fill the chart -- "All" routinely
  // has 100+. Measured after render (the tooltip's width depends on its
  // content, which changes per bar) and nudged back inside with a small
  // margin, rather than a fixed width guess.
  let edgeOffset = $state(0);
  $effect(() => {
    if (hoveredIndex === null || !tooltipEl || !box) {
      edgeOffset = 0;
      return;
    }
    const boxRect = box.getBoundingClientRect();
    const tipRect = tooltipEl.getBoundingClientRect();
    const margin = 6;
    if (tipRect.left < boxRect.left + margin) {
      edgeOffset = boxRect.left + margin - tipRect.left;
    } else if (tipRect.right > boxRect.right - margin) {
      edgeOffset = boxRect.right - margin - tipRect.right;
    } else {
      edgeOffset = 0;
    }
  });

  function barOpacity(i: number): number {
    if (hoveredIndex !== null) return hoveredIndex === i ? 1 : 0.32;
    if (selectedIndex >= 0) return selectedIndex === i ? 1 : 0.32;
    // Loss runs shorter than the caution line recede so the ones worth
    // reading stand out.
    const r = runs[i];
    if (lossLines.on && r.outcome === "loss" && r.length < lossLines.caution) return 0.62;
    return 1;
  }

  // ---- overview strip -- only shown once the chart is wide enough to
  // scroll, so there's a way to tell there's more history off to the side
  // and to jump straight to it. ----
  const overviewBars = $derived.by(() => {
    if (!runs.length) return null;
    const n = runs.length;
    const gap = 0.5;
    const barW = Math.max(0.5, (availW - gap * (n - 1)) / n);
    const zeroY = OVERVIEW_H * 0.55;
    const upScale = (OVERVIEW_H * 0.45) / (maxWinStreak || 1);
    const downScale = (OVERVIEW_H * 0.45) / (maxLossStreak || 1);
    return runs.map((r, i) => {
      const up = r.outcome === "win";
      const h = Math.max(0.6, r.length * (up ? upScale : downScale));
      const isRecord = up
        ? maxWinStreak > 0 && r.length === maxWinStreak
        : maxLossStreak > 0 && r.length === maxLossStreak;
      return { x: i * (barW + gap), y: up ? zeroY - h : zeroY, w: barW, h, outcome: r.outcome, isRecord };
    });
  });

  let viewStart = $state(0);
  let viewFrac = $state(1);
  function syncViewport() {
    if (!scrollEl) return;
    const sw = scrollEl.scrollWidth || 1;
    viewStart = scrollEl.scrollLeft / sw;
    viewFrac = Math.min(1, scrollEl.clientWidth / sw);
  }

  // Default to the tail of the history -- the current streak is the one
  // thing you always want in view without having to scroll for it -- and
  // re-anchor there whenever the run list itself changes (a new filter or
  // group-by), not on every resize-driven layout recompute. Also drops any
  // hover, since a stale index into the old (larger) `runs` would otherwise
  // point at the wrong bar, or none at all, until the next mousemove.
  $effect(() => {
    runs;
    hoveredIndex = null;
    if (!scrollEl) return;
    requestAnimationFrame(() => {
      if (!scrollEl) return;
      scrollEl.scrollLeft = scrollEl.scrollWidth;
      syncViewport();
    });
  });

  function jumpTo(e: MouseEvent) {
    if (!scrollEl || !overviewEl) return;
    const rect = overviewEl.getBoundingClientRect();
    const frac = (e.clientX - rect.left) / rect.width;
    scrollEl.scrollLeft = frac * scrollEl.scrollWidth - scrollEl.clientWidth / 2;
    syncViewport();
  }

  // Dragging the viewport rectangle itself pans continuously instead of
  // re-jumping on every pixel -- one overview-strip pixel of mouse travel
  // maps to scrollWidth/availW main-chart pixels, since the strip
  // compresses the whole scrollable width down to availW.
  let draggingViewport = $state(false);
  function startDrag(e: MouseEvent) {
    e.stopPropagation();
    if (!scrollEl) return;
    draggingViewport = true;
    const startX = e.clientX;
    const startScrollLeft = scrollEl.scrollLeft;
    const scale = scrollEl.scrollWidth / Math.max(1, availW);
    const onMove = (ev: MouseEvent) => {
      if (!scrollEl) return;
      scrollEl.scrollLeft = startScrollLeft + (ev.clientX - startX) * scale;
      syncViewport();
    };
    const onUp = () => {
      draggingViewport = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  let hoveringViewport = $state(false);
  const viewportLabel = $derived.by(() => {
    if (!runs.length) return "";
    const startIdx = Math.max(0, Math.min(runs.length - 1, Math.floor(viewStart * runs.length)));
    const endIdx = Math.max(startIdx, Math.min(runs.length - 1, Math.ceil((viewStart + viewFrac) * runs.length) - 1));
    return `${fmtDate(runs[startIdx].start)} – ${fmtDate(runs[endIdx].end)}`;
  });
</script>

{#snippet partialToggle()}
  {#if onTogglePartial}
    <button
      type="button"
      class="partial-toggle"
      role="switch"
      aria-checked={includePartial}
      onclick={() => onTogglePartial(!includePartial)}
      title="Count positions that are still open but have already realized some P&L"
    >
      <span class="sw"></span>
      Include partially-closed positions
      <span class="n">· {partialCount} in view</span>
    </button>
  {/if}
{/snippet}

{#snippet lossLinesControls()}
  {#if onLossLinesChange}
    {#if lossLines.on}
      <div class="step">
        <button
          type="button"
          aria-label="Lower caution threshold"
          disabled={lossLines.caution <= 2}
          onclick={() => onLossLinesChange({ ...lossLines, caution: lossLines.caution - 1 })}>−</button
        >
        <span><i class="caution"></i>≥ {lossLines.caution}</span>
        <button
          type="button"
          aria-label="Raise caution threshold"
          disabled={lossLines.caution >= lossLines.alert - 1}
          onclick={() => onLossLinesChange({ ...lossLines, caution: lossLines.caution + 1 })}>+</button
        >
      </div>
      <div class="step">
        <button
          type="button"
          aria-label="Lower alert threshold"
          disabled={lossLines.alert <= lossLines.caution + 1}
          onclick={() => onLossLinesChange({ ...lossLines, alert: lossLines.alert - 1 })}>−</button
        >
        <span><i class="alert"></i>≥ {lossLines.alert}</span>
        <button
          type="button"
          aria-label="Raise alert threshold"
          disabled={lossLines.alert >= maxLossStreak}
          onclick={() => onLossLinesChange({ ...lossLines, alert: lossLines.alert + 1 })}>+</button
        >
      </div>
    {/if}
    <button
      type="button"
      class="partial-toggle"
      role="switch"
      aria-checked={lossLines.on}
      onclick={() => onLossLinesChange({ ...lossLines, on: !lossLines.on })}
      title="Dashed lines at the loss-run lengths that deserve a second look"
    >
      <span class="sw"></span>
      Loss threshold lines
    </button>
  {/if}
{/snippet}

<div class="panel">
  <div class="hd">
    <div class="hd-left">
      <div class="eyebrow">Streak flow</div>
      <div class="title">Consecutive wins &amp; losses</div>
      <div class="caption">
        Each bar is one run of same-outcome positions, in the order they {groupBy === "exit" ? "closed" : "opened"} · height = run length
      </div>
    </div>
    {#if currentRun}
      <div class="hd-right">
        {#if lossLines.on}
          <div class="stat">
            <div class="val caution">{cautionHits}</div>
            <div class="lbl">runs ≥ {lossLines.caution}L</div>
          </div>
          <div class="stat">
            <div class="val alert">{alertHits}</div>
            <div class="lbl">runs ≥ {lossLines.alert}L</div>
          </div>
        {/if}
        <div class="stat">
          <div class="val win">{maxWinStreak}W</div>
          <div class="lbl">longest win streak</div>
        </div>
        <div class="stat">
          <div class="val loss">{maxLossStreak}L</div>
          <div class="lbl">longest loss streak</div>
        </div>
        <div class="stat">
          <div class="val {currentRun.outcome === 'win' ? 'win' : 'loss'}">
            {currentRun.length}{currentRun.outcome === "win" ? "W" : "L"}
          </div>
          <div class="lbl">current streak</div>
        </div>
      </div>
    {/if}
  </div>

  {#if !bars || !layout}
    <div class="empty">No closed positions in this view.</div>
    <div class="legend-row empty-legend"><div class="legend-ctrls">{@render partialToggle()}</div></div>
  {:else}
    <div class="body">
      <div class="bars-box" bind:this={box} bind:clientWidth={availW} onmouseleave={() => (hoveredIndex = null)}>
        <div class="bars-scroll" bind:this={scrollEl} onscroll={syncViewport}>
          <svg
            class="bars-svg"
            width={layout.contentW}
            height={CHART_H}
            viewBox="0 0 {layout.contentW} {CHART_H}"
          >
            <defs>
              {#each ["win", "loss"] as o}
                <pattern
                  id="streak-partial-{o}"
                  width="6"
                  height="6"
                  patternUnits="userSpaceOnUse"
                  patternTransform="rotate(45)"
                >
                  <rect width="6" height="6" fill={o === "win" ? "var(--up)" : "var(--dn)"} />
                  <rect width="2.2" height="6" fill="var(--surface)" opacity="0.5" />
                </pattern>
              {/each}
            </defs>
            {#each runs as r, i (i)}
              <rect
                class="hover-band"
                class:active={hoveredIndex === i}
                x={layout.xs[i] - GAP / 2}
                y={0}
                width={layout.barW + GAP}
                height={CHART_H}
                onmousemove={() => (hoveredIndex = i)}
                onclick={() => selectRun(i)}
              />
            {/each}
            <line class="zero-line" x1={PAD_L} y1={layout.zeroY} x2={layout.contentW - PAD_R} y2={layout.zeroY} />
            {#each bars as bar, i (i)}
              <path
                class="bar-rect"
                d={bar.d}
                fill={bar.partials.length
                  ? `url(#streak-partial-${bar.outcome})`
                  : bar.outcome === "win"
                    ? "var(--up)"
                    : "var(--dn)"}
                style="opacity:{barOpacity(i)}"
                bind:this={barEls[i]}
              />
              {#if i === selectedIndex}
                <path class="bar-selected-ring" d={bar.d} stroke="var(--accent)" />
              {/if}
              {#if showLabel(bar, i)}
                <text
                  class="bar-label"
                  class:record={bar.isRecord}
                  class:alert={lossLines.on && bar.outcome === "loss" && bar.length >= lossLines.alert}
                  x={bar.x + bar.w / 2}
                  y={bar.outcome === "win" ? bar.y - 4 : bar.y + bar.h + 9}
                  text-anchor="middle"
                >
                  {bar.length}
                </text>
              {/if}
            {/each}
            {#if lossLines.on}
              {#each [{ tier: "caution", n: lossLines.caution }, { tier: "alert", n: lossLines.alert }] as t (t.tier)}
                {#if t.n <= maxLossStreak}
                  {@const y = layout.zeroY + t.n * layout.downScale}
                  <line class="thr {t.tier}" x1={PAD_L} y1={y} x2={layout.contentW - PAD_R} y2={y} />
                  {#if !layout.scrolling}
                    <g transform="translate({layout.contentW - PAD_R - 58},{y - 8})">
                      <rect class="thr-tag {t.tier}" width="58" height="16" rx="8" />
                      <text class="thr-tag-text {t.tier}" x="29" y="11.5" text-anchor="middle">{t.n} losses</text>
                    </g>
                  {/if}
                {/if}
              {/each}
            {/if}
            <text class="axis-caption" x={PAD_L} y={CHART_H - 4}>{fmtDate(runs[0].start)}</text>
            <text class="axis-caption" x={layout.contentW - PAD_R} y={CHART_H - 4} text-anchor="end">
              {fmtDate(runs[runs.length - 1].end)}
            </text>
          </svg>
        </div>
        {#if hoveredIndex !== null && tooltip}
          {@const r = runs[hoveredIndex]}
          <div
            class="tooltip show"
            bind:this={tooltipEl}
            style="left:{tooltip.x}px; top:{tooltip.y}px; --edge-offset:{edgeOffset}px"
          >
            <div class="t-title {r.outcome === 'win' ? 'win' : 'loss'}">
              {r.length}
              {r.outcome === "win" ? "consecutive wins" : "consecutive losses"}
            </div>
            <div class="t-sub">
              {fmtDateFull(r.start)}{r.start !== r.end ? ` – ${fmtDateFull(r.end)}` : ""}
            </div>
            <div class="t-sub total {toneOf(r.total)}">{fmtMoney(r.total, currency)} total</div>
            {#if lossLines.on && r.outcome === "loss" && r.length >= lossLines.caution}
              <div class="t-sub {r.length >= lossLines.alert ? 'alert' : 'partial'}">
                {#if r.length >= lossLines.alert}
                  reaches the {lossLines.alert}-loss alert{r.length > lossLines.alert ? ` (+${r.length - lossLines.alert})` : ""}
                {:else}
                  reaches the {lossLines.caution}-loss caution line
                {/if}
              </div>
            {/if}
            {#if r.partials.length}
              <div class="t-sub partial">
                includes {r.partials.length} partial{r.partials.length === 1 ? "" : "s"}: {r.partials.join(", ")}
              </div>
            {/if}
            {#if onSelectRun}
              <div class="t-hint">
                {hoveredIndex === selectedIndex ? "Click to clear this filter" : "Click to filter Positions to this range"}
              </div>
            {/if}
          </div>
        {/if}
      </div>
      {#if layout.scrolling && overviewBars}
        {@const vpX = viewStart * availW}
        {@const vpW = Math.max(2, viewFrac * availW)}
        <div class="overview" bind:this={overviewEl} onmousedown={jumpTo} title="Click to jump, or drag the highlighted range">
          <svg class="overview-svg" width={availW} height={OVERVIEW_H} viewBox="0 0 {availW} {OVERVIEW_H}">
            {#each overviewBars as ob, i (i)}
              <rect
                x={ob.x}
                y={ob.y}
                width={ob.w}
                height={ob.h}
                fill={ob.outcome === "win" ? "var(--up)" : "var(--dn)"}
                opacity={ob.isRecord ? 1 : 0.5}
              />
            {/each}
            <rect
              class="viewport-rect"
              class:dragging={draggingViewport}
              x={vpX}
              y="0"
              width={vpW}
              height={OVERVIEW_H}
              onmousedown={startDrag}
              onmouseenter={() => (hoveringViewport = true)}
              onmouseleave={() => (hoveringViewport = false)}
            />
            {#if draggingViewport || hoveringViewport}
              <rect class="viewport-handle" x={vpX + 2} y={OVERVIEW_H / 2 - 5} width="2" height="10" rx="1" />
              <rect class="viewport-handle" x={vpX + vpW - 4} y={OVERVIEW_H / 2 - 5} width="2" height="10" rx="1" />
            {/if}
          </svg>
          {#if draggingViewport || hoveringViewport}
            <div class="viewport-tooltip" style="left:{vpX + vpW / 2}px">{viewportLabel}</div>
          {/if}
        </div>
      {/if}
      <div class="legend-row">
        <div class="legend-item"><span class="legend-dot" style="background:var(--up)"></span>Win streak</div>
        <div class="legend-item"><span class="legend-dot" style="background:var(--dn)"></span>Loss streak</div>
        {#if lossLines.on}
          <div class="legend-item"><span class="legend-dash caution"></span>Caution<span class="legend-dash alert"></span>Alert</div>
        {/if}
        {#if includePartial && bars.some((b) => b.partials.length)}
          <div class="legend-item"><span class="legend-dot partial"></span>Includes a partial position</div>
        {/if}
        <div class="legend-item muted">
          {layout.scrolling ? "Scroll or click the strip above to explore history · hover" : "Hover"} a bar for its dates,
          length &amp; total P&amp;L
        </div>
        <div class="legend-ctrls">
          {@render lossLinesControls()}
          {@render partialToggle()}
        </div>
      </div>
    </div>
  {/if}
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
    gap: 12px;
    padding: 11px 22px;
    border-bottom: 1px solid var(--border-05);
    flex-wrap: wrap;
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
    margin-top: 2px;
  }
  .hd-right {
    display: flex;
    gap: 18px;
    flex: none;
  }
  .stat {
    text-align: right;
  }
  .stat .val {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    font-variant-numeric: tabular-nums;
  }
  .stat .val.win {
    color: var(--up);
  }
  .stat .val.loss {
    color: var(--dn);
  }
  .stat .lbl {
    font-size: var(--text-2xs);
    color: var(--dim-45);
    margin-top: 1px;
  }

  .body {
    padding: 12px 22px 14px;
  }
  .bars-box {
    position: relative;
  }
  .bars-scroll {
    overflow-x: auto;
    overflow-y: hidden;
    scrollbar-width: thin;
  }
  .bars-scroll::-webkit-scrollbar {
    height: 6px;
  }
  .bars-scroll::-webkit-scrollbar-thumb {
    background: var(--border-12);
    border-radius: 3px;
  }
  .bars-svg {
    display: block;
  }
  .bar-rect {
    transition: opacity 0.12s;
    pointer-events: none;
  }
  .bar-selected-ring {
    fill: none;
    stroke-width: 1.6;
    pointer-events: none;
  }
  .hover-band {
    fill: transparent;
    cursor: pointer;
    transition: fill 0.12s;
  }
  .hover-band.active {
    fill: var(--accent-bg);
  }
  .zero-line {
    stroke: var(--border-12);
    stroke-width: 1;
  }
  .bar-label {
    font-size: 10px;
    font-weight: var(--weight-bold);
    font-variant-numeric: tabular-nums;
    fill: var(--text);
  }
  .bar-label.record {
    font-size: 11px;
  }
  .axis-caption {
    font-size: 12px;
    font-weight: var(--weight-medium);
    fill: var(--dim-45);
  }

  .overview {
    position: relative;
    margin-top: 8px;
    border-radius: 4px;
    background: var(--surface-alt);
    cursor: pointer;
  }
  .overview-svg {
    display: block;
    border-radius: 4px;
    overflow: hidden;
  }
  .viewport-rect {
    fill: var(--accent-bg);
    stroke: var(--accent);
    stroke-width: 1;
    cursor: grab;
  }
  .viewport-rect.dragging {
    cursor: grabbing;
  }
  .viewport-handle {
    fill: var(--accent);
    pointer-events: none;
  }
  .viewport-tooltip {
    position: absolute;
    bottom: calc(100% + 6px);
    transform: translateX(-50%);
    background: var(--text);
    color: var(--surface);
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    padding: 4px 8px;
    border-radius: var(--radius-md);
    white-space: nowrap;
    pointer-events: none;
    z-index: 5;
  }

  .tooltip {
    position: absolute;
    pointer-events: none;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 8px 11px;
    font-size: var(--text-xs);
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.12);
    /* Centered on the bar by default; edgeOffset (set in JS after
       measuring the rendered tooltip) nudges it back inside the panel
       when that centering would push it past either edge. */
    --edge-offset: 0px;
    transform: translate(calc(-50% + var(--edge-offset)), -100%);
    white-space: nowrap;
    z-index: 5;
  }
  .tooltip .t-title {
    font-weight: var(--weight-semibold);
    margin-bottom: 3px;
  }
  .tooltip .t-title.win {
    color: var(--up);
  }
  .tooltip .t-title.loss {
    color: var(--dn);
  }
  .tooltip .t-sub {
    color: var(--dim-45);
    font-size: var(--text-2xs);
    margin-top: 2px;
  }
  .tooltip .t-sub.total {
    font-weight: var(--weight-semibold);
  }
  .tooltip .t-sub.partial {
    color: var(--amber);
  }
  .tooltip .t-sub.total.pos {
    color: var(--up);
  }
  .tooltip .t-sub.total.neg {
    color: var(--dn);
  }
  .tooltip .t-hint {
    color: var(--accent);
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px dashed var(--accent-bg);
  }

  .legend-row {
    display: flex;
    gap: 16px;
    margin-top: 8px;
    flex-wrap: wrap;
  }
  .legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: var(--text-2xs);
    color: var(--dim-55);
  }
  .legend-item.muted {
    color: var(--dim-45);
  }
  .legend-dot.partial {
    background: repeating-linear-gradient(135deg, var(--up) 0 2px, var(--surface) 2px 4px);
    outline: 1px solid var(--border-08);
  }
  .empty-legend {
    padding: 0 22px 14px;
  }
  .legend-ctrls {
    margin-left: auto;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .legend-dash {
    width: 16px;
    border-top: 1.5px dashed;
    margin-left: 4px;
  }
  .legend-dash.caution,
  .thr.caution {
    stroke: var(--yellow);
    border-color: var(--yellow);
  }
  .legend-dash.alert,
  .thr.alert {
    stroke: var(--over);
    border-color: var(--over);
  }
  .thr {
    stroke-width: 1.25;
    stroke-dasharray: 5 4;
    pointer-events: none;
  }
  .thr-tag.caution {
    fill: var(--yellow);
  }
  .thr-tag.alert {
    fill: var(--over);
  }
  .thr-tag-text {
    font-size: 10px;
    font-weight: 600;
    pointer-events: none;
  }
  .thr-tag-text.caution {
    fill: #3b2f00;
  }
  .thr-tag-text.alert {
    fill: #fff;
  }
  .stat .val.caution {
    color: var(--yellow);
  }
  .stat .val.alert {
    color: var(--over);
  }
  .bar-label.alert {
    fill: var(--dn);
    font-size: 11px;
  }
  .tooltip .t-sub.alert {
    color: var(--over);
  }
  .step {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    padding: 2px;
    border: 1px solid var(--border-12);
    border-radius: 99px;
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
  }
  .step span {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 0 6px;
    font-variant-numeric: tabular-nums;
  }
  .step i {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }
  .step i.caution {
    background: var(--yellow);
  }
  .step i.alert {
    background: var(--over);
  }
  .step button {
    width: 20px;
    height: 20px;
    border: 0;
    border-radius: 50%;
    background: var(--surface-04);
    color: var(--text);
    font: inherit;
    font-weight: 600;
    line-height: 1;
    cursor: pointer;
  }
  .step button:disabled {
    opacity: 0.35;
    cursor: default;
  }
  .step button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .partial-toggle {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 3px 11px 3px 6px;
    border: 1px solid var(--border-12);
    border-radius: 99px;
    background: var(--surface);
    color: var(--text);
    font: inherit;
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    cursor: pointer;
  }
  .partial-toggle:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .partial-toggle .n {
    color: var(--dim-45);
    font-weight: 400;
  }
  .partial-toggle .sw {
    width: 26px;
    height: 15px;
    border-radius: 99px;
    background: var(--border-12);
    position: relative;
    flex: none;
    transition: background 0.15s;
  }
  .partial-toggle .sw::after {
    content: "";
    position: absolute;
    top: 2px;
    left: 2px;
    width: 11px;
    height: 11px;
    border-radius: 50%;
    background: #fff;
    transition: transform 0.15s;
  }
  .partial-toggle[aria-checked="true"] .sw {
    background: var(--accent);
  }
  .partial-toggle[aria-checked="true"] .sw::after {
    transform: translateX(11px);
  }
  .legend-dot {
    width: 8px;
    height: 8px;
    border-radius: 2px;
    flex: none;
  }

  .empty {
    color: var(--dim-55);
    text-align: center;
    padding: 40px 0;
    font-size: var(--text-sm);
  }
</style>
