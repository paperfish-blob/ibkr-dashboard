<script lang="ts">
  /**
   * Month filter: a single calendar pill that opens a year-grouped checklist,
   * same interaction shape as SymbolFilter's overflow panel (multi-select,
   * search-free since a year's worth of months is short enough to scan).
   * Only months that actually have trades appear -- same reasoning as
   * PeriodPicker only offering downloaded years, not the full calendar.
   */
  interface Props {
    /** "YYYY-MM" -> however many trades fall in that month. */
    counts: Map<string, number>;
    active: string[];
    onChange: (next: string[]) => void;
  }
  let { counts, active, onChange }: Props = $props();

  interface MonthOpt {
    key: string; // "2026-07"
    label: string; // "Jul 2026"
    short: string; // "Jul"
    year: string;
    n: number;
  }

  const options = $derived.by((): MonthOpt[] =>
    [...counts.entries()].map(([key, n]) => {
      const [y, m] = key.split("-").map(Number);
      const d = new Date(y, m - 1, 1);
      return {
        key,
        label: d.toLocaleDateString("en-US", { month: "short", year: "numeric" }),
        short: d.toLocaleDateString("en-US", { month: "short" }),
        year: String(y),
        n,
      };
    }),
  );

  // Newest year first; within a year, calendar order (Jan -> Dec).
  const years = $derived([...new Set(options.map((o) => o.year))].sort((a, b) => b.localeCompare(a)));
  function monthsOf(year: string): MonthOpt[] {
    return options.filter((o) => o.year === year).sort((a, b) => a.key.localeCompare(b.key));
  }

  const triggerLabel = $derived.by(() => {
    if (active.length === 0) return "All months";
    if (active.length === 1) return options.find((o) => o.key === active[0])?.label ?? active[0];
    return `${active.length} months`;
  });

  let menuOpen = $state(false);
  let container: HTMLDivElement | undefined = $state();

  function toggle(key: string) {
    onChange(active.includes(key) ? active.filter((k) => k !== key) : [...active, key]);
  }
  function clear() {
    onChange([]);
    menuOpen = false;
  }

  $effect(() => {
    if (!menuOpen) return;
    function onDocClick(e: MouseEvent) {
      if (container && !container.contains(e.target as Node)) menuOpen = false;
    }
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  });
</script>

{#if options.length > 1 || active.length > 0}
  <div class="more" bind:this={container}>
    <button class="pill" class:active={active.length > 0} onclick={() => (menuOpen = !menuOpen)}>
      <svg class="cal-icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" />
      </svg>
      {triggerLabel}
    </button>
    {#if menuOpen}
      <div class="panel">
        {#each years as year (year)}
          <div class="year-group">
            <div class="year-hd">{year}</div>
            <div class="grid">
              {#each monthsOf(year) as o (o.key)}
                <button class="mbtn" class:checked={active.includes(o.key)} onclick={() => toggle(o.key)}>
                  {o.short}<span class="n">{o.n}</span>
                </button>
              {/each}
            </div>
          </div>
        {/each}
        {#if active.length}
          <div class="foot">
            <button class="clear" onclick={clear}>Clear filter</button>
          </div>
        {/if}
      </div>
    {/if}
  </div>
{/if}

<style>
  .more {
    position: relative;
  }

  .pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
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
  .cal-icon {
    flex: none;
    opacity: 0.6;
  }
  .pill.active {
    background: var(--ink);
    color: var(--on-ink);
    border-color: var(--ink);
  }
  .pill.active .cal-icon {
    opacity: 1;
  }

  .panel {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    width: 250px;
    background: var(--surface);
    border: 1px solid var(--border-08);
    border-radius: var(--radius-md);
    box-shadow: 0 12px 32px rgba(12, 13, 16, 0.16);
    padding: 10px;
    z-index: 20;
  }

  .year-group + .year-group {
    margin-top: 10px;
  }
  .year-hd {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--dim-45);
    padding: 2px 6px 4px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 4px;
  }

  .mbtn {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 4px;
    padding: 6px 8px;
    border: 1px solid transparent;
    background: var(--surface-04);
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-family: inherit;
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    color: var(--text);
  }
  .mbtn:hover {
    border-color: var(--border-12);
  }
  .mbtn.checked {
    background: var(--ink);
    color: var(--on-ink);
    border-color: var(--ink);
    font-weight: var(--weight-semibold);
  }
  .mbtn .n {
    font-size: var(--text-2xs);
    color: var(--dim-45);
    font-variant-numeric: tabular-nums;
  }
  .mbtn.checked .n {
    color: rgba(255, 255, 255, 0.6);
  }

  .foot {
    display: flex;
    justify-content: flex-end;
    padding-top: 8px;
    margin-top: 8px;
    border-top: 1px solid var(--border-05);
  }
  .clear {
    background: none;
    border: none;
    padding: 4px 6px;
    font-family: inherit;
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    color: var(--dim-55);
    cursor: pointer;
  }
  .clear:hover {
    color: var(--dn);
  }
</style>
