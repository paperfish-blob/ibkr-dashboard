<script lang="ts">
  import "../app.css";
  import { page } from "$app/stores";

  let { children } = $props();

  const nav = [
    { href: "/", label: "Overview" },
    { href: "/transactions", label: "Transactions" },
    { href: "/round-trips", label: "Round Trips" },
    { href: "/history", label: "History" },
  ];

  const current = $derived($page.url.pathname);
</script>

<div class="shell">
  <header class="header">
    <a href="/" class="brand">IBKR&nbsp;·&nbsp;Realized P&amp;L</a>
    <nav class="nav">
      {#each nav as item (item.href)}
        <a href={item.href} class:active={current === item.href}>
          <span class="nav-link">
            {#if item.href === "/"}
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 12l4-5 3 3 5-6" />
                <path d="M2 14h12" />
              </svg>
            {:else if item.href === "/transactions"}
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 4h12M2 8h12M2 12h8" />
              </svg>
            {:else if item.href === "/round-trips"}
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M3.5 6H10a2 2 0 0 1 2 2v1" />
                <path d="M8.5 4L11 6l-2.5 2" />
                <path d="M12.5 10H6a2 2 0 0 1-2-2V7" />
                <path d="M7.5 12L5 10l2.5-2" />
              </svg>
            {:else}
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M8 2c3.3 0 6 1 6 2.2S11.3 6.5 8 6.5 2 5.4 2 4.2 4.7 2 8 2z" />
                <path d="M2 4.2v7.6C2 13 4.7 14 8 14s6-1 6-2.2V4.2M2 8c0 1.2 2.7 2.2 6 2.2s6-1 6-2.2" />
              </svg>
            {/if}
            {item.label}
          </span>
        </a>
      {/each}
    </nav>
  </header>

  <main class="main">
    {@render children()}
  </main>
</div>

<style>
  .shell {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
  }

  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 14px 24px;
    border-bottom: 1px solid var(--border-05);
    background: var(--surface);
    flex-wrap: wrap;
  }

  .brand {
    font-family: var(--font-sans);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.02em;
    color: var(--text);
    text-decoration: none;
  }
  .brand:hover {
    color: var(--text);
    text-decoration: none;
  }

  .nav {
    display: flex;
    gap: 16px;
    font-size: var(--text-md);
  }
  .nav :global(a) {
    color: var(--dim-55);
  }
  .nav :global(a:hover) {
    color: var(--text);
    text-decoration: none;
  }
  .nav :global(a.active) {
    color: var(--text);
    font-weight: var(--weight-semibold);
  }
  .nav :global(.nav-link) {
    display: flex;
    align-items: center;
    gap: 5px;
  }
  .nav :global(.nav-link svg) {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
  }

  .main {
    flex: 1;
    width: 100%;
  }
</style>
