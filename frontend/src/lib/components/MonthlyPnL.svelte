<script lang="ts">
  /**
   * Monthly realized P&L, paired with a monthly trade-count chart directly
   * below it sharing the same month columns -- so a tall bar in one lines
   * up with its counterpart in the other. Two separate single-axis charts,
   * not one chart with two y-axes (P&L and trade count have unrelated
   * scales; a shared axis would mislead). A tile grid with both numbers per
   * month sits below that. All three read from the same daily `series` the
   * Overview page's cumulative chart already fetches -- bucketed by month
   * client side, the way the position detail page's period tiles bucket by
   * trading-day offset.
   */
  import { fmtMoney, num, toneOf } from "$lib/format";
  import type { CumulativePoint } from "$lib/api";

  interface Props {
    series: CumulativePoint[];
    currency?: string;
    /** Fired with the hovered month's "YYYY-MM" key (or null on clear) --
     *  lets a sibling chart elsewhere on the page (e.g. an index benchmark)
     *  sync its own highlight to the same month. */
    onHoverMonth?: (monthKey: string | null) => void;
  }
  let { series, currency = "USD", onHoverMonth }: Props = $props();

  interface MonthBucket {
    key: string; // "2026-06", sorts chronologically as a string
    label: string; // "Jun 2026"
    total: number;
    trades: number;
  }

  const months = $derived.by((): MonthBucket[] => {
    const buckets = new Map<string, MonthBucket>();
    for (const p of series) {
      const key = p.date.slice(0, 7);
      let b = buckets.get(key);
      if (!b) {
        const [y, m] = key.split("-").map(Number);
        const label = new Date(y, m - 1, 1).toLocaleDateString("en-US", { month: "short", year: "numeric" });
        b = { key, label, total: 0, trades: 0 };
        buckets.set(key, b);
      }
      b.total += num(p.realized_pnl);
      b.trades += p.trade_count;
    }
    return [...buckets.values()].sort((a, b) => a.key.localeCompare(b.key));
  });

  const grandTotal = $derived(months.reduce((sum, m) => sum + m.total, 0));
  const totalTrades = $derived(months.reduce((sum, m) => sum + m.trades, 0));

  // ---- shared bar geometry -- both charts use the same x/width per month
  // so their columns line up exactly. ----
  const CHART_W = 860;
  const PAD_L = 6;
  const PAD_R = 6;
  const BAR_GAP = 10;

  const barLayout = $derived.by(() => {
    if (!months.length) return null;
    const plotW = CHART_W - PAD_L - PAD_R;
    const n = months.length;
    const barW = Math.max(2, (plotW - BAR_GAP * (n - 1)) / n);
    const xs = months.map((_, i) => PAD_L + i * (barW + BAR_GAP));
    // A "+$1,234.56" label needs roughly 60px of clear width either side of
    // its bar; below that they start overlapping their neighbors (this is
    // what happens across a multi-year "All" view with 40+ months), so drop
    // to hover-only rather than render illegible overlapping text.
    const showValueLabels = barW >= 50;
    // Cap visible month ticks the same way CumulativeChart caps its x-axis
    // (maxTicksLimit), so month labels don't crowd either at high counts.
    const monthLabelEvery = Math.max(1, Math.ceil(n / 24));
    return { barW, xs, showValueLabels, monthLabelEvery };
  });

  function barPath(x: number, y: number, w: number, h: number, up: boolean, r: number): string {
    if (h <= 0.5) return "";
    return up
      ? `M${x},${y + r} a${r},${r} 0 0 1 ${r},${-r} h${w - 2 * r} a${r},${r} 0 0 1 ${r},${r} v${h - r} h${-w} Z`
      : `M${x},${y} h${w} v${h - r} a${r},${r} 0 0 1 ${-r},${r} h${-(w - 2 * r)} a${r},${r} 0 0 1 ${-r},${-r} Z`;
  }

  // ---- P&L bars (diverging around zero) ----
  const PNL_H = 190;
  const PNL_PAD_TOP = 24;
  const PNL_PAD_BOTTOM = 34;

  interface PnlBar extends MonthBucket {
    x: number;
    y: number;
    w: number;
    h: number;
    up: boolean;
    path: string;
    labelY: number;
  }

  const pnlBars = $derived.by((): { bars: PnlBar[]; zeroY: number } | null => {
    if (!months.length || !barLayout) return null;
    const { barW, xs } = barLayout;
    const plotH = PNL_H - PNL_PAD_TOP - PNL_PAD_BOTTOM;
    const zeroY = PNL_PAD_TOP + plotH * 0.6;
    const maxUp = Math.max(0, ...months.map((m) => Math.max(m.total, 0)));
    const maxDown = Math.max(0, ...months.map((m) => Math.max(-m.total, 0)));
    const upScale = (plotH * 0.6) / (maxUp || 1);
    const downScale = (plotH * 0.4) / (maxDown || 1);

    const out: PnlBar[] = months.map((m, i) => {
      const x = xs[i];
      const up = m.total >= 0;
      const h = Math.abs(up ? m.total * upScale : m.total * downScale);
      const y = up ? zeroY - h : zeroY;
      const r = Math.min(4, barW / 2, h);
      return {
        ...m,
        x,
        y,
        w: barW,
        h,
        up,
        path: barPath(x, y, barW, h, up, r),
        labelY: up ? y - 6 : y + h + 12,
      };
    });
    return { bars: out, zeroY };
  });

  // ---- trade-count bars (magnitude only, single hue, rise from a
  // baseline of 0 -- never negative) ----
  const TRADES_H = 130;
  const TRADES_PAD_TOP = 22;
  const TRADES_PAD_BOTTOM = 22;

  interface TradesBar extends MonthBucket {
    x: number;
    y: number;
    w: number;
    h: number;
    path: string;
  }

  const tradesBars = $derived.by((): { bars: TradesBar[]; baseY: number } | null => {
    if (!months.length || !barLayout) return null;
    const { barW, xs } = barLayout;
    const plotH = TRADES_H - TRADES_PAD_TOP - TRADES_PAD_BOTTOM;
    const baseY = TRADES_H - TRADES_PAD_BOTTOM;
    const maxTrades = Math.max(1, ...months.map((m) => m.trades));
    const scale = plotH / maxTrades;

    const out: TradesBar[] = months.map((m, i) => {
      const x = xs[i];
      const h = m.trades * scale;
      const y = baseY - h;
      const r = Math.min(4, barW / 2, h);
      return { ...m, x, y, w: barW, h, path: barPath(x, y, barW, h, true, r) };
    });
    return { bars: out, baseY };
  });

  // Hovering a month bar in either chart highlights that month in BOTH
  // (dims the rest) and shows both tooltips -- comparing P&L to trade count
  // for one month then needs a single hover, not two. Keyed by index into
  // `months` rather than by bar object, since that's the one thing both
  // charts' bars share.
  let hoveredIndex = $state<number | null>(null);
  let pnlBox: HTMLDivElement | undefined = $state();
  let tradesBox: HTMLDivElement | undefined = $state();
  let pnlBarEls: (SVGPathElement | undefined)[] = [];
  let tradesBarEls: (SVGPathElement | undefined)[] = [];

  function barOpacity(i: number): number {
    return hoveredIndex === null || hoveredIndex === i ? 1 : 0.32;
  }

  function setHoveredIndex(i: number | null) {
    hoveredIndex = i;
    onHoverMonth?.(i === null ? null : months[i].key);
  }

  function tooltipPos(box: HTMLDivElement | undefined, bar: SVGPathElement | undefined) {
    if (!box || !bar) return null;
    const barRect = bar.getBoundingClientRect();
    const boxRect = box.getBoundingClientRect();
    return { x: barRect.left + barRect.width / 2 - boxRect.left, y: barRect.top - boxRect.top - 10 };
  }

  const pnlTooltip = $derived(hoveredIndex === null ? null : tooltipPos(pnlBox, pnlBarEls[hoveredIndex]));
  const tradesTooltip = $derived(hoveredIndex === null ? null : tooltipPos(tradesBox, tradesBarEls[hoveredIndex]));
