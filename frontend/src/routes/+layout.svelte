<script lang="ts">
  import "../app.css";
  import { page } from "$app/stores";

  let { children } = $props();

  const nav = [
    { href: "/", label: "Overview" },
    { href: "/transactions", label: "Transactions" },
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
            {:else}
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 4h12M2 8h12M2 12h8" />
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
