# IBKR Realized P&L Dashboard

A local dashboard showing the latest realized P&L for your IBKR account: a
headline total, a cumulative-P&L-over-time chart, and a per-trade
transaction ledger grouped by day.

It reads two sources and works with either one alone:

| Source | Provides | Needs |
|---|---|---|
| **Flex Web Service** | Historical realized P&L per trade | A token + query ID. No install. |
| **IB Gateway** | Today's live realized P&L (`reqPnL`) | IB Gateway running and logged in. |

IB Gateway needs an interactive login each day, so it is down much of the
time. That is expected: the dashboard falls back to Flex and shows a
"Gateway disconnected" badge rather than failing.

The UI is a SvelteKit app in [frontend/](frontend/), sharing its design
language with the `ui-reference` dashboard.

## Quick start

```bash
cp .env.example .env            # then fill in the values from the setup below

cd frontend && npm install && npm run build && cd ..
uv run uvicorn ibkr_pnl.server:app --port 9001
```

Open <http://localhost:9001>. FastAPI serves both the API and the built UI on
that one port, so there is no CORS setup and nothing else to run.

Skip the `npm` step and it still works — the server falls back to the original
single-file dashboard when `frontend/build/` is absent.

### Developing the frontend

Two processes, with Vite proxying `/api` to the backend so the browser still
sees one origin:

```bash
uv run uvicorn ibkr_pnl.server:app --port 9001   # terminal 1
cd frontend && npm run dev                       # terminal 2
```

Open <http://localhost:5173> for hot reload. Run `npm run build` again when
you want the `:9001` build to pick the changes up.

`frontend/build/` is gitignored, so switching branches does **not** touch it —
the `:9001` server keeps serving whatever was last built, even a page whose
route no longer exists on the branch you're now on. Rebuild after checking
out a different branch:

```bash
cd frontend && rm -rf build .svelte-kit && npm run build
```

## Setup

### 1. Flex Query

Client Portal → **Performance & Reports** → **Flex Queries** → new
**Activity Flex Query**:

- **Section:** Trades. Level of detail: **Execution** only (leave Order and
  Closed Lots off — enabling more than one level emits several rows per
  fill, and each row repeats the same realized P&L).
- **Fields, required for the headline and chart:** Currency, Symbol, Trade
  Date, Realized P/L, IB Commission, Buy/Sell, Quantity.
- **Fields, additionally needed for the transaction ledger:** Date/Time,
  Trade Price, Trade Money, Order Type, Notes/Codes, Exchange, Asset Class.
  Skip these and the ledger still works — those columns just render blank
  for rows missing the field.
- **Date range:** Year to Date
- **Format:** XML

Save it and note the **Query ID** → `FLEX_QUERY_ID`. If you already created
the query with only the first field set, edit it and add the second set —
no need to start over or change the query ID.

> The ledger fields' underlying XML attribute names (`tradeMoney`,
> `orderType`, etc.) are IBKR's documented names but weren't checked against
> a real export before this was written. After adding them, run `--dump`
> (below) once — if a column comes out blank in the dashboard despite being
> checked in the query, the raw attributes it prints will show the actual
> name so [flex.py](src/ibkr_pnl/sources/flex.py)'s `_first(...)` lookups
> can be corrected.

### 2. Flex token

Client Portal → **Settings** → **Account Settings** → **Flex Web Service** →
create a token → `FLEX_TOKEN`. Note its expiry; when it lapses the dashboard
shows the IBKR error rather than a misleading $0.00.

### 3. IB Gateway (optional — only for today's live figure)

Download the macOS **standalone** build. It bundles its own JRE, so you do
not need to install Java separately. After logging in, Configure → Settings →
API → Settings:

- ✅ Enable ActiveX and Socket Clients
- ✅ **Read-Only API** — leave this on. This app only reads P&L, and it
  removes any possibility of it placing an order.
- ✅ Prepare portfolio PnL data when downloading positions — `reqPnL`
  returns nothing without it
- Trusted IP `127.0.0.1`; port **4001** live / **4002** paper → `IB_PORT`

## How the two sources are combined

`reqPnL`'s `realizedPnL` **resets to zero each trading day**, so it is
*today's* figure, not a running total. Flex covers history but can also pick
up part of today. Adding them double-counts today.

So today comes from exactly one source:

```
history  = Flex trades strictly before today
today    = Gateway realized P&L   (when connected and reporting)
           else Flex trades dated today
           else 0
headline = sum(history) + today
```

