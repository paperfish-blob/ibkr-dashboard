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
  import { fmtMoney, num, toneOf, EM_DASH } from "$lib/format";
  import type { CumulativePoint } from "$lib/api";
  import SegToggle from "./SegToggle.svelte";

  interface Props {
    series: CumulativePoint[];
    currency?: string;
    /** Singular noun for what series[].trade_count actually counts --
     *  "trade" (default, Overview's daily P&L series) or "position" (the
     *  Positions Overview page's closed round-trips). Pluralized with a
     *  trailing "s". */
    unit?: string;
    /** Overrides the panel's caption line under the title. */
    caption?: string;
    /** Builds the URL a clicked month opens (new tab) -- defaults to the
     *  Transactions ledger, filtered to that month's opening trades.
     *  Positions Overview passes one pointing at the Positions page instead,
     *  since its months are round-trips, not executions. */
    monthLink?: (monthKey: string) => string;
    /** "YYYY-MM" -> { wins, total } among that month's closed positions --
     *  when given, adds a third "win rate" chart row and a win-rate line on
     *  each tile. Positions Overview only; omitted (the default) on the
     *  plain Overview page, where a single trade isn't naturally a
     *  win/loss the same way a closed round-trip is. */
    winRates?: Map<string, { wins: number; total: number }>;
    /** "YYYY-MM" -> aggregate win/loss dollars among that month's closed
     *  positions -- when given, adds a fourth "avg R:R" chart row (that
     *  month's average winning position divided by its average losing
     *  position) and an R:R line on each tile. Positions Overview only,
     *  same as winRates. */
    rrStats?: Map<string, { winSum: number; winCount: number; lossSum: number; lossCount: number }>;
    /** Fired with the hovered month's "YYYY-MM" key (or null on clear) --
     *  lets a sibling chart elsewhere on the page (e.g. an index benchmark)
     *  sync its own highlight to the same month. */
    onHoverMonth?: (monthKey: string | null) => void;
    /** "charts" (default) renders the stacked bar charts below; "table"
     *  renders a dense scorecard instead -- same month data, no chart axes
     *  to get illegibly thin once a period has many months. Owned by the
     *  caller (backed by a persisted store) rather than internal state, so
     *  the choice can be shared across every page that embeds this panel. */
    view?: "charts" | "table";
    onViewChange?: (view: "charts" | "table") => void;
  }
  let {
    series,
    currency = "USD",
    unit = "trade",
    caption = "Gross, before commission · Flex trades only, bucketed from the daily series above",
    monthLink = (key) => `/transactions?year=${key.slice(0, 4)}&filter=opening&months=${key}&group=1`,
    winRates,
    rrStats,
    onHoverMonth,
    view = "charts",
    onViewChange,
  }: Props = $props();
  const unitPlural = $derived(`${unit}s`);
  const unitCountLabel = $derived(`${unit[0].toUpperCase()}${unit.slice(1)} count`);

  interface MonthBucket {
    key: string; // "2026-06", sorts chronologically as a string
    label: string; // "Jun 2026"
    total: number;
    trades: number;
    winRate: number | null; // 0-100, null when winRates has nothing for this month
    rr: number | null; // avg win / avg loss, null when there's no loss (or no win) to divide by
  }

  const months = $derived.by((): MonthBucket[] => {
    const buckets = new Map<string, MonthBucket>();
    for (const p of series) {
      const key = p.date.slice(0, 7);
      let b = buckets.get(key);
      if (!b) {
        const [y, m] = key.split("-").map(Number);
        const label = new Date(y, m - 1, 1).toLocaleDateString("en-US", { month: "short", year: "numeric" });
        const w = winRates?.get(key);
        const r = rrStats?.get(key);
        const rr = r && r.winCount > 0 && r.lossCount > 0 ? (r.winSum / r.winCount) / (r.lossSum / r.lossCount) : null;
        b = { key, label, total: 0, trades: 0, winRate: w && w.total > 0 ? (w.wins / w.total) * 100 : null, rr };
        buckets.set(key, b);
      }
      b.total += num(p.realized_pnl);
      b.trades += p.trade_count;
    }
    return [...buckets.values()].sort((a, b) => a.key.localeCompare(b.key));
  });

  const grandTotal = $derived(months.reduce((sum, m) => sum + m.total, 0));
  const totalTrades = $derived(months.reduce((sum, m) => sum + m.trades, 0));

  // Weighted across every closed position, not an average of the per-month
  // percentages -- a 100%-of-1 month and a 40%-of-50 month shouldn't count
  // the same.
  const overallWinRate = $derived.by(() => {
    if (!winRates || winRates.size === 0) return null;
    let wins = 0;
    let total = 0;
    for (const v of winRates.values()) {
      wins += v.wins;
      total += v.total;
    }
    return total > 0 ? (wins / total) * 100 : null;
  });

  // Same weighted-not-averaged reasoning as overallWinRate -- total winning
  // dollars / total win count, over total losing dollars / total loss
  // count, so one outsized single-position month can't dominate the
  // headline the way averaging the monthly ratios would let it.
  const overallRR = $derived.by(() => {
    if (!rrStats || rrStats.size === 0) return null;
    let winSum = 0, winCount = 0, lossSum = 0, lossCount = 0;
    for (const v of rrStats.values()) {
      winSum += v.winSum;
      winCount += v.winCount;
      lossSum += v.lossSum;
      lossCount += v.lossCount;
    }
    if (winCount === 0 || lossCount === 0) return null;
    return (winSum / winCount) / (lossSum / lossCount);
  });

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

  // ---- table view's headline sparkline -- a plain (non-rounded, no hover)
  // strip since the table rows below already carry the per-month detail. ----
  const MINI_H = 46;
  interface MiniBar {
    x: number;
    y: number;
    w: number;
    h: number;
    up: boolean;
  }
  const maxAbsTotal = $derived(Math.max(1, ...months.map((m) => Math.abs(m.total))));

  const miniBars = $derived.by((): MiniBar[] | null => {
    if (!months.length || !barLayout) return null;
    const { barW, xs } = barLayout;
    const plotH = MINI_H - 8;
    const zeroY = MINI_H / 2;
    const scale = (plotH * 0.48) / maxAbsTotal;
    return months.map((m, i) => {
      const up = m.total >= 0;
      const h = Math.max(1, Math.abs(m.total) * scale);
      return { x: xs[i], y: up ? zeroY - h : zeroY, w: barW, h, up };
    });
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

  // ---- win-rate bars (always 0-100%, a fixed scale rather than one that
  // floats with the data -- a 60% month should always read the same height
  // whichever months happen to be in view) ----
  const WIN_H = 130;
  const WIN_PAD_TOP = 22;
  const WIN_PAD_BOTTOM = 22;
  // The reference line and the green/red split both sit at this rate, not
  // 50% -- a lower bar with a solid overall edge (big winners, frequent
  // small losers) is still "winning" by this book, not just literally
  // batting above half.
  const WIN_RATE_THRESHOLD = 30;

  interface WinBar extends MonthBucket {
    x: number;
    y: number;
    w: number;
    h: number;
    up: boolean;
    path: string;
  }

  const winBars = $derived.by((): { bars: WinBar[]; refY: number } | null => {
    if (!months.length || !barLayout || !winRates) return null;
    const { barW, xs } = barLayout;
    const plotH = WIN_H - WIN_PAD_TOP - WIN_PAD_BOTTOM;
    const baseY = WIN_H - WIN_PAD_BOTTOM;
    const refY = WIN_PAD_TOP + plotH * (1 - WIN_RATE_THRESHOLD / 100);

    const out: WinBar[] = months.map((m, i) => {
      const x = xs[i];
      const rate = m.winRate ?? 0;
      const up = rate >= WIN_RATE_THRESHOLD;
      const h = (rate / 100) * plotH;
      const y = baseY - h;
      const r = Math.min(4, barW / 2, h);
      return { ...m, x, y, w: barW, h, up, path: barPath(x, y, barW, h, true, r) };
    });
    return { bars: out, refY };
  });

  // ---- avg R:R bars (avg win / avg loss has no natural cap the way a
  // percentage does, so the scale floats to the tallest month with some
  // headroom rather than a fixed 0-100 -- the reference line stays pinned
  // at 1.0x, i.e. avg win == avg loss, regardless of where that puts it) ----
  const RR_H = 130;
  const RR_PAD_TOP = 22;
  const RR_PAD_BOTTOM = 22;
  const RR_REF = 1;

  interface RRBar extends MonthBucket {
    x: number;
    y: number;
    w: number;
    h: number;
    up: boolean;
    path: string;
  }

  const rrBars = $derived.by((): { bars: RRBar[]; refY: number } | null => {
    if (!months.length || !barLayout || !rrStats) return null;
    const { barW, xs } = barLayout;
    const plotH = RR_H - RR_PAD_TOP - RR_PAD_BOTTOM;
    const baseY = RR_H - RR_PAD_BOTTOM;
    const maxRR = Math.max(RR_REF, ...months.map((m) => m.rr ?? 0));
    const scale = plotH / (maxRR * 1.18);
    const refY = baseY - RR_REF * scale;

    const out: RRBar[] = months.map((m, i) => {
      const x = xs[i];
      const rr = m.rr ?? 0;
      const up = m.rr !== null && m.rr >= RR_REF;
      const h = rr * scale;
      const y = baseY - h;
      const r = Math.min(4, barW / 2, h);
      return { ...m, x, y, w: barW, h, up, path: barPath(x, y, barW, h, true, r) };
    });
    return { bars: out, refY };
  });

  // Hovering a month bar in either chart highlights that month in BOTH
  // (dims the rest) and shows both tooltips -- comparing P&L to trade count
  // for one month then needs a single hover, not two. Keyed by index into
  // `months` rather than by bar object, since that's the one thing both
  // charts' bars share.
  let hoveredIndex = $state<number | null>(null);

  // Switching between Charts and Table swaps out whichever element was
  // hovered without a mouseleave necessarily firing on it first (its row
  // or bar just vanishes), which would otherwise leave a stale highlight
  // pinned on both this panel and the synced index chart.
  $effect(() => {
    view;
    hoveredIndex = null;
    onHoverMonth?.(null);
  });

  let pnlBox: HTMLDivElement | undefined = $state();
  let tradesBox: HTMLDivElement | undefined = $state();
  let winBox: HTMLDivElement | undefined = $state();
  let rrBox: HTMLDivElement | undefined = $state();
  let miniBox: HTMLDivElement | undefined = $state();
  let pnlBarEls: (SVGPathElement | undefined)[] = [];
  let tradesBarEls: (SVGPathElement | undefined)[] = [];
  let winBarEls: (SVGPathElement | undefined)[] = [];
  let rrBarEls: (SVGPathElement | undefined)[] = [];
  let miniBarEls: (SVGRectElement | undefined)[] = [];

  function barOpacity(i: number): number {
    return hoveredIndex === null || hoveredIndex === i ? 1 : 0.32;
  }

  function setHoveredIndex(i: number | null) {
    hoveredIndex = i;
    onHoverMonth?.(i === null ? null : months[i].key);
  }

  // Clicking a month drills into it on whichever page monthLink points at --
  // Transactions by default, or wherever the caller passed instead. New tab
  // so this page (and its current hover state) stays put behind it.
  function openMonth(key: string) {
    window.open(monthLink(key), "_blank");
  }

  function tooltipPos(box: HTMLDivElement | undefined, bar: SVGGraphicsElement | undefined) {
    if (!box || !bar) return null;
    const barRect = bar.getBoundingClientRect();
    const boxRect = box.getBoundingClientRect();
    return { x: barRect.left + barRect.width / 2 - boxRect.left, y: barRect.top - boxRect.top - 10 };
  }

  const pnlTooltip = $derived(hoveredIndex === null ? null : tooltipPos(pnlBox, pnlBarEls[hoveredIndex]));
  const tradesTooltip = $derived(hoveredIndex === null ? null : tooltipPos(tradesBox, tradesBarEls[hoveredIndex]));
  const winTooltip = $derived(hoveredIndex === null ? null : tooltipPos(winBox, winBarEls[hoveredIndex]));
  const rrTooltip = $derived(hoveredIndex === null ? null : tooltipPos(rrBox, rrBarEls[hoveredIndex]));
  const miniTooltip = $derived(hoveredIndex === null ? null : tooltipPos(miniBox, miniBarEls[hoveredIndex]));
</script>

<div class="panel">
  <div class="hd">
    <div class="hd-left">
      <div class="eyebrow">By month</div>
      <div class="title">Monthly P&amp;L &amp; {unit} count</div>
      <div class="caption">{caption}</div>
    </div>
    <div class="hd-mid">
      <SegToggle
        options={[
          { label: "Charts", value: "charts" },
          { label: "Table", value: "table" },
        ]}
        active={view}
        onChange={(v) => onViewChange?.(v as "charts" | "table")}
      />
    </div>
    <div class="hd-right">
      <div class="val {toneOf(grandTotal)}">{fmtMoney(grandTotal, currency)}</div>
      <div class="sub">
        {totalTrades} {totalTrades === 1 ? unit : unitPlural}{overallWinRate !== null
          ? ` · ${overallWinRate.toFixed(0)}% win rate`
          : ""}{overallRR !== null ? ` · ${overallRR.toFixed(1)}R avg R:R` : ""}
      </div>
    </div>
  </div>

  {#if !pnlBars || !tradesBars || !barLayout}
    <div class="empty">No realizing trades in this statement period.</div>
  {:else if view === "table"}
    <div class="mini-strip" bind:this={miniBox} onmouseleave={() => setHoveredIndex(null)}>
      <svg class="bars-svg" viewBox="0 0 {CHART_W} {MINI_H}" preserveAspectRatio="xMidYMid meet">
        {#each months as m, i (m.key)}
          <rect
            class="hover-band"
            class:active={hoveredIndex === i}
            x={barLayout.xs[i] - BAR_GAP / 2}
            y={0}
            width={barLayout.barW + BAR_GAP}
            height={MINI_H}
            onmousemove={() => setHoveredIndex(i)}
            onclick={() => openMonth(m.key)}
          ><title>Open {m.label} in Transactions</title></rect>
        {/each}
        <line class="base-line" x1={PAD_L} y1={MINI_H / 2} x2={CHART_W - PAD_R} y2={MINI_H / 2} />
        {#if miniBars}
          {#each miniBars as bar, i (months[i].key)}
            <rect
              x={bar.x}
              y={bar.y}
              width={bar.w}
              height={bar.h}
              rx="1.5"
              fill={bar.up ? "var(--up)" : "var(--dn)"}
              style="opacity:{barOpacity(i)}; pointer-events:none"
              bind:this={miniBarEls[i]}
            />
          {/each}
        {/if}
      </svg>
      {#if hoveredIndex !== null && miniTooltip}
        <div class="tooltip show" style="left:{miniTooltip.x}px; top:{miniTooltip.y}px">
          <div class="t-month">{months[hoveredIndex].label}</div>
          <div class="t-val {toneOf(months[hoveredIndex].total)}">{fmtMoney(months[hoveredIndex].total, currency)}</div>
        </div>
      {/if}
    </div>
    <div class="body table-body">
      <table class="score-table">
        <thead>
          <tr>
            <th>Month</th>
            <th class="num">P&amp;L</th>
            <th class="num">{unitCountLabel}</th>
            {#if winRates}<th class="num">Win rate</th>{/if}
            {#if rrStats}<th class="num">Avg R:R</th>{/if}
          </tr>
        </thead>
        <tbody>
          {#each months as m, i (m.key)}
            <tr
              onclick={() => openMonth(m.key)}
              onmouseenter={() => setHoveredIndex(i)}
              onmouseleave={() => setHoveredIndex(null)}
              title="Open {m.label} in Transactions"
            >
              <td class="month-cell">{m.label}</td>
              <td class="num">
                <div class="pnl-cell">
                  <div class="pnl-bar-track">
                    <div
                      class="pnl-bar-fill {m.total >= 0 ? 'pos' : 'neg'}"
                      style="width:{(Math.min(1, Math.abs(m.total) / maxAbsTotal) * 50).toFixed(1)}%"
                    ></div>
                  </div>
                  <span class="pnl-val {toneOf(m.total)}">{fmtMoney(m.total, currency)}</span>
                </div>
              </td>
              <td class="num tabular">{m.trades}</td>
              {#if winRates}
                <td class="num">
                  <div class="win-cell">
                    <div class="win-dot-track">
                      <div
                        class="win-dot-fill"
                        style="width:{m.winRate ?? 0}%; background:{m.winRate === null
                          ? 'var(--dim-35)'
                          : m.winRate >= WIN_RATE_THRESHOLD
                            ? 'var(--up)'
                            : 'var(--dn)'}"
                      ></div>
                    </div>
                    <span>{m.winRate === null ? EM_DASH : `${m.winRate.toFixed(0)}%`}</span>
                  </div>
                </td>
              {/if}
              {#if rrStats}
                <td class="num">
                  <span class="rr-chip {m.rr === null ? 'none' : m.rr >= RR_REF ? 'hi' : 'lo'}">
                    {m.rr === null ? EM_DASH : `${m.rr.toFixed(1)}R`}
                  </span>
                </td>
              {/if}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
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
              onclick={() => openMonth(m.key)}
            ><title>Open {m.label} in Transactions</title></rect>
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
              {months[hoveredIndex].trades} {months[hoveredIndex].trades === 1 ? unit : unitPlural}
            </div>
          </div>
        {/if}
      </div>
    </div>

    <div class="divider"></div>

    <div class="body">
      <div class="sub-title">{unitCountLabel}</div>
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
              onclick={() => openMonth(m.key)}
            ><title>Open {m.label} in Transactions</title></rect>
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
              {months[hoveredIndex].trades} {months[hoveredIndex].trades === 1 ? unit : unitPlural}
            </div>
          </div>
        {/if}
      </div>
    </div>

    {#if winBars}
      <div class="divider"></div>

      <div class="body">
        <div class="sub-title">
          Win rate <span class="agg">— share of that month's {unitPlural} closed profitably</span>
        </div>
        <div class="bars-box" bind:this={winBox} onmouseleave={() => setHoveredIndex(null)}>
          <svg class="bars-svg" viewBox="0 0 {CHART_W} {WIN_H}" preserveAspectRatio="xMidYMid meet">
            {#each months as m, i (m.key)}
              <rect
                class="hover-band"
                class:active={hoveredIndex === i}
                x={barLayout.xs[i] - BAR_GAP / 2}
                y={0}
                width={barLayout.barW + BAR_GAP}
                height={WIN_H}
                onmousemove={() => setHoveredIndex(i)}
                onclick={() => openMonth(m.key)}
              ><title>Open {m.label} in Transactions</title></rect>
            {/each}
            <line class="ref-line" x1={PAD_L} y1={winBars.refY} x2={CHART_W - PAD_R} y2={winBars.refY} />
            {#each winBars.bars as bar, i (bar.key)}
              <path
                class="bar-rect"
                d={bar.path}
                fill={bar.winRate === null ? "var(--dim-35)" : bar.up ? "var(--up)" : "var(--dn)"}
                style="opacity:{barOpacity(i)}"
                bind:this={winBarEls[i]}
              />
              {#if barLayout.showValueLabels}
                <text
                  class="bar-label"
                  x={bar.x + bar.w / 2}
                  y={bar.y - 6}
                  text-anchor="middle"
                  fill={bar.winRate === null ? "var(--dim-45)" : bar.up ? "var(--up)" : "var(--dn)"}
                >
                  {bar.winRate === null ? EM_DASH : `${bar.winRate.toFixed(0)}%`}
                </text>
              {/if}
              {#if i % barLayout.monthLabelEvery === 0}
                <text class="bar-month" x={bar.x + bar.w / 2} y={WIN_H - 6} text-anchor="middle">
                  {bar.label.split(" ")[0]}
                </text>
              {/if}
            {/each}
            <text class="ref-label" x={CHART_W - PAD_R} y={winBars.refY - 4} text-anchor="end">
              {WIN_RATE_THRESHOLD}% line
            </text>
          </svg>
          {#if hoveredIndex !== null && winTooltip}
            <div class="tooltip show" style="left:{winTooltip.x}px; top:{winTooltip.y}px">
              <div class="t-month">{months[hoveredIndex].label}</div>
              <div class="t-val {months[hoveredIndex].winRate === null ? '' : months[hoveredIndex].winRate! >= WIN_RATE_THRESHOLD ? 'pos' : 'neg'}">
                {months[hoveredIndex].winRate === null ? EM_DASH : `${months[hoveredIndex].winRate!.toFixed(0)}%`}
              </div>
            </div>
          {/if}
        </div>
      </div>
    {/if}

    {#if rrBars}
      <div class="divider"></div>

      <div class="body">
        <div class="sub-title">
          Avg R:R <span class="agg">— that month's average winning {unit} ÷ average losing {unit}</span>
        </div>
        <div class="bars-box" bind:this={rrBox} onmouseleave={() => setHoveredIndex(null)}>
          <svg class="bars-svg" viewBox="0 0 {CHART_W} {RR_H}" preserveAspectRatio="xMidYMid meet">
            {#each months as m, i (m.key)}
              <rect
                class="hover-band"
                class:active={hoveredIndex === i}
                x={barLayout.xs[i] - BAR_GAP / 2}
                y={0}
                width={barLayout.barW + BAR_GAP}
                height={RR_H}
                onmousemove={() => setHoveredIndex(i)}
                onclick={() => openMonth(m.key)}
              ><title>Open {m.label} in Transactions</title></rect>
            {/each}
            <line class="ref-line" x1={PAD_L} y1={rrBars.refY} x2={CHART_W - PAD_R} y2={rrBars.refY} />
            {#each rrBars.bars as bar, i (bar.key)}
              <path
                class="bar-rect"
                d={bar.path}
                fill={bar.rr === null ? "var(--dim-35)" : bar.up ? "var(--up)" : "var(--dn)"}
                style="opacity:{barOpacity(i)}"
                bind:this={rrBarEls[i]}
              />
              {#if barLayout.showValueLabels}
                <text
                  class="bar-label"
                  x={bar.x + bar.w / 2}
                  y={bar.y - 6}
                  text-anchor="middle"
                  fill={bar.rr === null ? "var(--dim-45)" : bar.up ? "var(--up)" : "var(--dn)"}
                >
                  {bar.rr === null ? EM_DASH : `${bar.rr.toFixed(1)}R`}
                </text>
              {/if}
              {#if i % barLayout.monthLabelEvery === 0}
                <text class="bar-month" x={bar.x + bar.w / 2} y={RR_H - 6} text-anchor="middle">
                  {bar.label.split(" ")[0]}
                </text>
              {/if}
            {/each}
            <text class="ref-label" x={CHART_W - PAD_R} y={rrBars.refY - 4} text-anchor="end">
              1.0R line
            </text>
          </svg>
          {#if hoveredIndex !== null && rrTooltip}
            <div class="tooltip show" style="left:{rrTooltip.x}px; top:{rrTooltip.y}px">
              <div class="t-month">{months[hoveredIndex].label}</div>
              <div class="t-val {months[hoveredIndex].rr === null ? '' : months[hoveredIndex].rr! >= RR_REF ? 'pos' : 'neg'}">
                {months[hoveredIndex].rr === null ? EM_DASH : `${months[hoveredIndex].rr!.toFixed(1)}R`}
              </div>
            </div>
          {/if}
        </div>
      </div>
    {/if}

    <div class="divider"></div>

    <div class="body">
      <div class="tiles">
        {#each months as m (m.key)}
          <button class="tile" onclick={() => openMonth(m.key)} title="Open {m.label} in Transactions">
            <div class="tile-month">{m.label}</div>
            <div class="tile-val {toneOf(m.total)}">{fmtMoney(m.total, currency)}</div>
            <div class="tile-trades">{m.trades} {m.trades === 1 ? unit : unitPlural}</div>
            {#if m.winRate !== null || m.rr !== null}
              <div class="tile-stats">
                {#if m.winRate !== null}
                  <div class="tile-win {m.winRate >= WIN_RATE_THRESHOLD ? 'hi' : 'lo'}" title="Win rate">
                    <span class="dot"></span>{m.winRate.toFixed(0)}% win
                  </div>
                {/if}
                {#if m.rr !== null}
                  <div class="tile-rr {m.rr >= RR_REF ? 'hi' : 'lo'}" title="Avg R:R">
                    <span class="dot"></span>{m.rr.toFixed(1)}R avg
                  </div>
                {/if}
              </div>
            {/if}
          </button>
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
    flex-wrap: wrap;
    gap: 12px;
    padding: 14px 22px;
    border-bottom: 1px solid var(--border-05);
  }
  .hd-mid {
    margin-left: auto;
    padding-top: 1px;
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

  .mini-strip {
    position: relative;
    padding: 10px 22px 2px;
  }

  .table-body {
    padding-top: 8px;
    overflow-x: auto;
  }
  .score-table {
    width: 100%;
    border-collapse: collapse;
  }
  .score-table th {
    text-align: left;
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--dim-45);
    padding: 6px 10px;
    border-bottom: 1px solid var(--border-08);
    white-space: nowrap;
  }
  .score-table th.num,
  .score-table td.num {
    text-align: right;
  }
  .score-table td {
    padding: 7px 10px;
    font-size: var(--text-sm);
    border-bottom: 1px solid var(--border-05);
    vertical-align: middle;
  }
  .score-table td.tabular {
    font-variant-numeric: tabular-nums;
  }
  .score-table tbody tr {
    cursor: pointer;
  }
  .score-table tbody tr:hover td {
    background: var(--surface-02);
  }
  .score-table .month-cell {
    font-weight: var(--weight-semibold);
    white-space: nowrap;
  }
  .pnl-cell {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
  }
  .pnl-bar-track {
    width: 64px;
    height: 6px;
    border-radius: 3px;
    background: var(--surface-06);
    position: relative;
    overflow: hidden;
    flex: none;
  }
  .pnl-bar-fill {
    position: absolute;
    top: 0;
    bottom: 0;
    border-radius: 3px;
  }
  .pnl-bar-fill.pos {
    background: var(--up);
    left: 50%;
  }
  .pnl-bar-fill.neg {
    background: var(--dn);
    right: 50%;
  }
  .pnl-val {
    font-variant-numeric: tabular-nums;
    font-weight: var(--weight-semibold);
    width: 74px;
    text-align: right;
  }
  .pnl-val.pos {
    color: var(--up);
  }
  .pnl-val.neg {
    color: var(--dn);
  }
  .win-cell {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 6px;
    font-variant-numeric: tabular-nums;
  }
  .win-dot-track {
    width: 30px;
    height: 5px;
    border-radius: 3px;
    background: var(--surface-06);
    overflow: hidden;
  }
  .win-dot-fill {
    height: 100%;
    border-radius: 3px;
  }
  .rr-chip {
    display: inline-block;
    font-size: var(--text-2xs);
    font-weight: var(--weight-bold);
    font-variant-numeric: tabular-nums;
    padding: 2px 7px;
    border-radius: var(--radius-pill);
  }
  .rr-chip.hi {
    color: var(--up);
    background: var(--up-bg);
  }
  .rr-chip.lo {
    color: var(--dn);
    background: var(--dn-bg);
  }
  .rr-chip.none {
    color: var(--dim-45);
    background: var(--surface-04);
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
  .sub-title .agg {
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    text-transform: none;
    letter-spacing: 0;
    color: var(--dim-45);
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
  .ref-line {
    stroke: var(--border-12);
    stroke-width: 1;
    stroke-dasharray: 3 3;
  }
  .ref-label {
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
    font: inherit;
    text-align: left;
    cursor: pointer;
    width: 100%;
  }
  .tile:hover {
    background: var(--surface-04);
    border-color: var(--border-12);
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
  .tile-stats {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 10px;
    margin-top: 2px;
  }
  .tile-win,
  .tile-rr {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    font-variant-numeric: tabular-nums;
  }
  .tile-win .dot,
  .tile-rr .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex: none;
  }
  .tile-win.hi,
  .tile-rr.hi {
    color: var(--up);
  }
  .tile-win.hi .dot,
  .tile-rr.hi .dot {
    background: var(--up);
  }
  .tile-win.lo,
  .tile-rr.lo {
    color: var(--dn);
  }
  .tile-win.lo .dot,
  .tile-rr.lo .dot {
    background: var(--dn);
  }

  .empty {
    color: var(--dim-55);
    text-align: center;
    padding: 40px 0;
    font-size: var(--text-sm);
  }
</style>
