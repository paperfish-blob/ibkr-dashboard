<script lang="ts">
  /**
   * Download past years' statements, one at a time.
   *
   * A year costs up to 6 requests against a token limited to 10/minute and
   * takes 10-40s to generate, so downloads are serialised server-side and this
   * page polls only while one is running.
   */
  import { onMount, onDestroy } from "svelte";
  import PageHeader from "$lib/components/PageHeader.svelte";
  import SkeletonCard from "$lib/components/SkeletonCard.svelte";
  import AlertBar from "$lib/components/AlertBar.svelte";
  import { fmtDateTime, fmtMoney, num, toneOf, EM_DASH } from "$lib/format";
  import {
    history,
    historyError,
    refreshHistory,
    downloadYear,
    stopHistoryPoll,
  } from "$lib/stores";
  import { rawYearUrl, previewYear, type YearStatus } from "$lib/api";

  let note = $state<string | null>(null);
  let elapsed = $state(0);
  let ticker: ReturnType<typeof setInterval> | null = null;

  const busy = $derived($history?.downloading ?? null);

  // ── "View JSON" hover preview ────────────────────────────────────────────
  //
  // A fixed-position tooltip, not one nested in the table: the table sits in
  // a horizontally-scrolling wrapper (`.scroll`), and an absolutely
  // positioned child of a scroll container gets clipped by it. Positioning
  // from the hovered link's own bounding rect and rendering the tooltip at
  // the page level sidesteps that.
  //
  // Fetched once per year and cached in memory for the session: re-hovering
  // a year already peeked at should not cost another request.

  const previewCache = new Map<number, string>();
  let tooltip = $state<{ year: number; x: number; y: number } | null>(null);
  let tooltipText = $state<string | null>(null);
  let showTimer: ReturnType<typeof setTimeout> | null = null;
  // The tooltip's content is usually taller than TOOLTIP_MAX_HEIGHT (two
  // pretty-printed trades run well past it) and scrolls internally, which
  // means it has to accept the mouse -- so leaving the link can't close it
  // immediately, or the cursor could never reach the tooltip to scroll it.
  // hideTimer is the grace period that gets it there: closing is deferred
  // long enough for the mouse to land on the tooltip, which cancels it.
  let hideTimer: ReturnType<typeof setTimeout> | null = null;

  const TOOLTIP_WIDTH = 380;
  const TOOLTIP_MAX_HEIGHT = 280;
  const MARGIN = 16;

  function placeTooltip(anchor: HTMLElement): { x: number; y: number } {
    const rect = anchor.getBoundingClientRect();

    let x = Math.min(rect.left, window.innerWidth - TOOLTIP_WIDTH - MARGIN);
    x = Math.max(MARGIN, x);

    let y = rect.bottom + 8;
    if (y + TOOLTIP_MAX_HEIGHT > window.innerHeight - MARGIN) {
      // Not enough room below -- flip above the link instead.
      y = Math.max(MARGIN, rect.top - TOOLTIP_MAX_HEIGHT - 8);
    }
    return { x, y };
  }

  function cancelHide() {
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = null;
  }

  function scheduleHide() {
    cancelHide();
    hideTimer = setTimeout(() => {
      tooltip = null;
      tooltipText = null;
    }, 150);
  }

  function onViewEnter(year: number, e: MouseEvent) {
    cancelHide();
    const anchor = e.currentTarget as HTMLElement;
    // A short delay: a cursor merely passing over the link on its way
    // elsewhere should not fire a request.
    showTimer = setTimeout(() => {
      tooltip = { year, ...placeTooltip(anchor) };
      tooltipText = previewCache.get(year) ?? null;
      if (previewCache.has(year)) return;

      previewYear(year).then(
        (data) => {
          const text = JSON.stringify(data, null, 2);
          previewCache.set(year, text);
          if (tooltip?.year === year) tooltipText = text;
        },
        () => {
          if (tooltip?.year === year) tooltipText = "Couldn't load a preview.";
        },
      );
    }, 200);
  }

  function onViewLeave() {
    if (showTimer) clearTimeout(showTimer);
    showTimer = null;
    // Deferred, not immediate: gives the cursor time to reach the tooltip
    // itself, whose own mouseenter (below) cancels this if it does.
    scheduleHide();
  }

  async function start(year: number) {
    note = null;
    const res = await downloadYear(year);
    note = res.started ? null : res.message;
  }

  function label(y: YearStatus): string {
    if (y.state === "downloading") return "Downloading…";
    if (y.state === "error") return "Failed";
    if (y.state === "missing") return "Not downloaded";
    if (y.trade_count === 0) return "Stored · no trades";
    return y.is_current ? "Current year" : "Stored";
  }

  function buttonLabel(y: YearStatus): string {
    if (y.state === "downloading") return "Downloading…";
    if (y.state === "stored") return y.is_current ? "Refresh" : "Re-download";
    if (y.state === "error") return "Retry";
    return "Download";
  }

  onMount(() => {
    refreshHistory();
    // Elapsed time on the running row: 10-40s of nothing needs to look alive.
    ticker = setInterval(() => (elapsed += 1), 1000);
    return () => {
      if (ticker) clearInterval(ticker);
    };
  });

  $effect(() => {
    // Reset the counter whenever the running year changes.
    void busy;
    elapsed = 0;
  });

  // The poll belongs to the download, not to this page being open, but there
  // is no point polling for a page nobody is looking at either.
  onDestroy(() => {
    stopHistoryPoll();
    if (showTimer) clearTimeout(showTimer);
    cancelHide();
  });
