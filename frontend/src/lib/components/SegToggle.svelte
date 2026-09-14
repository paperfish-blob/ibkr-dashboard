<script lang="ts">
  // Carried over from ui-reference/src/lib/components/SegToggle.svelte.
  type Option = string | { label: string; value: string };
  interface Props {
    options: Option[];
    active: string;
    label?: string;
    onChange?: (value: string) => void;
  }
  let { options, active, label, onChange }: Props = $props();
  const valueOf = (o: Option) => (typeof o === "string" ? o : o.value);
  const labelOf = (o: Option) => (typeof o === "string" ? o : o.label);
</script>

<div class="seg">
  {#if label}
    <span class="seg-label">{label}</span>
  {/if}
  {#each options as o, i (valueOf(o))}
    {@const is = valueOf(o) === active}
    <button
      class="seg-btn"
      class:active={is}
      class:first={i === 0}
      onclick={() => onChange?.(valueOf(o))}
    >
      {labelOf(o)}
    </button>
  {/each}
</div>

<style>
  .seg {
    display: inline-flex;
    align-items: stretch;
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
    background: var(--surface);
    font-family: var(--font-sans);
    font-variant-numeric: tabular-nums;
  }
  .seg-label {
    font-size: var(--text-2xs);
    font-weight: var(--weight-semibold);
    color: var(--dim-55);
    letter-spacing: 0.12em;
    padding: 7px 10px;
    border-right: 1px solid var(--border-05);
    display: inline-flex;
    align-items: center;
  }
  .seg-btn {
    padding: 7px 12px;
    border: none;
    border-left: 1px solid var(--border-05);
    background: transparent;
    color: var(--dim-70);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    letter-spacing: 0.04em;
    cursor: pointer;
    font-family: inherit;
    font-variant-numeric: inherit;
  }
  .seg-btn.first {
    border-left: none;
  }
  .seg-btn.active {
    background: var(--ink);
    color: var(--on-ink);
    font-weight: var(--weight-bold);
  }
</style>
