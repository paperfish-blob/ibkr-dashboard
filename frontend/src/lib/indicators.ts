/**
 * Per-bar indicator helpers shared by the chart components.
 *
 * calcSMA/calcEMA return arrays aligned 1:1 with the input closes, with leading nulls
 * until the lookback is satisfied — so a caller can index them alongside the bars and
 * treat null as "not enough history", the same way Pine treats na.
 */
import type { OHLCVBar } from "$lib/api";

export function calcSMA(closes: number[], period: number): (number | null)[] {
  return closes.map((_, i) => {
    if (i < period - 1) return null;
    const slice = closes.slice(i - period + 1, i + 1);
    return slice.reduce((a, b) => a + b, 0) / period;
  });
}

export function calcEMA(closes: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1);
  const out: (number | null)[] = new Array(closes.length).fill(null);
  let ema: number | null = null;
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) continue;
    if (ema === null) {
      ema = closes.slice(0, period).reduce((a, b) => a + b, 0) / period;
    } else {
      ema = closes[i] * k + ema * (1 - k);
    }
    out[i] = ema;
  }
  return out;
}

/**
 * Average True Range, Wilder's smoothing — aligned 1:1 with the input bars.
 *
 * Pine's ta.atr(n) is ta.rma(ta.tr(true), n), and ta.rma is Wilder's moving average, NOT a
 * simple mean: rma = (prev * (n - 1) + tr) / n, seeded with the SMA of the first n values.
 * The two ATRs in the Python backend (services/brief_service.py, services/market_data.py)
 * both take a plain mean of the last 14 TRs, so their numbers will not match this one. That
 * is deliberate — this function's job is to reproduce the TradingView overlay exactly.
 *
 * ta.tr(true) is the `handle_na = true` form: on bar 0 there is no previous close, and it
 * falls back to high - low rather than returning na.
 */
export function calcATR(bars: OHLCVBar[], period = 14): (number | null)[] {
  const tr = bars.map((b, i) =>
    i === 0
      ? b.high - b.low
      : Math.max(b.high - b.low, Math.abs(b.high - bars[i - 1].close), Math.abs(b.low - bars[i - 1].close)),
  );

  const out: (number | null)[] = new Array(bars.length).fill(null);
  let rma: number | null = null;
  for (let i = 0; i < tr.length; i++) {
    if (i < period - 1) continue;
    rma =
      rma === null
        ? tr.slice(0, period).reduce((a, b) => a + b, 0) / period
        : (rma * (period - 1) + tr[i]) / period;
    out[i] = rma;
  }
  return out;
}

/**
 * Tier colours for the parabolic circles, keyed by the tier's lower bound.
 *
 * Pine's built-ins verbatim as hues. The ramp is NOT monotonic — color.red sits at the
 * LOWEST visible tier, below color.lime — which reads backwards but is what the script
 * does; the ordering is upstream, not a mistake here.
 *
 * The script's transparency 20 is dropped. These are small solid dots on a #ffffff pane and
 * #00E676 at 0.8 alpha barely registers against it — the same white-background problem
 * APS_COLORS documents at length. Opaque costs nothing legibility-wise for a 4px mark.
 */
export const PARABOLIC_COLORS: Record<number, string> = {
  7: "#FF5252",  // color.red
  8: "#00E676",  // color.lime
  10: "#4CAF50", // color.green
  12: "#9C27B0", // color.purple
};

