<script lang="ts">
  /**
   * Consolidated "Filters" popover for the Positions page -- date range,
   * side (long/short), and asset category together behind one pill with a
   * count badge, rather than each as its own toolbar control. Symbol and
   * Month stay as their own SymbolFilter/MonthFilter pills since those are
   * the two people reach for constantly; these three are reached for less
   * often and would otherwise crowd the toolbar.
   */
  import type { PosSide } from "$lib/stores";

  interface Props {
    dateFrom: string | null;
    dateTo: string | null;
    onDateChange: (from: string | null, to: string | null) => void;
    side: PosSide;
    onSideChange: (side: PosSide) => void;
    /** Asset category (e.g. "STK", "CFD") -> position count, for the chip
     *  list -- same counts-map convention as SymbolFilter. */
    categories: Map<string, number>;
    activeCategories: string[];
    onCategoriesChange: (next: string[]) => void;
    /** Positions left after every active filter (not just these three) --
     *  shown in the popover footer so a change's effect is visible without
     *  closing the popover. */
    matchCount: number;
  }
  let {
    dateFrom,
    dateTo,
    onDateChange,
    side,
    onSideChange,
    categories,
    activeCategories,
    onCategoriesChange,
    matchCount,
  }: Props = $props();

  let open = $state(false);
  let container: HTMLDivElement | undefined = $state();

  const activeCount = $derived(
    (dateFrom || dateTo ? 1 : 0) + (side !== "all" ? 1 : 0) + (activeCategories.length > 0 ? 1 : 0),
  );

  const categoryList = $derived([...categories.keys()].sort((a, b) => (categories.get(b) ?? 0) - (categories.get(a) ?? 0)));

  function toggleCategory(cat: string) {
    onCategoriesChange(activeCategories.includes(cat) ? activeCategories.filter((c) => c !== cat) : [...activeCategories, cat]);
  }

  function clearAll() {
    onDateChange(null, null);
    onSideChange("all");
    onCategoriesChange([]);
  }

  // "YYYY-MM-DD" in local time, matching how open_date/exit_date already
  // read on the wire -- Date#toISOString would shift by the viewer's UTC
  // offset and could land on the wrong day.
  function isoDate(d: Date): string {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }
  function daysAgo(n: number): string {
    const d = new Date();
    d.setDate(d.getDate() - n);
    return isoDate(d);
  }
  const today = isoDate(new Date());
  const startOfMonth = $derived.by(() => {
    const d = new Date();
    return isoDate(new Date(d.getFullYear(), d.getMonth(), 1));
  });
  const startOfYear = $derived.by(() => {
    const d = new Date();
    return isoDate(new Date(d.getFullYear(), 0, 1));
  });

  const PRESETS = $derived([
    { label: "Last 30d", from: daysAgo(30), to: today },
    { label: "Last 90d", from: daysAgo(90), to: today },
    { label: "This month", from: startOfMonth, to: today },
    { label: "YTD", from: startOfYear, to: today },
  ]);

  function applyPreset(p: { from: string; to: string }) {
    onDateChange(p.from, p.to);
  }

  $effect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (container && !container.contains(e.target as Node)) open = false;
    }
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  });
</script>

