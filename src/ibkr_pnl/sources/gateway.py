"""IB Gateway source: today's live realized P&L.

reqPnL is a *subscription*, not a request/response. It returns a PnL object
immediately with unset fields and then populates it via pnlEvent roughly once
a second. So we hold one long-lived connection in a background task and keep
the latest values in memory for the API to read. Connecting per request would
churn clientIds and cause reconnect failures.

Gateway needs a daily interactive login, so it is down most of the time. That
is an expected state, not an error: the monitor retries quietly and the rest
of the app falls back to Flex.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime
from decimal import Decimal

from ..config import Settings, settings
from ..models import GatewayState

logger = logging.getLogger(__name__)

# TWS sends this sentinel for "no value"; ib_async usually maps it to nan.
UNSET_DOUBLE = 1.7976931348623157e308

# Gateway is closed most of the time (it needs a daily interactive login), and
# ib_async logs two ERROR lines per attempt. At one attempt every 30s that
# floods the log and buries genuine errors, so we drop those specific lines.
# The reason is still captured in GatewayState and shown in the UI, and we log
# connect/disconnect transitions ourselves.
_EXPECTED_WHEN_GATEWAY_CLOSED = (
    "API connection failed",
    "Make sure API port on TWS/IBG is open",
)


class _SuppressExpectedDisconnects(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(text in message for text in _EXPECTED_WHEN_GATEWAY_CLOSED)


logging.getLogger("ib_async.client").addFilter(_SuppressExpectedDisconnects())


def _clean(value: float | None) -> Decimal | None:
    """Convert a TWS double to Decimal, treating unset sentinels as None."""
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or abs(value) >= UNSET_DOUBLE):
        return None
    return Decimal(str(value))


class GatewayMonitor:
    """Keeps one IB Gateway connection alive and tracks the latest P&L."""

    def __init__(self, config: Settings | None = None) -> None:
        self._config = config or settings
        self._state = GatewayState()
        self._task: asyncio.Task | None = None
        self._ib = None  # ib_async.IB, imported lazily

    @property
    def state(self) -> GatewayState:
        return self._state

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="ib-gateway-monitor")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._disconnect()

    async def _disconnect(self) -> None:
        if self._ib is not None and self._ib.isConnected():
            try:
                self._ib.disconnect()
            except Exception:  # noqa: BLE001 - teardown must never raise
                logger.debug("error while disconnecting from IB Gateway", exc_info=True)
        self._ib = None

    def _on_pnl(self, pnl) -> None:
        """pnlEvent handler -- fires about once per second while connected."""
        self._state = GatewayState(
            connected=True,
            realized_pnl=_clean(getattr(pnl, "realizedPnL", None)),
            unrealized_pnl=_clean(getattr(pnl, "unrealizedPnL", None)),
            daily_pnl=_clean(getattr(pnl, "dailyPnL", None)),
            account=getattr(pnl, "account", "") or self._state.account,
            updated_at=datetime.now(),
        )

    async def _connect_once(self) -> None:
        from ib_async import IB

        ib = IB()
        self._ib = ib
        await ib.connectAsync(
            self._config.ib_host,
            self._config.ib_port,
            clientId=self._config.ib_client_id,
            timeout=10,
            readonly=True,
        )

        account = self._config.ib_account.strip()
        if not account:
            managed = ib.managedAccounts()
            if not managed:
                raise RuntimeError("IB Gateway reported no accounts")
            account = managed[0]

        ib.pnlEvent += self._on_pnl
        ib.reqPnL(account)

        self._state = GatewayState(
            connected=True,
            account=account,
            updated_at=datetime.now(),
        )
        logger.info("connected to IB Gateway (account %s)", account)

        # Hold the connection open; _on_pnl keeps state current.
        while ib.isConnected():
            await asyncio.sleep(1)

        raise ConnectionError("IB Gateway connection closed")

    async def _run(self) -> None:
        last_reason = ""
        while True:
            was_connected = self._state.connected
            try:
                await self._connect_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - any failure means "retry later"
                reason = str(exc) or exc.__class__.__name__
                # Log the transition only. Gateway being closed is the normal
                # case; repeating it every 30s would be noise.
                if was_connected:
                    logger.info("IB Gateway disconnected: %s", reason)
                elif reason != last_reason:
                    logger.info("IB Gateway unavailable: %s", reason)
                last_reason = reason
                self._state = GatewayState(
                    connected=False,
                    account=self._state.account,
                    error=reason,
                )
            finally:
                await self._disconnect()

            await asyncio.sleep(self._config.ib_reconnect_seconds)


monitor = GatewayMonitor()
