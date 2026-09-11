"""Flex Web Service client: historical realized P&L.

Two-call protocol:

    GET SendRequest?t=<token>&q=<query id>&v=3   -> <ReferenceCode>
    GET GetStatement?t=<token>&q=<ref>&v=3       -> the statement XML

Three things this has to get right, each of which will otherwise produce a
plausible-looking wrong number:

1. Statement generation is asynchronous. GetStatement usually answers the
   first call with "generation in progress" (code 1019) rather than data.
2. Failures arrive as HTTP 200 with a <Status>Fail</Status> envelope, so the
   status code tells us nothing. We check the envelope.
3. A query configured with more than one level of detail emits several <Trade>
   rows for the same fill (EXECUTION, ORDER, CLOSED_LOT). Summing them all
   multiplies realized P&L. We keep exactly one level -- see _select_level.
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import httpx

from ..config import Settings, settings
from ..models import FlexResult, RealizedTrade

BASE_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"
SEND_REQUEST_URL = f"{BASE_URL}/SendRequest"
GET_STATEMENT_URL = f"{BASE_URL}/GetStatement"

# IBKR requires a User-Agent; the service rejects some default client strings.
HEADERS = {"User-Agent": "ibkr-pnl-dashboard/0.1"}

# Statement generation is asynchronous. Rate limit is 1 req/sec, so never
# poll faster than that.
POLL_DELAYS = (2.0, 3.0, 5.0, 8.0, 13.0)

# Preference order when a query reports several levels of detail for the same
# fill. Exactly one is kept.
LEVEL_PREFERENCE = ("EXECUTION", "ORDER", "CLOSED_LOT", "")


class FlexError(Exception):
    """A Flex envelope came back with Status=Fail."""


def _decimal(raw: str | None) -> Decimal:
    if raw is None or raw.strip() == "":
        return Decimal(0)
    try:
        return Decimal(raw.strip())
    except InvalidOperation:
        return Decimal(0)


def _parse_date(raw: str | None) -> date | None:
    """tradeDate format follows the query's own date-format setting."""
    if not raw:
        return None
    text = raw.strip().split(";")[0].strip()  # some fields are "DATE;TIME"
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%m/%d/%Y", "%d-%b-%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _check_envelope(xml_text: str) -> ET.Element:
    """Parse a Flex response and raise on a Fail/Warn envelope."""
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError as exc:
        raise FlexError(f"Flex returned unparseable XML: {exc}") from exc

    status = root.findtext("Status")
    if status and status.strip().lower() != "success":
        code = (root.findtext("ErrorCode") or "").strip()
        message = (root.findtext("ErrorMessage") or "unknown error").strip()
        raise FlexError(f"Flex error {code}: {message}" if code else f"Flex error: {message}")
    return root


def _select_level(trade_nodes: list[ET.Element]) -> list[ET.Element]:
    """Keep a single level of detail so fills are not counted more than once."""
    present = {(node.get("levelOfDetail") or "").strip().upper() for node in trade_nodes}
    # Only one level in play (the normal case) -- nothing to disambiguate.
    if len(present) <= 1:
        return trade_nodes
    for level in LEVEL_PREFERENCE:
        if level in present:
            return [
                node
                for node in trade_nodes
                if (node.get("levelOfDetail") or "").strip().upper() == level
            ]
    return trade_nodes


def parse_statement(xml_text: str) -> FlexResult:
    """Parse a Flex Activity statement into realized trades.

    Rows with no realized P&L (opening trades) are dropped -- they carry
    fifoPnlRealized="0" and would only add noise to the series.
    """
    root = _check_envelope(xml_text)

    account_id = ""
    statement = root.find(".//FlexStatement")
    if statement is not None:
        account_id = (statement.get("accountId") or "").strip()

    nodes = _select_level(root.findall(".//Trade"))

    trades: list[RealizedTrade] = []
    for node in nodes:
        trade_date = _parse_date(node.get("tradeDate") or node.get("dateTime"))
        if trade_date is None:
            continue
        realized = _decimal(node.get("fifoPnlRealized"))
        if realized == 0:
            continue
        trades.append(
            RealizedTrade(
                symbol=(node.get("symbol") or "").strip(),
                trade_date=trade_date,
                realized_pnl=realized,
                commission=_decimal(node.get("ibCommission")),
                currency=(node.get("currency") or "USD").strip() or "USD",
                asset_category=(node.get("assetCategory") or "").strip(),
                quantity=_decimal(node.get("quantity")),
                buy_sell=(node.get("buySell") or "").strip(),
            )
        )

    trades.sort(key=lambda t: t.trade_date)
    return FlexResult(
        ok=True,
        trades=trades,
        fetched_at=datetime.now(),
        account_id=account_id,
    )


