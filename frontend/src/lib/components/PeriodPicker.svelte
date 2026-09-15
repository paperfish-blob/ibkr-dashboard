<script lang="ts">
  /**
   * Period selector: "All" plus every downloaded year.
   *
   * Only years that are actually downloaded appear. Offering 2022 when it has
   * never been fetched would present an empty result as though the account had
   * no trades that year, which is the confident-zero failure this project
   * avoids everywhere else — the History page is where years get added.
   */
  import SegToggle from "./SegToggle.svelte";
  import { history, period, setPeriod, refreshHistory } from "$lib/stores";
  import { onMount } from "svelte";

  const options = $derived.by(() => {
    const years = ($history?.years ?? [])
      .filter((y) => y.state === "stored" && y.trade_count > 0)
      .map((y) => ({ label: String(y.year), value: String(y.year) }));
    return [{ label: "All", value: "all" }, ...years];
  });

  onMount(() => {
    // The picker needs to know which years exist; the History page may never
    // have been opened.
    if (!$history) refreshHistory();
  });
</script>

{#if options.length > 1}
  <SegToggle {options} active={$period} onChange={setPeriod} />
{/if}
