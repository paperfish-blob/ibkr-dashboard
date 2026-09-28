<script lang="ts">
  /** A small boolean on/off control, for a page-level setting that isn't a
   *  multi-value choice (that's SegToggle's job) -- e.g. "include realized
   *  P&L" on the Open Positions page. */
  interface Props {
    checked: boolean;
    label?: string;
    ariaLabel?: string;
    onChange: (value: boolean) => void;
  }
  let { checked, label, ariaLabel, onChange }: Props = $props();
</script>

<div class="switch-wrap">
  {#if label}<span class="switch-label">{label}</span>{/if}
  <button
    class="switch"
    class:on={checked}
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={ariaLabel ?? label}
    onclick={() => onChange(!checked)}
  >
    <span class="knob"></span>
  </button>
</div>

<style>
  .switch-wrap {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--surface);
    padding: 6px 10px 6px 12px;
  }
  .switch-label {
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    color: var(--text);
    white-space: nowrap;
  }
  .switch {
    position: relative;
    width: 32px;
    height: 18px;
    border-radius: var(--radius-pill);
    background: var(--dim-20);
    border: none;
    cursor: pointer;
    flex: none;
    padding: 0;
    transition: background 0.15s;
  }
  .switch.on {
    background: var(--accent);
  }
  .switch .knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #fff;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
    transition: transform 0.15s;
  }
  .switch.on .knob {
    transform: translateX(14px);
  }
</style>
