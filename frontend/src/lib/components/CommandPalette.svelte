<script lang="ts">
  /**
   * Ported from ui-reference/src/lib/components/CommandPalette.svelte --
   * same trigger, keyboard mechanics and styling, with NAV rebuilt from
   * this app's own +layout.svelte nav list. A couple of entries route
   * through their nav bar's default query string (e.g. Positions opens
   * pre-filtered to closed/entry) rather than the bare path, via `href`;
   * `path` stays the clean string shown in the row.
   */
  import { goto } from "$app/navigation";

  interface NavItem {
    label: string;
    path: string;
    href?: string;
    keywords: string[];
    icon: string;
  }

  const NAV: NavItem[] = [
    {
      label: "Overview",
      path: "/",
      href: "/?reset=1",
      keywords: ["overview", "home", "dashboard", "summary"],
      icon: "M2 12l4-5 3 3 5-6M2 14h12",
    },
    {
      label: "Transactions",
      path: "/transactions",
      href: "/transactions?reset=1",
      keywords: ["transactions", "ledger", "trades", "fills", "executions"],
      icon: "M2 4h12M2 8h12M2 12h8",
    },
    {
      label: "Positions Overview",
      path: "/positions/overview",
      href: "/positions/overview?reset=1",
      keywords: ["positions overview", "summary", "monthly", "streak"],
      icon: "M3 3v10h10M6 10l1.3-2 1.4 1L11 6",
    },
    {
      label: "Positions",
      path: "/positions",
      href: "/positions?filter=closed&groupBy=entry&reset=1",
      keywords: ["positions", "closed", "realized", "round-trip", "ledger"],
      icon: "M3 3v10h10M5.5 10.5l2.5-3 2 2 2.5-3.5",
    },
    {
      label: "Open Positions",
      path: "/positions/open",
      href: "/positions/open?reset=1",
      keywords: ["open positions", "unrealized", "held", "current"],
      icon: "M2 6.5h12v6.5H2zM6 6.5V4.8A1.3 1.3 0 0 1 7.3 3.5h1.4A1.3 1.3 0 0 1 10 4.8v1.7",
    },
    {
      label: "History",
      path: "/history",
      keywords: ["history", "downloads", "flex", "statement", "sync"],
      icon: "M8 2c3.3 0 6 1 6 2.2S11.3 6.5 8 6.5 2 5.4 2 4.2 4.7 2 8 2zM2 4.2v7.6C2 13 4.7 14 8 14s6-1 6-2.2V4.2M2 8c0 1.2 2.7 2.2 6 2.2s6-1 6-2.2",
    },
  ];

  interface Props { searchKeywords?: boolean }
  let { searchKeywords = false }: Props = $props();

  let open = $state(false);
  let query = $state("");
  let cursor = $state(0);
  let inputEl: HTMLInputElement | undefined = $state();
  let cmdHeld = $state(false);

  const results = $derived(
    query.trim() === ""
      ? NAV
      : NAV.filter((item) => {
          const q = query.toLowerCase();
          return (
            item.label.toLowerCase().startsWith(q) ||
            (searchKeywords && item.keywords.some((k) => k.startsWith(q)))
          );
        }),
  );

  $effect(() => {
    // clamp cursor when results shrink
    if (cursor >= results.length) cursor = Math.max(0, results.length - 1);
  });

  function openPalette() {
    open = true;
    query = "";
    cursor = 0;
    // wait one tick for the input to mount
    setTimeout(() => inputEl?.focus(), 0);
  }

  function closePalette() {
    open = false;
    query = "";
  }

  function select(item: NavItem, newTab = false) {
    closePalette();
    const target = item.href ?? item.path;
    if (newTab) window.open(target, "_blank");
    else goto(target);
  }

  // Capture-phase listener so '/' always wins before PageHeader or any other handler.
  $effect(() => {
    function onCapture(e: KeyboardEvent) {
      if (e.key === "/") {
        if (open) return; // already open -- let the input receive it normally
        e.preventDefault();
        e.stopPropagation();
        openPalette();
      }
    }
    window.addEventListener("keydown", onCapture, { capture: true });
    return () => window.removeEventListener("keydown", onCapture, { capture: true });
  });

  function onWindowKeydown(e: KeyboardEvent) {
    cmdHeld = e.metaKey || e.ctrlKey;
    if (!open) return;
    if (e.key === "Escape") {
      e.preventDefault();
      closePalette();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      cursor = (cursor + 1) % results.length;
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      cursor = (cursor - 1 + results.length) % results.length;
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      if (results[cursor]) select(results[cursor], e.metaKey || e.ctrlKey);
      return;
    }
  }

  function onWindowKeyup(e: KeyboardEvent) {
    cmdHeld = e.metaKey || e.ctrlKey;
  }

  function onBackdropClick(e: MouseEvent) {
    if (e.target === e.currentTarget) closePalette();
  }