async def fetch_statement_xml(config: Settings | None = None) -> str:
    """Run the two-call protocol and return the raw statement XML."""
    config = config or settings
    if not config.flex_configured:
        raise FlexError("FLEX_TOKEN and FLEX_QUERY_ID are not set in .env")

    params = {"t": config.flex_token, "q": config.flex_query_id, "v": "3"}

    async with httpx.AsyncClient(timeout=60.0, headers=HEADERS) as client:
        response = await client.get(SEND_REQUEST_URL, params=params)
        response.raise_for_status()
        envelope = _check_envelope(response.text)

        reference = (envelope.findtext("ReferenceCode") or "").strip()
        if not reference:
            raise FlexError("Flex accepted the request but returned no reference code")

        # IBKR may hand back a per-request URL; prefer it when present.
        statement_url = (envelope.findtext("Url") or GET_STATEMENT_URL).strip()
        statement_params = {"t": config.flex_token, "q": reference, "v": "3"}

        last_error: FlexError | None = None
        for delay in POLL_DELAYS:
            await asyncio.sleep(delay)
            statement = await client.get(statement_url, params=statement_params)
            statement.raise_for_status()
            try:
                _check_envelope(statement.text)
            except FlexError as exc:
                # "Generation in progress" is expected on early polls; any
                # other failure is terminal and should surface immediately.
                if "1019" in str(exc) or "in progress" in str(exc).lower():
                    last_error = exc
                    continue
                raise
            return statement.text

        raise FlexError(
            f"Statement was still generating after {sum(POLL_DELAYS):.0f}s"
            + (f" ({last_error})" if last_error else "")
        )


async def fetch(config: Settings | None = None) -> FlexResult:
    """Fetch and parse, turning failures into a FlexResult we can render."""
    try:
        return parse_statement(await fetch_statement_xml(config))
    except (FlexError, httpx.HTTPError) as exc:
        return FlexResult(ok=False, error=str(exc), fetched_at=datetime.now())


async def _dump() -> None:
    """Write the raw statement to a file so the real field names and the
    sign/commission semantics of fifoPnlRealized can be confirmed against an
    actual account before trusting the parsed numbers.

        uv run python -m ibkr_pnl.sources.flex --dump
    """
    import sys

    destination = sys.argv[2] if len(sys.argv) > 2 else "flex_dump.xml"
    try:
        xml_text = await fetch_statement_xml()
    except (FlexError, httpx.HTTPError) as exc:
        print(f"Flex fetch failed: {exc}")
        raise SystemExit(1)

    with open(destination, "w", encoding="utf-8") as handle:
        handle.write(xml_text)
    print(f"Wrote raw statement to {destination}")

    result = parse_statement(xml_text)
    total = sum((t.realized_pnl for t in result.trades), Decimal(0))
    commissions = sum((t.commission for t in result.trades), Decimal(0))
    currencies = sorted({t.currency for t in result.trades})
    print(f"account:            {result.account_id}")
    print(f"realizing trades:   {len(result.trades)}")
    print(f"currencies:         {', '.join(currencies) or '-'}")
    print(f"sum fifoPnlRealized {total}")
    print(f"sum ibCommission    {commissions}")
    print(f"sum net             {total + commissions}")
    print("\nCompare these against Client Portal's own realized P&L to")
    print("settle whether fifoPnlRealized is already net of commission.")


if __name__ == "__main__":
    import sys

    if "--dump" in sys.argv:
        asyncio.run(_dump())
    else:
        print("usage: python -m ibkr_pnl.sources.flex --dump [path]")