/**
 * "Overlay Extended / Parabolic Alert" — ported from the TradingView script.
 *
 * The measure is how far price has stretched from its 50MA relative to its OWN volatility:
 * atrMultiple = (% above MA50) / (ATR as % of price). A name 20% above its 50MA is ordinary
 * if it swings 4% a day and parabolic if it swings 1%.
 *
 * Returns two arrays rather than one merged value, because a single bar can be both a climax
 * bar and an extended one and the script plots them as two independent plotshapes.
 *
 *   climax — the "C" label: atrMultiple >= 5, an open-to-close spread wider than the 20-day
 *            average range, and an up close. An exhaustion bar.
 *   tier   — the coloured circle's threshold, or null for none.
 *
 * The 5..7 band is intentionally absent from `tier`. The script's circle fires at >= 5, but
 * circleColor is only ever assigned at >= 7 — below that it stays na, and color.new(na, 20)
 * is na, so Pine draws nothing. Ported as-is: >= 5 only gates the C label.
 *
 * `today` is a parameter rather than an inline clock read, both for testability and because
 * it makes the historical charts correct for free: on the scanner and backtrace panes the
 * last bar is an as-of date, not today, so every bar takes the `high` branch as it should.
 *
 * request.security(tickerid, 'D', ...) is a no-op on daily bars, so dailyRange/dailySpread
 * are read straight off each bar. That only holds for a DAILY series — see the caller's
 * interval guard.
 */
export function parabolicAlerts(
  bars: OHLCVBar[],
  today: string = new Date().toISOString().slice(0, 10),
): { climax: boolean[]; tier: (number | null)[] } {
  const closes = bars.map((b) => b.close);
  const atr = calcATR(bars, 14);
  const ma50 = calcSMA(closes, 50);
  // calcSMA is generic over any number series, so the high-low range goes straight in.
  const avgDailyRange = calcSMA(bars.map((b) => b.high - b.low), 20);

  const climax = new Array<boolean>(bars.length).fill(false);
  const tier = new Array<number | null>(bars.length).fill(null);

  for (let i = 0; i < bars.length; i++) {
    const b = bars[i];
    const a = atr[i];
    const m50 = ma50[i];
    if (a === null || m50 === null || m50 <= 0) continue;

    const price = b.time === today ? b.close : b.high;
    if (price <= 0) continue;

    const atrPct = (a / price) * 100;
    // Guard the divisor rather than the comparison: a zero ATR would send atrMultiple to
    // Infinity and light up every tier at once.
    if (atrPct <= 0) continue;

    const atrMultiple = ((price - m50) / m50) * 100 / atrPct;

    const adr = avgDailyRange[i];
    if (
      atrMultiple >= 5 &&
      adr !== null &&
      Math.abs(b.open - b.close) > adr &&
      i > 0 &&
      b.close > closes[i - 1]
    ) {
      climax[i] = true;
    }

    // Descending, so the highest matching tier wins — Pine's if / else-if chain.
    if (atrMultiple >= 12) tier[i] = 12;
    else if (atrMultiple >= 10) tier[i] = 10;
    else if (atrMultiple >= 8) tier[i] = 8;
    else if (atrMultiple >= 7) tier[i] = 7;
  }

  return { climax, tier };
}

/**
 * Regime background colours, ported from the TradingView bgcolor block.
 *
 * Pine's color.green is #4CAF50, color.blue #2196F3 and color.red #FF5252, so the
 * script's color.rgb(...) values are those same hues at different transparencies —
 * one palette, not four. Pine transparency t maps to opacity (100 - t) / 100, hence
 * the 0.10 / 0.05 continuation shades against the fully opaque crossover markers.
 *
 * crossUp50 departs from the script's color.blue on purpose. TickerChart draws the MA50
 * line in #3b82f6, near-identical to Pine's #2196F3, and the line paints ON TOP of this
 * column — an opaque blue erased the MA50 exactly at the bar where "is price above the
 * MA50" is the question the colour answers.
 *
 * Solved with alpha rather than by darkening. An opaque column has to clear every line
 * and candle on lightness, and the mid-blues are boxed in: MA50 sits at L* 56 and EMA20
 * at L* 70, so the only opaque blues that work are near-navy. Translucency sidesteps the
 * constraint entirely — the lines and candles are opaque and paint at full strength over
 * a tint regardless of hue. At 0.40 this composites to rgb(168,193,247) over the white
 * background, L* 78, a clear 22 points off the page and 8x the powertrend band's 0.05.
 */