</script>

<svelte:head><title>History · IBKR Realized P&L</title></svelte:head>

<div class="page">
  <PageHeader eyebrow="Local store · Statement history" title="History" sticky />

  <AlertBar messages={[$historyError, note]} />

  <div class="intro">
    IBKR serves the five previous calendar years plus the current one, though a
    year at the far end of that range may come back empty if it predates the
    account's own Flex retention. A year is downloaded once and kept — a
    closed year never changes, so it is never re-fetched. Downloads run one at
    a time and take 10–40 seconds each.
  </div>

  {#if !$history}
    <SkeletonCard height={320} rows={5} />
  {:else}
    <div class="panel">
      <div class="scroll">
        <table>
          <thead>
            <tr>
              <th>Year</th>
              <th>Status</th>
              <th class="num">Executions</th>
              <th class="num">Realizing</th>
              <th class="num">Realized P&amp;L</th>
              <th class="num">Downloaded</th>
              <th class="act"></th>
            </tr>
          </thead>
          <tbody>
            {#each $history.years as y (y.year)}
              <tr class:running={y.state === "downloading"}>
                <td class="year">
                  {y.year}
                  {#if y.immutable}<span class="tag" title="Closed and settled — never re-fetched">locked</span>{/if}
                </td>
                <td>
                  <!-- The flex row is an inner div: making the <td> itself a
                       flex container drops it out of table layout, which
                       detaches the cell from its row entirely. -->
                  <div class="status">
                    {#if y.state === "downloading"}<span class="spinner"></span>{/if}
                    <span class:err={y.state === "error"}>{label(y)}</span>
                    {#if y.state === "downloading"}<span class="elapsed">{elapsed}s</span>{/if}
                  </div>
                </td>
                <td class="num">{y.state === "stored" ? y.trade_count.toLocaleString() : EM_DASH}</td>
                <td class="num">{y.state === "stored" ? y.realizing_count.toLocaleString() : EM_DASH}</td>
                <td class="num pnl">
                  {#if y.state === "stored" && y.realizing_count > 0}
                    <span class={toneOf(num(y.realized_pnl))}>
                      {fmtMoney(num(y.realized_pnl), y.currency)}
                    </span>
                  {:else}
                    <span class="dash">{EM_DASH}</span>
                  {/if}
                </td>
                <td class="num dim">
                  {y.downloaded_at ? fmtDateTime(y.downloaded_at) : EM_DASH}
                </td>
                <td class="act">
                  <div class="act-row">
                    {#if y.state === "stored"}
                      <!-- Plain link to the API route: the browser's own JSON
                           viewer is the whole UI, so there is nothing here to
                           wire up beyond the href -- view-only by construction. -->
                      <a
                        class="view-link"
                        href={rawYearUrl(y.year)}
                        target="_blank"
                        rel="noopener"
                        onmouseenter={(e) => onViewEnter(y.year, e)}
                        onmouseleave={onViewLeave}
                      >
                        View JSON
                      </a>
                    {/if}
                    <button
                      class="run-btn"
                      disabled={busy !== null}
                      onclick={() => start(y.year)}
                    >
                      {buttonLabel(y)}
                    </button>
                  </div>
                </td>
              </tr>
              {#if y.error && y.state !== "downloading"}
                <tr class="err-row"><td colspan="7">{y.year}: {y.error}</td></tr>
              {/if}
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {/if}
</div>

{#if tooltip}
  <div
    class="json-tooltip"
    style="left: {tooltip.x}px; top: {tooltip.y}px;"
    onmouseenter={cancelHide}
    onmouseleave={scheduleHide}
  >
    {#if tooltipText === null}
      <span class="dim">Loading preview…</span>
    {:else}
      <pre>{tooltipText}</pre>
    {/if}
  </div>
{/if}

<style>
  .page {
    padding: var(--page-py) var(--page-px);
    width: 100%;
  }

  .intro {
    max-width: 760px;
    margin-bottom: 16px;
    font-size: var(--text-sm);
    line-height: 1.5;
    color: var(--dim-70);
  }

  .panel {
    background: var(--surface);
    border: 1px solid var(--border-05);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }
  .scroll {
    overflow-x: auto;
  }

  table {
    width: 100%;
    min-width: 720px;
    border-collapse: collapse;
    font-family: var(--font-sans);
    font-feature-settings: "ss01", "cv11";
  }
  th {
    padding: 8px 18px;
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--dim-70);
    text-align: left;
    white-space: nowrap;
    border-bottom: 1px solid var(--border-05);
  }
  th.num {
    text-align: right;
  }
  th.act {
    text-align: right;
  }

  td {
    padding: 10px 18px;
    font-size: var(--text-xs);
    color: var(--text);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
    border-bottom: 1px solid var(--border-05);
  }
  td.num {
    text-align: right;
  }
  td.act {
    text-align: right;
  }
  td.dim {
    color: var(--dim-70);
  }
  tbody tr:last-child td {
    border-bottom: none;
  }
  tr.running td {
    background: var(--surface-02);
  }

  .year {
    font-weight: var(--weight-bold);
    font-size: var(--text-sm);
  }
  .tag {
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    color: var(--dim-45);
    margin-left: 6px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .status {
    display: flex;
    align-items: center;
    gap: 7px;
    color: var(--dim-70);
  }
  .status .err {
    color: var(--dn);
    font-weight: var(--weight-semibold);
  }
  .elapsed {
    color: var(--dim-45);
    font-variant-numeric: tabular-nums;
  }

  .pnl {
    font-weight: var(--weight-semibold);
  }
  .pos {
    color: var(--up);
  }
  .neg {
    color: var(--dn);
  }
  .flat {
    color: var(--text);
  }
  .dash {
    color: var(--dim-35);
  }

  .err-row td {
    padding-top: 0;
    font-size: var(--text-2xs);
    color: var(--dn);
    white-space: normal;
  }

  .act-row {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 14px;
  }

  .view-link {
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: 0.02em;
    color: var(--dim-55);
    text-decoration: underline;
    text-underline-offset: 2px;
    white-space: nowrap;
  }
  .view-link:hover {
    color: var(--text);
  }

  /* The primary action, carried over from ui-reference's data-cache page. */
  .run-btn {
    font-family: var(--font-sans);
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.04em;
    text-transform: uppercase;
    padding: 7px 14px;
    min-width: 116px;
    border-radius: var(--radius-md);
    border: 1px solid var(--ink);
    background: var(--ink);
    color: var(--on-ink);
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .run-btn:hover:not(:disabled) {
    opacity: 0.85;
  }
  .run-btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  .spinner {
    display: inline-block;
    width: 10px;
    height: 10px;
    border: 2px solid var(--surface-10);
    border-top-color: var(--ink);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    flex-shrink: 0;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .spinner {
      animation: none;
    }
  }

  /* Fixed, not absolute: the table sits inside .scroll (overflow-x: auto),
     which would clip an absolutely-positioned child. Position is computed in
     script from the hovered link's own bounding rect.

     Content is usually taller than max-height (two pretty-printed trades run
     well past it), so this scrolls -- which means it has to accept the
     mouse. Its own mouseenter/mouseleave (in script) keep it from closing
     out from under a cursor that has moved onto it to do that. */
  .json-tooltip {
    position: fixed;
    z-index: 50;
    width: 380px;
    max-height: 280px;
    overflow: auto;
    padding: 12px 14px;
    background: var(--surface);
    border: 1px solid var(--border-10);
    border-radius: var(--radius-md);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.16);
  }
  .json-tooltip pre {
    margin: 0;
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    font-size: var(--text-2xs);
    line-height: 1.5;
    white-space: pre;
    color: var(--text);
  }
  .json-tooltip .dim {
    font-size: var(--text-xs);
    color: var(--dim-55);
  }
</style>
