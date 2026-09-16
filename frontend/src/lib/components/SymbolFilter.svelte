<script lang="ts">
  /**
   * Symbol filter: the account's most-traded tickers as toggle pills, with a
   * "+N more" pill opening a searchable checklist for the rest. Multi-select --
   * an active pill narrows the ledger to that symbol, several narrow to their
   * union, none means every symbol.
   */
  import type { DayGroup } from "$lib/api";

  interface Props {
    days: DayGroup[];
    active: string[];
    onChange: (next: string[]) => void;
  }
  let { days, active, onChange }: Props = $props();

  const TOP_N = 4;

  const counts = $derived.by(() => {
    const m = new Map<string, number>();
    for (const d of days) {
      for (const t of d.trades) m.set(t.symbol, (m.get(t.symbol) ?? 0) + 1);
    }
    return m;
  });
  const periodSymbols = $derived(
    [...counts.keys()].sort((a, b) => (counts.get(b) ?? 0) - (counts.get(a) ?? 0)),
  );

  // Active symbols pin to the row ahead of everything else, even one with no
  // trades in the period showing right now -- switching years shouldn't make
  // a chosen symbol disappear and read as the filter having cleared itself.
  const fillCandidates = $derived(periodSymbols.filter((s) => !active.includes(s)));
  const top = $derived([...active, ...fillCandidates.slice(0, Math.max(0, TOP_N - active.length))]);
  const rest = $derived(fillCandidates.slice(Math.max(0, TOP_N - active.length)));
  const symbols = $derived([...new Set([...periodSymbols, ...active])]);

  let menuOpen = $state(false);
  let query = $state("");
  let container: HTMLDivElement | undefined = $state();

  const restFiltered = $derived(
    query.trim()
      ? rest.filter((s) => s.toUpperCase().includes(query.trim().toUpperCase()))
      : rest,
  );

  function toggle(sym: string) {
    onChange(active.includes(sym) ? active.filter((s) => s !== sym) : [...active, sym]);
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

{#if symbols.length > 1 || active.length > 0}
  <div class="bar">
    <button class="pill" class:active={active.length === 0} onclick={() => onChange([])}>
      All symbols
    </button>
    {#each top as s (s)}
      <button class="pill" class:active={active.includes(s)} onclick={() => toggle(s)}>
        <span class="dot"></span>{s}
      </button>
    {/each}

    {#if rest.length}
      <div class="more" bind:this={container}>
        <button class="pill" onclick={() => (menuOpen = !menuOpen)}>
          +{rest.length} more
        </button>
        {#if menuOpen}
          <div class="panel">
            <input class="search" placeholder="Search symbol…" bind:value={query} />
            <div class="list">
              {#each restFiltered as s (s)}
                <button class="row" class:checked={active.includes(s)} onclick={() => toggle(s)}>
                  <span class="lbl"><span class="box"></span>{s}</span>
                  <span class="n">{counts.get(s)}</span>
                </button>
              {:else}
                <div class="empty">No matching symbol</div>
              {/each}
            </div>
            {#if active.length}
              <div class="foot">
                <button class="clear" onclick={clear}>Clear filter</button>
              </div>
            {/if}
          </div>
        {/if}
      </div>
    {/if}
  </div>
{/if}

<style>
  .bar {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
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
  .pill .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--dim-35);
    flex: none;
  }
  .pill.active {
    background: var(--ink);
    color: var(--on-ink);
    border-color: var(--ink);
  }
  .pill.active .dot {
    background: var(--on-ink);
  }

  .more {
    position: relative;
  }

  .panel {
    position: absolute;
    top: calc(100% + 6px);
    right: 0;
    width: 220px;
    background: var(--surface);
    border: 1px solid var(--border-08);
    border-radius: var(--radius-md);
    box-shadow: 0 12px 32px rgba(12, 13, 16, 0.16);
    padding: 8px;
    z-index: 20;
  }

  .search {
    width: 100%;
    padding: 7px 9px;
    border: 1px solid var(--border-08);
    border-radius: var(--radius-sm);
    background: var(--surface-alt);
    color: var(--text);
    font-family: inherit;
    font-size: var(--text-xs);
    margin-bottom: 6px;
  }
  .search:focus {
    outline: 2px solid var(--accent);
    outline-offset: -1px;
  }

  .list {
    max-height: 220px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }

  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 6px 6px;
    border: none;
    background: none;
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-family: inherit;
    font-size: var(--text-xs);
    text-align: left;
  }
  .row:hover {
    background: var(--surface-04);
  }
  .row .lbl {
    display: flex;
    align-items: center;
    gap: 7px;
    font-weight: var(--weight-semibold);
    color: var(--text);
  }
  .row .box {
    width: 13px;
    height: 13px;
    border: 1.5px solid var(--border-12);
    border-radius: 3px;
    flex: none;
  }
  .row.checked .box {
    background: var(--ink);
    border-color: var(--ink);
    position: relative;
  }
  .row.checked .box::after {
    content: "";
    position: absolute;
    left: 3px;
    top: 2px;
    width: 6px;
    height: 3px;
    border-left: 1.5px solid var(--on-ink);
    border-bottom: 1.5px solid var(--on-ink);
    transform: rotate(-45deg);
  }
  .row .n {
    color: var(--dim-45);
    font-variant-numeric: tabular-nums;
  }

  .empty {
    padding: 10px 6px;
    font-size: var(--text-xs);
    color: var(--dim-45);
  }

  .foot {
    display: flex;
    justify-content: flex-end;
    padding-top: 6px;
    margin-top: 4px;
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
