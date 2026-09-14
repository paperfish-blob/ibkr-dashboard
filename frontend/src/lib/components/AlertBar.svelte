<script lang="ts">
  /**
   * Problems that must not be mistaken for data.
   *
   * An expired Flex token would otherwise render as a confident $0.00, and a
   * multi-currency statement sums raw values without FX conversion. Both need
   * to be visible rather than silently folded into the figures.
   */
  interface Props {
    messages: (string | null | undefined)[];
  }
  let { messages }: Props = $props();

  const shown = $derived(messages.filter((m): m is string => Boolean(m)));
</script>

{#if shown.length}
  <div class="alert" role="status">
    {#each shown as message}
      <div class="line">{message}</div>
    {/each}
  </div>
{/if}

<style>
  .alert {
    padding: 12px 16px;
    margin-bottom: 16px;
    border: 1px solid var(--amber-bg);
    border-radius: var(--radius-lg);
    background: var(--amber-bg);
    color: var(--amber);
    font-size: var(--text-sm);
    line-height: 1.45;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
</style>