export const REGIME_COLORS = {
  trend:      "rgba(76, 175, 79, 0.10)",   // color.rgb(76,175,79, 90)
  powertrend: "rgba(33, 149, 243, 0.05)",  // color.rgb(33,149,243, 95)
  crossUp:    "#4CAF50",                   // color.green
  crossUp50:  "rgba(37, 99, 235, 0.40)",   // color.blue, alpha'd off the MA50 line
  below50:    "rgba(255, 82, 82, 0.05)",   // color.rgb(255,82,82, 95)
} as const;

/**
 * One background colour per bar, or undefined where no rule matched.
 *
 * The five rules are applied in the script's own order and overwrite each other, because
 * Pine's sequential `if`s mean the LAST match wins — price_below_50 is last and so beats a
 * bare 9/20 crossover that fired below the 50MA.
 *
 * Every rule guards its inputs for null explicitly rather than leaning on comparisons:
 * Pine treats na comparisons as false, but JS coerces null to 0, so `null < src` would be
 * true and silently paint the warmup bars.
 */
export function regimeBands(bars: OHLCVBar[]): (string | undefined)[] {
  const closes = bars.map((b) => b.close);
  const ema9 = calcEMA(closes, 9);
  const ema20 = calcEMA(closes, 20);
  const ma50 = calcSMA(closes, 50);
  const ma200 = calcSMA(closes, 200);

  return bars.map((_, i) => {
    const src = closes[i];
    const e9 = ema9[i];
    const e20 = ema20[i];
    const m50 = ma50[i];
    const m200 = ma200[i];
    const pe9 = i > 0 ? ema9[i - 1] : null;
    const pe20 = i > 0 ? ema20[i - 1] : null;

    // ta.crossover(EMA9, EMA20): below-or-equal on the prior bar, above on this one.
    const crossUp9_20 =
      e9 !== null && e20 !== null && pe9 !== null && pe20 !== null && pe9 <= pe20 && e9 > e20;
    const midBullishFan =
      e20 !== null && m50 !== null && m200 !== null && e20 > m50 && m50 > m200;

    const crossUp9_20AndAbove50 = crossUp9_20 && m50 !== null && src > m50;
    const powertrendContinuation =
      e20 !== null && m200 !== null && src > e20 && src > m200 && midBullishFan;
    const trendContinuation =
      e20 !== null && m50 !== null && e9 !== null && src > e20 && src > m50 && e9 > e20;
    const priceBelow50 = m50 !== null && src < m50;

    let color: string | undefined;
    if (trendContinuation) color = REGIME_COLORS.trend;
    if (powertrendContinuation) color = REGIME_COLORS.powertrend;
    if (crossUp9_20) color = REGIME_COLORS.crossUp;
    if (crossUp9_20AndAbove50) color = REGIME_COLORS.crossUp50;
    if (priceBelow50) color = REGIME_COLORS.below50;
    return color;
  });
}

/**
 * Absolute Price Strength (ROC) — ported from the TradingView indicator by chasexcellence.
 *
 * "Has price travelled X% within the last N bars, high-to-low?" Each tier that fires
 * contributes a level, and the level is what gets plotted as a column height.
 *
 * The downside deliberately has no level 1 — the original script defines three bearish
 * tiers against four bullish ones. That asymmetry is upstream, not an omission here.
 */
export const APS_TIERS = {
  up: [
    { pct: 10, bars: 3, level: 1 },
    { pct: 20, bars: 5, level: 2 },
    { pct: 50, bars: 14, level: 3 },
    { pct: 100, bars: 42, level: 4 },
  ],
  down: [
    { pct: -20, bars: 5, level: -2 },
    { pct: -35, bars: 25, level: -3 },
    { pct: -50, bars: 42, level: -4 },
  ],
} as const;