</script>

<svelte:window onkeydown={onWindowKeydown} onkeyup={onWindowKeyup} />

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div class="backdrop" onclick={onBackdropClick}>
    <div class="palette" role="dialog" aria-modal="true" aria-label="Command palette">
      <div class="search-row">
        <svg class="search-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="6.5" cy="6.5" r="4" />
          <path d="M10 10l3.5 3.5" stroke-linecap="round" />
        </svg>
        <input
          bind:this={inputEl}
          bind:value={query}
          class="search-input"
          placeholder="Go to page…"
          autocomplete="off"
          spellcheck="false"
        />
        <kbd class="esc-hint">esc</kbd>
      </div>

      <div class="divider"></div>

      {#if results.length === 0}
        <p class="empty">No pages match "{query}"</p>
      {:else}
        <ul class="list" role="listbox">
          {#each results as item, i (item.path)}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <li
              class="item"
              class:active={i === cursor}
              role="option"
              aria-selected={i === cursor}
              onmouseenter={() => (cursor = i)}
              onclick={(e) => select(item, e.metaKey || e.ctrlKey)}
            >
              <svg class="item-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
                <path d={item.icon} />
              </svg>
              <span class="item-label">{item.label}</span>
              {#if cmdHeld && i === cursor}
                <span class="item-newtab">new tab</span>
              {:else}
                <span class="item-path">{item.path}</span>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}

      <div class="footer">
        <span><kbd>↑↓</kbd> navigate</span>
        <span><kbd>↵</kbd> go</span>
        <span><kbd>⌘↵</kbd> new tab</span>
        <span><kbd>esc</kbd> close</span>
      </div>
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 9999;
    background: rgba(var(--ink-rgb), 0.35);
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding-top: 18vh;
    backdrop-filter: blur(2px);
  }

  .palette {
    width: 520px;
    max-width: calc(100vw - 32px);
    background: var(--surface);
    border: 1px solid var(--border-12);
    border-radius: var(--radius-lg);
    box-shadow:
      0 16px 48px rgba(var(--ink-rgb), 0.14),
      0 4px 12px rgba(var(--ink-rgb), 0.06);
    overflow: hidden;
  }

  /* -- search row -- */
  .search-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 16px;
  }

  .search-icon {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
    color: var(--dim-55);
  }

  .search-input {
    flex: 1;
    border: none;
    outline: none;
    background: transparent;
    font-family: var(--font-sans);
    font-size: var(--text-lg);
    color: var(--text);
  }

  .search-input::placeholder {
    color: var(--dim-35);
  }

  .esc-hint {
    font-family: var(--font-sans);
    font-size: var(--text-xs);
    color: var(--dim-55);
    background: var(--surface-06);
    border: 1px solid var(--border-08);
    border-radius: var(--radius-sm);
    padding: 2px 6px;
    flex-shrink: 0;
  }

  .divider {
    height: 1px;
    background: var(--border-05);
  }

  /* -- results list -- */
  .list {
    list-style: none;
    margin: 0;
    padding: 6px;
  }

  .item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 12px;
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: background 0.1s;
  }

  .item.active {
    background: #0c0d10;
  }

  .item-icon {
    width: 15px;
    height: 15px;
    flex-shrink: 0;
    color: var(--dim-55);
  }

  .item.active .item-icon {
    color: rgba(255, 255, 255, 0.5);
  }

  .item-label {
    flex: 1;
    font-family: var(--font-sans);
    font-size: var(--text-md);
    font-weight: var(--weight-medium);
    color: var(--text);
  }

  .item.active .item-label {
    color: #ffffff;
  }

  .item-path {
    font-family: var(--font-sans);
    font-size: var(--text-sm);
    color: var(--dim-35);
  }

  .item.active .item-path {
    color: rgba(255, 255, 255, 0.5);
  }

  .item-newtab {
    font-family: var(--font-sans);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: rgba(255, 255, 255, 0.6);
    background: rgba(255, 255, 255, 0.12);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: var(--radius-sm);
    padding: 2px 7px;
  }

  /* -- empty state -- */
  .empty {
    padding: 20px 16px;
    text-align: center;
    font-family: var(--font-sans);
    font-size: var(--text-md);
    color: var(--dim-55);
    margin: 0;
  }

  /* -- footer hints -- */
  .footer {
    display: flex;
    gap: 16px;
    padding: 10px 16px;
    border-top: 1px solid var(--border-05);
    font-family: var(--font-sans);
    font-size: var(--text-xs);
    color: var(--dim-35);
  }

  .footer span {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .footer kbd {
    font-family: var(--font-sans);
    background: var(--surface-06);
    border: 1px solid var(--border-08);
    border-radius: var(--radius-sm);
    padding: 1px 5px;
    font-size: var(--text-xs);
    color: var(--dim-55);
  }
</style>