The API reports which one it used as `today_source`, and the page shows it.
Selecting a past year sets it to `none`: Gateway reports P&L realized *now*,
which belongs to the current year and would be contamination in a 2024 total.

## Past years

The **History** page downloads prior calendar years. IBKR serves the four
previous years plus the current one, and the saved Flex Query is re-pointed at
each window at request time via the `fd`/`td` parameters — so **one query
covers every year** and nothing needs configuring in Client Portal.

A year is downloaded once and kept. A closed year can never change, so it is
never re-fetched; only the current year keeps a TTL. Once downloaded, a year
appears in the period selector on Overview and Transactions.

Two details that are easy to get wrong:

- **The current year's window ends today, not Dec 31.** IBKR rejects a window
  ending in the future with `error 1001: Statement could not be generated at
  this time`, which reads exactly like throttling and is not.
- **Failures back off, doubling.** IBKR answers a burst with error 1001 and
  answers persistence with `error 1025: Too many failed attempts` — a lockout
  that further attempts keep alive. A failed year is therefore left alone for
  90s, then 3min, 6min, and so on up to 30 minutes. Pressing Download always
  tries immediately regardless; only the automatic path backs off.

Downloads run **one at a time** — a year costs up to 6 requests against a
token limited to 10/minute, and takes 10–40s. A second request while one is
running is refused with `{"started": false}` and a message saying which year
holds the slot.

## Verifying the numbers

The test that actually matters is a cross-check against IBKR itself:

```bash
uv run python -m ibkr_pnl.sources.flex --dump statement.xml
```

This writes the raw statement and prints the summed `fifoPnlRealized`,
summed `ibCommission`, and the net (`fifoPnlRealized + ibCommission`).
Compare **`sum fifoPnlRealized`** — not the net figure — against Client
Portal's own realized P&L; that's what the dashboard displays throughout.

This was checked against a real account: the whole-statement gross sum
landed within a couple of dollars of Client Portal's own YTD total (the
small gap was fully explained by a handful of trades in the few days
outside the fetched date range), while the net figure was off by hundreds
of dollars. IBKR's own "Realized P&L" is gross — commission is a separate
line item, not netted into it. `RealizedTrade.net_pnl` is still available
in the API if you want a commission-inclusive figure for your own use, but
it is not what the headline or ledger show.

`statement.xml` contains your account number and full trade history — it is
gitignored, but delete it when you are done.

## Tests

```bash
uv run pytest
```

Covers the Flex parser (including expired-token envelopes and the
multiple-levels-of-detail trap) and the merge rule (including the
Gateway-plus-Flex double-count case).

## Layout

```
src/ibkr_pnl/
  config.py           settings from .env
  models.py           shared data model
  sources/flex.py     SendRequest -> poll GetStatement -> parse
  sources/gateway.py  persistent ib_async connection, reqPnL subscription
  cache.py            per-year disk cache + failure backoff
  history.py          per-year downloads, one at a time
  aggregate.py        merges both sources
  server.py           FastAPI: /api/*, plus serving the frontend build
  static/index.html   fallback dashboard, used when frontend/build is absent

frontend/
  src/app.css                     design tokens (shared with ui-reference)
  src/routes/+page.svelte         Overview: headline + cumulative chart
  src/routes/transactions/        the per-trade ledger
  src/routes/history/             download past years
  src/lib/api.ts                  typed client; Decimals arrive as strings
  src/lib/format.ts               money/date formatters, tone helper
  src/lib/stores.ts               data stores + persisted filter preference
  src/lib/components/             PageHeader, SegToggle, ledger, chart, badges
```

## Notes

- **Ledger columns follow your Flex Query.** Price, Amount, Commission and
  Time only appear if the query exports those fields; columns with no data
  anywhere are hidden, and the ledger header names what's missing. Add the
  fields in Client Portal and they come back on their own.
- **Multi-currency:** if trades that actually carry realized P&L span
  currencies, totals add raw values without FX conversion and the page says
  so. A foreign-currency *opening* trade is ignored for this — it contributes
  exactly 0, so it can neither distort a total nor relabel the headline.
- **Rate limits:** the Flex token allows 1 request/second and 10/minute.
  Statements are cached for 15 minutes (`FLEX_CACHE_TTL_SECONDS`); append
  `?refresh=1` to `/api/pnl` to force a fetch.
- **Not in v1:** per-symbol breakdown, period switcher, gross/net commission
  split. The data model already carries the fields for all three.
