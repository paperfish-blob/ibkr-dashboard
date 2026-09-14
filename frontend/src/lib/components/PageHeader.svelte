<script lang="ts">
  /**
   * Page title bar. Pared down from ui-reference's PageHeader (no search, no
   * news ticker, no clock) but keeping its structure: a two-part eyebrow over
   * the title, actions right-aligned, and the negative-margin trick that lets
   * a sticky header run full-bleed out of the page's own padding.
   */
  import type { Snippet } from "svelte";

  interface Props {
    eyebrow: string;
    title: string;
    marginBottom?: string;
    sticky?: boolean;
    onRefresh?: () => void;
    refreshing?: boolean;
    right?: Snippet;
  }
  let {
    eyebrow,
    title,
    marginBottom = "24px",
    sticky = false,
    onRefresh,
    refreshing = false,
    right,
  }: Props = $props();
</script>

<div class="hd" class:sticky style="margin-bottom:{marginBottom}">
  <div class="hd-left">
    <div class="title-stack">
      <div class="eyebrow">{eyebrow}</div>
      <h1>{title}</h1>
    </div>
  </div>

  <div class="hd-right">
    {#if right}{@render right()}{/if}
    {#if onRefresh}
      <button
        class="ghost-btn icon"
        onclick={onRefresh}
        disabled={refreshing}
        title="Refetch from IBKR, bypassing the cache"
        aria-label="Refresh"
      >
        <svg
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          class:spin={refreshing}
        >
          <path d="M14 8A6 6 0 1 1 12.2 3.7M14 2v4h-4" />
        </svg>
      </button>
    {/if}
  </div>
</div>

<style>
  .hd {
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: 16px;

    /* Break out of .page padding so the sticky bar spans the full width. */
    margin-top: calc(-1 * var(--page-py));
    margin-left: calc(-1 * var(--page-px));
    margin-right: calc(-1 * var(--page-px));
    padding: var(--page-py) var(--page-px);
  }

  .hd.sticky {
    position: sticky;
    top: 0;
    z-index: 50;
    background: var(--surface);
    border-bottom: 1px solid var(--border-05);
  }

  .hd-left {
    display: flex;
    align-items: center;
    gap: 16px;
    flex: 1;
    min-width: 0;
  }
  .title-stack {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }
  .hd-right {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .eyebrow {
    font-size: var(--text-xs);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--dim-55);
  }

  h1 {
    margin: 4px 0 0 0;
    font-size: var(--text-2xl);
    font-weight: var(--weight-semibold);
    letter-spacing: -0.01em;
  }

  /* The house ghost button, repeated verbatim from ui-reference. */
  .ghost-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 7px 9px;
    border: 1px solid var(--border-05);
    border-radius: var(--radius-md);
    background: var(--surface);
    color: var(--dim-55);
    font-family: var(--font-sans);
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
    cursor: pointer;
    transition:
      border-color 0.15s,
      color 0.15s,
      background 0.15s;
  }
  .ghost-btn svg {
    width: 14px;
    height: 14px;
  }
  .ghost-btn:hover:not(:disabled) {
    border-color: var(--border);
    color: var(--text);
    background: var(--surface-06);
  }
  .ghost-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .spin {
    animation: hd-spin 0.8s linear infinite;
  }
  @keyframes hd-spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .spin {
      animation: none;
    }
  }

  @media (max-width: 620px) {
    .hd {
      flex-direction: column;
      align-items: flex-start;
      gap: 12px;
    }
    .hd-right {
      justify-content: flex-start;
    }
  }
</style>