</script>

<div class="panel">
  <div class="hd">
    <div class="hd-left">
      <div class="eyebrow">By month</div>
      <div class="title">Monthly P&amp;L &amp; trade count</div>
      <div class="caption">Gross, before commission · Flex trades only, bucketed from the daily series above</div>
    </div>
    <div class="hd-right">
      <div class="val {toneOf(grandTotal)}">{fmtMoney(grandTotal, currency)}</div>
      <div class="sub">{totalTrades} trade{totalTrades === 1 ? "" : "s"}</div>
    </div>
  </div>

  {#if !pnlBars || !tradesBars || !barLayout}
    <div class="empty">No realizing trades in this statement period.</div>
  {:else}
    <div class="body">
      <div class="sub-title">Realized P&amp;L</div>
      <div class="bars-box" bind:this={pnlBox} onmouseleave={() => setHoveredIndex(null)}>
        <svg class="bars-svg" viewBox="0 0 {CHART_W} {PNL_H}" preserveAspectRatio="xMidYMid meet">
          {#each months as m, i (m.key)}
            <rect
              class="hover-band"
              class:active={hoveredIndex === i}
              x={barLayout.xs[i] - BAR_GAP / 2}
              y={0}
              width={barLayout.barW + BAR_GAP}
              height={PNL_H}
              onmousemove={() => setHoveredIndex(i)}
            />
          {/each}
          <line class="zero-line" x1={PAD_L} y1={pnlBars.zeroY} x2={CHART_W - PAD_R} y2={pnlBars.zeroY} />
          {#each pnlBars.bars as bar, i (bar.key)}
            <path
              class="bar-rect"
              d={bar.path}
              fill={bar.up ? "var(--up)" : "var(--dn)"}
              style="opacity:{barOpacity(i)}"
              bind:this={pnlBarEls[i]}
            />
            {#if barLayout.showValueLabels}
              <text class="bar-label" x={bar.x + bar.w / 2} y={bar.labelY} text-anchor="middle">
                {fmtMoney(bar.total, currency)}
              </text>
            {/if}
            {#if i % barLayout.monthLabelEvery === 0}
              <text class="bar-month" x={bar.x + bar.w / 2} y={PNL_H - 6} text-anchor="middle">
                {bar.label.split(" ")[0]}
              </text>
            {/if}
          {/each}
        </svg>
        {#if hoveredIndex !== null && pnlTooltip}
          <div class="tooltip show" style="left:{pnlTooltip.x}px; top:{pnlTooltip.y}px">
            <div class="t-month">{months[hoveredIndex].label}</div>
            <div class="t-val {toneOf(months[hoveredIndex].total)}">{fmtMoney(months[hoveredIndex].total, currency)}</div>
            <div class="t-sub">
              {months[hoveredIndex].trades} trade{months[hoveredIndex].trades === 1 ? "" : "s"}
            </div>
          </div>
        {/if}
      </div>
    </div>

    <div class="divider"></div>

    <div class="body">
      <div class="sub-title">Trade count</div>
      <div class="bars-box" bind:this={tradesBox} onmouseleave={() => setHoveredIndex(null)}>
        <svg class="bars-svg" viewBox="0 0 {CHART_W} {TRADES_H}" preserveAspectRatio="xMidYMid meet">
          {#each months as m, i (m.key)}
            <rect
              class="hover-band"
              class:active={hoveredIndex === i}
              x={barLayout.xs[i] - BAR_GAP / 2}
              y={0}
              width={barLayout.barW + BAR_GAP}
              height={TRADES_H}
              onmousemove={() => setHoveredIndex(i)}
            />
          {/each}
          <line class="base-line" x1={PAD_L} y1={tradesBars.baseY} x2={CHART_W - PAD_R} y2={tradesBars.baseY} />
          {#each tradesBars.bars as bar, i (bar.key)}
            <path
              class="bar-rect"
              d={bar.path}
              fill="var(--accent)"
              style="opacity:{barOpacity(i)}"
              bind:this={tradesBarEls[i]}
            />
            {#if barLayout.showValueLabels}
              <text class="bar-label muted" x={bar.x + bar.w / 2} y={bar.y - 6} text-anchor="middle">
                {bar.trades}
              </text>
            {/if}
            {#if i % barLayout.monthLabelEvery === 0}
              <text class="bar-month" x={bar.x + bar.w / 2} y={TRADES_H - 6} text-anchor="middle">
                {bar.label.split(" ")[0]}
              </text>
            {/if}
          {/each}
        </svg>
        {#if hoveredIndex !== null && tradesTooltip}
          <div class="tooltip show" style="left:{tradesTooltip.x}px; top:{tradesTooltip.y}px">
            <div class="t-month">{months[hoveredIndex].label}</div>
            <div class="t-val neutral">
              {months[hoveredIndex].trades} trade{months[hoveredIndex].trades === 1 ? "" : "s"}
            </div>
          </div>
        {/if}
      </div>
    </div>

    <div class="divider"></div>

    <div class="body">
      <div class="tiles">
        {#each months as m (m.key)}
          <div class="tile">
            <div class="tile-month">{m.label}</div>
            <div class="tile-val {toneOf(m.total)}">{fmtMoney(m.total, currency)}</div>
            <div class="tile-trades">{m.trades} trade{m.trades === 1 ? "" : "s"}</div>
          </div>
        {/each}
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
  .hd-right {
    text-align: right;
    flex: none;
  }
  .hd-right .val {
    font-size: var(--text-2lg);
    font-weight: var(--weight-bold);
    font-variant-numeric: tabular-nums;
  }
  .hd-right .val.pos {
    color: var(--up);
  }
  .hd-right .val.neg {
    color: var(--dn);
  }
  .hd-right .sub {
    font-size: var(--text-2xs);
    color: var(--dim-45);
  }

  .body {
    padding: 14px 22px 18px;
  }
  .sub-title {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--dim-55);
    margin-bottom: 4px;
  }
  .divider {
    height: 1px;
    margin: 0 22px;
    background: var(--border-05);
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
  .bar-label {
    font-size: 10px;
    font-weight: var(--weight-semibold);
    font-variant-numeric: tabular-nums;
    fill: var(--text);
  }
  .bar-label.muted {
    fill: var(--dim-55);
    font-weight: var(--weight-medium);
  }
  .bar-month {
    font-size: 10px;
    font-weight: var(--weight-medium);
    fill: var(--dim-45);
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
  .base-line {
    stroke: var(--border-05);
    stroke-width: 1;
  }

  .tooltip {
    position: absolute;
    pointer-events: none;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 7px 10px;
    font-size: var(--text-xs);
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.12);
    transform: translate(-50%, -100%);
    white-space: nowrap;
    z-index: 5;
  }
  .tooltip .t-month {
    font-weight: var(--weight-semibold);
    color: var(--text);
    margin-bottom: 2px;
  }
  .tooltip .t-val {
    font-variant-numeric: tabular-nums;
    font-weight: var(--weight-semibold);
  }
  .tooltip .t-val.pos {
    color: var(--up);
  }
  .tooltip .t-val.neg {
    color: var(--dn);
  }
  .tooltip .t-val.neutral {
    color: var(--accent);
  }
  .tooltip .t-sub {
    color: var(--dim-45);
    font-size: var(--text-2xs);
    margin-top: 1px;
  }

  .tiles {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
    gap: 8px;
  }
  .tile {
    padding: 12px 10px 11px;
    border-radius: var(--radius-md);
    background: var(--surface-02);
    border: 1px solid var(--border-05);
  }
  .tile-month {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--dim-55);
  }
  .tile-val {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    font-variant-numeric: tabular-nums;
    margin-top: 4px;
  }
  .tile-val.pos {
    color: var(--up);
  }
  .tile-val.neg {
    color: var(--dn);
  }
  .tile-trades {
    font-size: var(--text-2xs);
    color: var(--accent);
    font-weight: var(--weight-semibold);
    margin-top: 3px;
    font-variant-numeric: tabular-nums;
  }

  .empty {
    color: var(--dim-55);
    text-align: center;
    padding: 40px 0;
    font-size: var(--text-sm);
  }
</style>
