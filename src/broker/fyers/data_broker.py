# src/broker/fyers/data_broker.py
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Callable, Dict, List, Optional

from ...core.data_model import Candle, Tick
from ...core.interfaces.idata_broker import IDataBroker
from ..registry import register_data_broker


@register_data_broker("fyers")
class FyersDataBroker(IDataBroker):
    """
    Adapter: wraps your existing Fyers websocket code behind IDataBroker.
    Replace the _fyers_* stubs with your real Fyers SDK calls.
    """

    def __init__(self, access_token: Optional[str] = None, **kwargs):
        self._access_token = access_token
        self._connected = False
        self._subscriptions: Dict[str, Callable[[Tick], None]] = {}
        # TODO: store your real Fyers SDK client here
        # self._ws = FyersDataSocket(access_token=access_token, ...)

    async def connect(self) -> None:
        # await self._ws.connect()
        self._connected = True

    async def disconnect(self) -> None:
        # await self._ws.close()
        self._connected = False

    async def subscribe(
        self,
        symbols: List[str],
        on_tick: Callable[[Tick], None],
    ) -> None:
        for symbol in symbols:
            self._subscriptions[symbol] = on_tick
        # TODO: self._ws.subscribe(symbols=symbols, data_type="symbolData")

    async def unsubscribe(self, symbols: List[str]) -> None:
        for symbol in symbols:
            self._subscriptions.pop(symbol, None)
        # self._ws.unsubscribe(symbols=symbols)

    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: int,
        from_dt: datetime,
        to_dt: datetime,
    ) -> List[Candle]:
        return []

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _on_tick_raw(self, raw: dict) -> None:
        """
        Fyers websocket message callback — thread-safe tick dispatch.

        BUG FIX: asyncio.coroutine was removed in Python 3.11.
        Use loop.call_soon_threadsafe(callback, tick) instead.
        The callback (SymbolManager._dispatch) is a plain sync function.
        """
        symbol = raw.get("symbol", "")
        if symbol not in self._subscriptions:
            return

        tick = Tick(
            symbol=symbol,
            ltp=float(raw.get("ltp", 0)),
            timestamp=datetime.fromtimestamp(raw.get("timestamp", 0)),
            volume=int(raw.get("vol_traded_today", 0)),
            bid=float(raw.get("bid_price", 0)),
            ask=float(raw.get("ask_price", 0)),
        )
        callback = self._subscriptions[symbol]

        # FIXED: was asyncio.coroutine(lambda: callback(tick))()
        # which crashes on Python 3.11+. callback is sync