<div class="anchor" bind:this={container}>
  <button class="pill" class:active={activeCount > 0} onclick={() => (open = !open)}>
    Filters
    {#if activeCount > 0}<span class="badge">{activeCount}</span>{/if}
    <span class="chev">▾</span>
  </button>

  {#if open}
    <div class="panel">
      <div class="sec">
        <div class="sec-label">Date range</div>
        <div class="date-row">
          <input
            type="date"
            value={dateFrom ?? ""}
            max={dateTo ?? undefined}
            onchange={(e) => onDateChange(e.currentTarget.value || null, dateTo)}
          />
          <span class="to">–</span>
          <input
            type="date"
            value={dateTo ?? ""}
            min={dateFrom ?? undefined}
            onchange={(e) => onDateChange(dateFrom, e.currentTarget.value || null)}
          />
        </div>
        <div class="presets">
          {#each PRESETS as p (p.label)}
            <button
              class="preset-chip"
              class:active={dateFrom === p.from && dateTo === p.to}
              onclick={() => applyPreset(p)}
            >
              {p.label}
            </button>
          {/each}
        </div>
      </div>

      <div class="sec">
        <div class="sec-label">Side</div>
        <div class="chip-row">
          <button class="chip" class:active={side === "all"} onclick={() => onSideChange("all")}>All</button>
          <button class="chip" class:active={side === "long"} onclick={() => onSideChange("long")}>Long</button>
          <button class="chip" class:active={side === "short"} onclick={() => onSideChange("short")}>Short</button>
        </div>
      </div>

      {#if categoryList.length > 1}
        <div class="sec">
          <div class="sec-label">Asset category</div>
          <div class="chip-row">
            <button class="chip" class:active={activeCategories.length === 0} onclick={() => onCategoriesChange([])}>
              All
            </button>
            {#each categoryList as cat (cat)}
              <button class="chip" class:active={activeCategories.includes(cat)} onclick={() => toggleCategory(cat)}>
                {cat}
              </button>
            {/each}
          </div>
        </div>
      {/if}

      <div class="foot">
        <button class="clear-link" onclick={clearAll} disabled={activeCount === 0}>Clear all</button>
        <span class="match-count">{matchCount} position{matchCount === 1 ? "" : "s"}</span>
      </div>
    </div>
  {/if}
</div>

<style>
  .anchor {
    position: relative;
  }
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 11px;
    border-radius: var(--radius-pill);
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--dim-70);
    font-family: var(--font-sans);
    font-size: var(--text-xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.01em;
    cursor: pointer;
    white-space: nowrap;
  }
  .pill.active {
    background: var(--ink);
    color: var(--on-ink);
    border-color: var(--ink);
  }
  .pill .badge {
    background: var(--accent);
    color: #fff;
    font-size: 9px;
    font-weight: var(--weight-bold);
    border-radius: var(--radius-pill);
    padding: 1px 5px;
  }
  .pill.active .badge {
    background: rgba(255, 255, 255, 0.25);
  }
  .pill .chev {
    font-size: 9px;
    opacity: 0.6;
  }

  .panel {
    position: absolute;
    top: calc(100% + 6px);
    right: 0;
    width: 300px;
    background: var(--surface);
    border: 1px solid var(--border-08);
    border-radius: var(--radius-md);
    box-shadow: 0 12px 32px rgba(12, 13, 16, 0.16);
    padding: 14px;
    z-index: 20;
  }
  .sec {
    margin-bottom: 14px;
  }
  .sec:last-of-type {
    margin-bottom: 0;
  }
  .sec-label {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--dim-45);
    margin-bottom: 7px;
  }

  .date-row {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .date-row input[type="date"] {
    flex: 1;
    min-width: 0;
    font-family: inherit;
    font-size: var(--text-xs);
    padding: 6px 8px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text);
    background: var(--surface);
  }
  .date-row input[type="date"]:focus {
    outline: 2px solid var(--accent);
    outline-offset: -1px;
  }
  .date-row .to {
    color: var(--dim-45);
    font-size: var(--text-xs);
    flex: none;
  }

  .presets {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin-top: 8px;
  }
  .preset-chip {
    font-family: inherit;
    font-size: 10px;
    font-weight: var(--weight-medium);
    color: var(--dim-55);
    background: var(--surface-04);
    border: none;
    border-radius: var(--radius-pill);
    padding: 4px 9px;
    cursor: pointer;
  }
  .preset-chip.active {
    background: var(--accent);
    color: #fff;
  }

  .chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .chip {
    font-family: inherit;
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    color: var(--dim-70);
    background: var(--surface-04);
    border: 1px solid transparent;
    border-radius: var(--radius-pill);
    padding: 5px 11px;
    cursor: pointer;
  }
  .chip.active {
    background: var(--accent-bg);
    color: var(--accent);
    border-color: rgba(91, 108, 255, 0.3);
    font-weight: var(--weight-semibold);
  }

  .foot {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid var(--border-05);
  }
  .clear-link {
    font-family: inherit;
    font-size: var(--text-xs);
    font-weight: var(--weight-semibold);
    color: var(--dim-45);
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
  }
  .clear-link:hover:not(:disabled) {
    color: var(--dn);
  }
  .clear-link:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .match-count {
    font-size: var(--text-2xs);
    color: var(--dim-45);
    font-variant-numeric: tabular-nums;
  }
</style>
