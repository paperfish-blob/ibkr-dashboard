<script lang="ts">
  /** Loading placeholder sized to the card it stands in for. Ported from
   *  ui-reference/src/lib/components/SkeletonCard.svelte. */
  interface Props {
    height?: number;
    rows?: number;
  }
  let { height = 200, rows = 3 }: Props = $props();
</script>

<div class="skeleton" style="height:{height}px">
  <div class="bar head"></div>
  {#each Array(rows) as _, i}
    <div class="bar" style="width:{[92, 74, 84, 66][i % 4]}%"></div>
  {/each}
</div>

<style>
  .skeleton {
    border: 1px solid var(--border-08);
    border-radius: var(--radius-lg);
    overflow: hidden;
    background: var(--surface);
    padding: 20px 18px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .bar {
    height: 12px;
    border-radius: var(--radius-sm);
    flex-shrink: 0;
    background: linear-gradient(
      90deg,
      var(--surface-04) 25%,
      var(--surface-10) 50%,
      var(--surface-04) 75%
    );
    background-size: 400% 100%;
    animation: shimmer 3s ease-in-out infinite;
  }
  .bar.head {
    height: 28px;
    width: 40%;
  }
  @keyframes shimmer {
    0% {
      background-position: 100% 0;
    }
    100% {
      background-position: 0 0;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .bar {
      animation: none;
    }
  }
</style>