/**
 * One colour per level, keyed by the signed level.
 *
 * Pine transparency t maps to opacity (100 - t) / 100, so the script's own values are
 * 0.20–0.30 — calibrated for TradingView's dark pane. TickerChart draws on #ffffff, where
 * those alphas are all but invisible. The hues are kept verbatim and the alpha is ramped
 * with the level instead, which buys back the contrast AND makes opacity encode strength:
 * a 100%-in-42-bars column now reads as decisively louder than a 10%-in-3-bars one, which
 * in the original is left entirely to column height.
 *
 * Level 4 keeps the script's neon color.rgb(57,255,20) verbatim, and is the one level drawn
 * fully opaque — it sits at L* 88 on a white page, so every point of alpha it gives up is
 * contrast it cannot spare. That also keeps the ramp monotonic (0.35 → 0.50 → 0.65 → 1.00).
 */
export const APS_COLORS: Record<number, string> = {
  1: "rgba(255, 152, 0, 0.35)", // color.orange
  2: "rgba(76, 175, 80, 0.50)", // color.green
  3: "rgba(33, 150, 243, 0.65)", // color.blue
  4: "rgba(57, 255, 20, 1)", // color.rgb(57,255,20)
  [-2]: "rgba(255, 69, 58, 0.40)", // color.rgb(255,69,58)
  [-3]: "rgba(255, 82, 82, 0.60)", // color.red
  [-4]: "rgba(139, 0, 0, 0.80)", // color.rgb(139,0,0)
};

/**
 * Per-bar strongest up level (0…4) and down level (0…-4), aligned 1:1 with the input bars.
 *
 * Both directions are returned separately because a single bar can satisfy an up tier and a
 * down tier at once, and the script plots both — collapsing them to one signed number would
 * silently drop half of a whipsaw bar.
 *
 * Pine's f_withinMaxConditionSignal loops lookback 1..max and fires if ANY lookback matches.
 * That is an OR over a monotonic comparison, so it collapses to a rolling extremum: the
 * largest possible (high - low[k]) / low[k] is the one taken against the LOWEST low in the
 * window. No per-bar loop over k is needed, only the window's min low / max high. The
 * script's `break` is the same short-circuit and needs no equivalent.
 *
 * Two boundary details are load-bearing:
 *   - k starts at 1, so the window is the bars BEFORE i; bar i's own low/high is excluded.
 *   - Pine reads low[k] as na when k > i and na comparisons are false, so the window is
 *     clamped to max(0, i - maxBars)…i-1 and bar 0 can never signal.
 *
 * Zero means "no signal" rather than null: the caller feeds this straight to a histogram
 * series, and a dense series is what preserves the chart's bar spacing (see regimeBands).
 */
export function absolutePriceStrength(bars: OHLCVBar[]): { up: number[]; down: number[] } {
  const up = new Array<number>(bars.length).fill(0);
  const down = new Array<number>(bars.length).fill(0);

  for (let i = 0; i < bars.length; i++) {
    for (const { pct, bars: maxBars, level } of APS_TIERS.up) {
      let minLow = Infinity;
      for (let j = Math.max(0, i - maxBars); j < i; j++) {
        // Guard the divisor rather than the comparison — a zero or negative low in bad
        // data would otherwise yield Infinity and light up every tier at once.
        if (bars[j].low > 0 && bars[j].low < minLow) minLow = bars[j].low;
      }
      if (minLow === Infinity) continue;
      if ((bars[i].high / minLow - 1) * 100 >= pct) up[i] = Math.max(up[i], level);
    }

    for (const { pct, bars: maxBars, level } of APS_TIERS.down) {
      let maxHigh = -Infinity;
      for (let j = Math.max(0, i - maxBars); j < i; j++) {
        if (bars[j].high > 0 && bars[j].high > maxHigh) maxHigh = bars[j].high;
      }
      if (maxHigh === -Infinity) continue;
      if ((bars[i].low / maxHigh - 1) * 100 <= pct) down[i] = Math.min(down[i], level);
    }
  }

  return { up, down };
}
