# IBKR Realized P&L Dashboard

A local dashboard showing the latest realized P&L for your IBKR account: a
headline total and a cumulative-P&L-over-time chart.

It reads two sources and works with either one alone:

| Source | Provides | Needs |
|---|---|---|
| **Flex Web Service** | Historical realized P&L per trade | A token + query ID. No install. |
| **IB Gateway** | Today's live realized P&L (`reqPnL`) | IB Gateway running and logged in. |

IB Gateway needs an interactive login each day, so it is down much of the
time. That is expected: the dashboard falls back to Flex and shows a
"Gateway disconnected" badge rather than failing.

## Quick start

```bash
cp .env.example .env      # then fill in the values from the setup below
uv run uvicorn ibkr_pnl.server:app --port 8000
```

Open <http://localhost:8000>.

## Setup

### 1. Flex Query

Client Portal → **Performance & Reports** → **Flex Queries** → new
**Activity Flex Query**:

- **Section:** Trades. Fields: `symbol`, `tradeDate`, `fifoPnlRealized`,
  `ibCommission`, `currency`, `assetCategory`, `quantity`, `buySell`.
- **Date range:** Year to Date
- **Format:** XML

Save it and note the **Query ID** → `FLEX_QUERY_ID`.

> Set **one** level of detail on the Trades section. If a query emits both
> Execution and Order (or Closed Lot) rows, each fill appears more than once.
> The parser keeps a single level to defend against this, but configuring it
> correctly is better.

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

## Verifying the numbers

The test that actually matters is a cross-check against IBKR itself:

```bash
uv run python -m ibkr_pnl.sources.flex --dump statement.xml
```

This writes the raw statement and prints the summed `fifoPnlRealized`,
summed `ibCommission`, and the net. Compare the headline against Client
Portal's own realized P&L.

**If they disagree,** the likely cause is commission treatment:
`fifoPnlRealized` is normally already net of the closing trade's commission,
but this is worth confirming against your own data rather than assuming. The
parser keeps `ibCommission` on every trade, so switching to
`realized_pnl + commission` in [aggregate.py](src/ibkr_pnl/aggregate.py) is a
one-line change if your account shows otherwise.

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
  cache.py            disk cache (the Flex token is rate limited)
  aggregate.py        merges both sources
  server.py           FastAPI: /api/pnl, /api/health
  static/index.html   the dashboard
```

## Notes

- **Multi-currency:** if the statement spans currencies, totals add raw
  values without FX conversion and the page says so. Single-currency
  accounts are unaffected.
- **Rate limits:** the Flex token allows 1 request/second and 10/minute.
  Statements are cached for 15 minutes (`FLEX_CACHE_TTL_SECONDS`); append
  `?refresh=1` to `/api/pnl` to force a fetch.
- **Not in v1:** per-symbol breakdown, period switcher, gross/net commission
  split. The data model already carries the fields for all three.
