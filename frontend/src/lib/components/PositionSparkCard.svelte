<script lang="ts">
  /**
   * One card in Open Positions' "Potential P&L by position" grid -- pulled
   * out of PotentialPnlPanel so its hover state (which point along its own
   * sparkline the cursor is over) is local to each card, not a map keyed by
   * symbol living in the parent. Hovering shows the same date/value/open/
   * close a chart tooltip would, just for this tiny hand-drawn line rather
   * than a full Chart.js instance -- one per card would be far too heavy
   * for a grid that can hold every open position at once.
   */
  import { positionDetailParams } from "$lib/api";
  import { fmtDay, fmtDayYear, fmtMoney, fmtPriceLike, toneOf, EM_DASH } from "$lib/format";
  import type { PositionSeries } from "./PotentialPnlPanel.svelte";

  interface Props {
    p: PositionSeries;
    currency?: string;
  }
  let { p, currency = "USD" }: Props = $props();

  const last = $derived(p.series.at(-1)?.value ?? 0);
  const prev = $derived(p.series.length > 1 ? p.series[p.series.length - 2].value : null);

  function cssVar(name: string): string {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function toRgba(varName: string, alpha: number): string {
    return `rgba(${cssVar(varName)}, ${alpha})`;
  }

  const VIEW_W = 300;
  const VIEW_H = 90;
  const PAD_BOTTOM = 6;
  const PLOT_H = 78;

  // One id suffix per card instance -- several of these cards render on the
  // same page at once, and SVG clipPath ids have to be unique in the DOM or
  // every card's clip starts referencing whichever one happened to render
  // last.
  const uid = Math.random().toString(36).slice(2);

  // Domain always includes 0, even for a series that's e.g. entirely
  // negative -- that's what makes yZero (below) a real point on the chart
  // rather than an extrapolation, so the zero-crossing coloring and the
  // reference line land where they actually should.
  const shape = $derived.by(() => {
    const series = p.series;
    if (series.length === 0) return null;
    const values = series.map((pt) => pt.value);
    const min = Math.min(0, ...values);
    const max = Math.max(0, ...values);
    const span = max - min || 1;
    const n = series.length;
    const xOf = (i: number) => (n === 1 ? 0 : (i / (n - 1)) * VIEW_W);
    const yOf = (v: number) => VIEW_H - PAD_BOTTOM - ((v - min) / span) * PLOT_H;
    const yZero = yOf(0);
    const path = series
      .map((pt, i) => `${i === 0 ? "M" : "L"}${xOf(i).toFixed(1)},${yOf(pt.value).toFixed(1)}`)
      .join(" ");
    // The line, closed back along the zero baseline rather than the chart's
    // bottom edge -- fill above zero reads as "how far up", fill below
    // reads as "how far down", instead of both filling to the floor.
    const areaPath = `${path} L${xOf(n - 1).toFixed(1)},${yZero.toFixed(1)} L${xOf(0).toFixed(1)},${yZero.toFixed(1)} Z`;
    return { path, areaPath, xOf, yOf, yZero, n };
  });

  let containerEl = $state<HTMLDivElement | undefined>();
  let tooltipEl = $state<HTMLDivElement | undefined>();
  let hoverIndex = $state<number | null>(null);

  function handleMove(e: PointerEvent) {
    if (!containerEl || !shape) return;
    const rect = containerEl.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    hoverIndex = shape.n === 1 ? 0 : Math.round(frac * (shape.n - 1));
  }
  function handleLeave() {
    hoverIndex = null;
  }

  const hoverPoint = $derived(hoverIndex !== null ? (p.series[hoverIndex] ?? null) : null);
  const hoverXY = $derived(
    hoverIndex !== null && shape ? { x: shape.xOf(hoverIndex), y: shape.yOf(p.series[hoverIndex].value) } : null,
  );

  // Same edge-clamping approach as Streak Flow's tooltip -- centered on the
  // hovered point by default, nudged back inside the card only once it's
  // actually measured as overflowing either side.
  let edgeOffset = $state(0);
  $effect(() => {
    if (hoverIndex === null || !tooltipEl || !containerEl) {
      edgeOffset = 0;
      return;
    }
    const boxRect = containerEl.getBoundingClientRect();
    const tipRect = tooltipEl.getBoundingClientRect();
    const margin = 4;
    if (tipRect.left < boxRect.left + margin) {
      edgeOffset = boxRect.left + margin - tipRect.left;
    } else if (tipRect.right > boxRect.right - margin) {
      edgeOffset = boxRect.right - margin - tipRect.right;
    } else {
      edgeOffset = 0;
    }
  });
</script>

<a class="card" href="/positions/detail?{positionDetailParams(p.row.p)}" target="_blank" rel="noopener">
  <div class="card-top">
    <span class="card-sym">{p.row.p.symbol}</span>
    <span class="card-range">{p.row.p.open_date ? fmtDayYear(p.row.p.open_date) : EM_DASH} &rarr; today</span>
  </div>
  <div class="card-pnl {toneOf(last)}">{fmtMoney(last, currency)}</div>
  {#if prev !== null}
    <div class="card-today {toneOf(last - prev)}">{fmtMoney(last - prev, currency)} today</div>
  {/if}
  <div class="card-sub">
    {p.row.status === "full" ? "Open (Full)" : "Open (Partial)"}
    {#if p.row.interim !== null}
      &middot; includes {fmtMoney(p.row.interim, currency)} already realized
    {/if}
  </div>
  {#if shape}
    <div
      class="spark"
      bind:this={containerEl}
      onpointermove={handleMove}
      onpointerleave={handleLeave}
      role="img"
      aria-label="Potential P&L sparkline for {p.row.p.symbol}"
    >
      <svg viewBox="0 0 {VIEW_W} {VIEW_H}" preserveAspectRatio="none">
        <defs>
          <clipPath id="spark-above-{uid}"><rect x="0" y="0" width={VIEW_W} height={shape.yZero} /></clipPath>
          <clipPath id="spark-below-{uid}"><rect x="0" y={shape.yZero} width={VIEW_W} height={VIEW_H - shape.yZero} /></clipPath>
        </defs>
        <path d={shape.areaPath} fill={cssVar("--up-bg")} clip-path="url(#spark-above-{uid})" />
        <path d={shape.areaPath} fill={cssVar("--dn-bg")} clip-path="url(#spark-below-{uid})" />
        <line x1="0" x2={VIEW_W} y1={shape.yZero} y2={shape.yZero} stroke={toRgba("--ink-rgb", 0.12)} stroke-width="1" stroke-dasharray="2,2" />
        <path d={shape.path} fill="none" stroke={cssVar("--up")} stroke-width="1.6" clip-path="url(#spark-above-{uid})" />
        <path d={shape.path} fill="none" stroke={cssVar("--dn")} stroke-width="1.6" clip-path="url(#spark-below-{uid})" />
        {#if hoverXY}
          <line
            x1={hoverXY.x}
            x2={hoverXY.x}
            y1={VIEW_H - PAD_BOTTOM}
            y2={VIEW_H - PAD_BOTTOM - PLOT_H}
            stroke={toRgba("--ink-rgb", 0.15)}
            stroke-width="1"
          />
          <circle
            cx={hoverXY.x}
            cy={hoverXY.y}
            r="3"
            fill={cssVar(hoverPoint && hoverPoint.value >= 0 ? "--up" : "--dn")}
            stroke={cssVar("--surface")}
            stroke-width="1.5"
          />
        {/if}
      </svg>
      {#if hoverPoint && hoverXY}
        <div
          class="spark-tip"
          bind:this={tooltipEl}
          style="left:{(hoverXY.x / VIEW_W) * 100}%; --edge-offset:{edgeOffset}px"
        >
          <div class="tip-date">{fmtDay(hoverPoint.date)}</div>
          <div class="tip-val {toneOf(hoverPoint.value)}">{fmtMoney(hoverPoint.value, currency)}</div>
          <div class="tip-oc">Open: {fmtPriceLike(hoverPoint.open, currency, 2)}</div>
          <div class="tip-oc">Close: {fmtPriceLike(hoverPoint.close, currency, 2)}</div>
        </div>
      {/if}
    </div>
  {/if}
  <div class="card-foot">
    <span>{p.row.p.open_date ? fmtDayYear(p.row.p.open_date) : EM_DASH}</span>
    <span>{p.row.daysHeld !== null && p.row.daysHeld < 30 ? `Today (${p.row.daysHeld}d)` : "Today"}</span>
  </div>
</a>

<style>
  .card {
    background: var(--surface);
    padding: 16px 18px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    text-decoration: none;
    color: inherit;
    position: relative;
  }
  .card:hover {
    background: var(--surface-02);
    z-index: 1;
  }
  .card-top {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
  }
  .card-sym {
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    color: var(--text);
  }
  .card-range {
    font-size: 9.5px;
    color: var(--dim-45);
    white-space: nowrap;
  }
  .card-pnl {
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
    letter-spacing: -0.01em;
  }
  .card-pnl.pos {
    color: var(--up);
  }
  .card-pnl.neg {
    color: var(--dn);
  }
  .card-pnl.flat {
    color: var(--text);
  }
  .card-today {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    margin-top: -3px;
  }
  .card-today.pos {
    color: var(--up);
  }
  .card-today.neg {
    color: var(--dn);
  }
  .card-today.flat {
    color: var(--dim-55);
  }
  .card-sub {
    font-size: var(--text-2xs);
    color: var(--dim-55);
  }
  .spark {
    margin-top: 4px;
    position: relative;
    cursor: crosshair;
  }
  .spark svg {
    display: block;
    width: 100%;
    height: 68px;
  }
  .spark-tip {
    position: absolute;
    top: -6px;
    pointer-events: none;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 6px 9px;
    font-size: var(--text-2xs);
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.12);
    --edge-offset: 0px;
    transform: translate(calc(-50% + var(--edge-offset)), -100%);
    white-space: nowrap;
    z-index: 5;
  }
  .tip-date {
    font-weight: var(--weight-semibold);
    color: var(--dim-55);
    margin-bottom: 2px;
  }
  .tip-val {
    font-weight: var(--weight-bold);
  }
  .tip-val.pos {
    color: var(--up);
  }
  .tip-val.neg {
    color: var(--dn);
  }
  .tip-val.flat {
    color: var(--text);
  }
  .tip-oc {
    color: var(--dim-55);
    margin-top: 1px;
  }
  .card-foot {
    display: flex;
    justify-content: space-between;
    font-size: 9.5px;
    color: var(--dim-45);
    margin-top: 2px;
  }
</style>
