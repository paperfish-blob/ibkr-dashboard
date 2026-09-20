<script lang="ts">
  /**
   * One diverging bar per run of consecutive same-outcome positions, in the
   * order they actually closed -- a win streak climbs up in green, a loss
   * streak drops down in red, and the bar's height is the streak length.
   * Same visual grammar as the P&L bar charts elsewhere in the app, just
   * one bar per run instead of one per month.
   */
  import { fmtMoney, toneOf } from "$lib/format";

  export interface StreakRun {
    outcome: "win" | "loss";
    length: number;
    start: string; // "YYYY-MM-DD", first position in the run
    end: string; // "YYYY-MM-DD", last position in the run
    total: number; // summed realized P&L across the run
  }

  interface Props {
    runs: StreakRun[];
    currency?: string;
  }
  let { runs, currency = "USD" }: Props = $props();

  const maxWinStreak = $derived(Math.max(0, ...runs.filter((r) => r.outcome === "win").map((r) => r.length)));
  const maxLossStreak = $derived(Math.max(0, ...runs.filter((r) => r.outcome === "loss").map((r) => r.length)));
  const currentRun = $derived(runs.length ? runs[runs.length - 1] : null);

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
  const CHART_W = 860;
  const PAD_L = 6;
  const PAD_R = 6;
  const PAD_T = 10;
  const PAD_B = 16;
  const GAP = 4;
  const CHART_H = 96;

  const layout = $derived.by(() => {
    if (!runs.length) return null;
    const n = runs.length;
    const plotW = CHART_W - PAD_L - PAD_R;
    const barW = Math.max(2, (plotW - GAP * (n - 1)) / n);
    const xs = runs.map((_, i) => PAD_L + i * (barW + GAP));
    const plotH = CHART_H - PAD_T - PAD_B;
    const zeroY = PAD_T + plotH * 0.5;
    const upScale = (plotH * 0.5) / (maxWinStreak || 1);
    const downScale = (plotH * 0.5) / (maxLossStreak || 1);
    return { barW, xs, zeroY, upScale, downScale };
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
  }

  const bars = $derived.by((): Bar[] | null => {
    if (!layout) return null;
    const { barW, xs, zeroY, upScale, downScale } = layout;
    return runs.map((r, i) => {
      const up = r.outcome === "win";
      const h = r.length * (up ? upScale : downScale);
      const y = up ? zeroY - h : zeroY;
      return { ...r, x: xs[i], y, w: barW, h };
    });
  });

  let hoveredIndex = $state<number | null>(null);
  let box: HTMLDivElement | undefined = $state();
  let tooltipEl: HTMLDivElement | undefined = $state();
  let barEls: (SVGPathElement | undefined)[] = [];

  function tooltipPos(bar: SVGGraphicsElement | undefined) {
    if (!box || !bar) return null;
    const barRect = bar.getBoundingClientRect();
    const boxRect = box.getBoundingClientRect();
    return { x: barRect.left + barRect.width / 2 - boxRect.left, y: barRect.top - boxRect.top - 8 };
  }
  const tooltip = $derived(hoveredIndex === null ? null : tooltipPos(barEls[hoveredIndex]));

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
    return hoveredIndex === null || hoveredIndex === i ? 1 : 0.32;
  }
</script>

<div class="panel">
  <div class="hd">
    <div class="hd-left">
      <div class="eyebrow">Streak flow</div>
      <div class="title">Consecutive wins &amp; losses</div>
      <div class="caption">
        Each bar is one run of same-outcome positions, in the order they closed · height = run length
      </div>
    </div>
    {#if currentRun}
      <div class="hd-right">
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
  {:else}
    <div class="body">
      <div class="bars-box" bind:this={box} onmouseleave={() => (hoveredIndex = null)}>
        <svg class="bars-svg" viewBox="0 0 {CHART_W} {CHART_H}" preserveAspectRatio="xMidYMid meet">
          {#each runs as r, i (i)}
            <rect
              class="hover-band"
              class:active={hoveredIndex === i}
              x={layout.xs[i] - GAP / 2}
              y={0}
              width={layout.barW + GAP}
              height={CHART_H}
              onmousemove={() => (hoveredIndex = i)}
            />
          {/each}
          <line class="zero-line" x1={PAD_L} y1={layout.zeroY} x2={CHART_W - PAD_R} y2={layout.zeroY} />
          {#each bars as bar, i (i)}
            <path
              class="bar-rect"
              d={barPath(bar.x, bar.y, bar.w, bar.h, bar.outcome === "win", Math.min(3, bar.w / 2, bar.h))}
              fill={bar.outcome === "win" ? "var(--up)" : "var(--dn)"}
              style="opacity:{barOpacity(i)}"
              bind:this={barEls[i]}
            />
            <text
              class="bar-label"
              x={bar.x + bar.w / 2}
              y={bar.outcome === "win" ? bar.y - 4 : bar.y + bar.h + 9}
              text-anchor="middle"
            >
              {bar.length}
            </text>
          {/each}
          <text class="axis-caption" x={PAD_L} y={CHART_H - 4}>{fmtDate(runs[0].start)}</text>
          <text class="axis-caption" x={CHART_W - PAD_R} y={CHART_H - 4} text-anchor="end">
            {fmtDate(runs[runs.length - 1].end)}
          </text>
        </svg>
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
          </div>
        {/if}
      </div>
      <div class="legend-row">
        <div class="legend-item"><span class="legend-dot" style="background:var(--up)"></span>Win streak</div>
        <div class="legend-item"><span class="legend-dot" style="background:var(--dn)"></span>Loss streak</div>
        <div class="legend-item muted">Hover a bar for its dates, length &amp; total P&amp;L</div>
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
  .bars-svg {
    width: 100%;
    height: auto;
    display: block;
    overflow: visible;
  }
  .bar-rect {
    transition: opacity 0.12s;
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
    font-size: 7px;
    font-weight: var(--weight-bold);
    font-variant-numeric: tabular-nums;
    fill: var(--text);
  }
  .axis-caption {
    font-size: 9px;
    font-weight: var(--weight-medium);
    fill: var(--dim-45);
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
  .tooltip .t-sub.total.pos {
    color: var(--up);
  }
  .tooltip .t-sub.total.neg {
    color: var(--dn);
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
