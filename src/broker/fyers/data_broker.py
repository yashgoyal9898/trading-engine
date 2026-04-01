from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional

from fyers_apiv3.FyersWebsocket import data_ws

from ...core.data_model import Candle, Tick
from ...core.interfaces.idata_broker import IDataBroker
from ..registry import register_data_broker

logger = logging.getLogger(__name__)


@register_data_broker("fyers")
class FyersDataBroker(IDataBroker):
    """
    Fyers WebSocket data broker.
    WS apne thread mein chalta hai; ticks asyncio loop mein
    call_soon_threadsafe se safely bheje jaate hain.
    """

    def __init__(self, client_id: str, access_token: str, **kwargs):
        # Fyers access token format: "APP_ID:token"
        self._access_token = f"{client_id}:{access_token}"
        self._connected = False
        self._subscriptions: Dict[str, Callable[[Tick], None]] = {}
        self._ws: Optional[data_ws.FyersDataSocket] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws_ready = threading.Event()   # WS connect hone par set hoga

    # ------------------------------------------------------------------ #
    #  Lifecycle
    # ------------------------------------------------------------------ #

    async def connect(self) -> None:
        """asyncio loop reference save karo — tick dispatch ke liye zaroori hai."""
        self._loop = asyncio.get_running_loop()
        self._connected = True
        logger.info("FyersDataBroker: ready (WS lazily starts on first subscribe)")

    async def disconnect(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close_connection()
            except Exception:
                pass
        self._connected = False
        logger.info("FyersDataBroker: disconnected")

    # ------------------------------------------------------------------ #
    #  Subscriptions
    # ------------------------------------------------------------------ #

    async def subscribe(
        self,
        symbols: List[str],
        on_tick: Callable[[Tick], None],
    ) -> None:
        for symbol in symbols:
            self._subscriptions[symbol] = on_tick

        if self._ws is None:
            # Pehli baar: WS banao aur background thread mein chalaao
            self._ws = data_ws.FyersDataSocket(
                access_token=self._access_token,
                log_path="",
                litemode=False,
                write_to_file=False,
                reconnect=True,
                on_connect=self._on_ws_connect,
                on_close=self._on_ws_close,
                on_error=self._on_ws_error,
                on_message=self._on_tick_raw,
            )
            self._ws_thread = threading.Thread(
                target=self._ws.connect,
                daemon=True,
                name="fyers-ws",
            )
            self._ws_thread.start()
            logger.info("FyersDataBroker: WebSocket thread started")

            # WS ke connect hone ka wait karo (max 10 sec)
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: self._ws_ready.wait(timeout=10)
            )
        else:
            # WS already chal raha hai — seedha subscribe karo
            self._ws.subscribe(symbols=symbols, data_type="SymbolUpdate")
            logger.info("FyersDataBroker: subscribed %s", symbols)

    async def unsubscribe(self, symbols: List[str]) -> None:
        for symbol in symbols:
            self._subscriptions.pop(symbol, None)
        if self._ws is not None:
            self._ws.unsubscribe(symbols=symbols)

    async def get_historical_candles(self, symbol, timeframe, from_dt, to_dt):
        return []   # future mein implement karo

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------ #
    #  WebSocket callbacks  (ye sab WS thread mein chalte hain)
    # ------------------------------------------------------------------ #

    def _on_ws_connect(self):
        """WS successfully connect ho gaya — sabhi symbols subscribe karo."""
        logger.info("FyersDataBroker: WebSocket connected")
        symbols = list(self._subscriptions.keys())
        if symbols:
            self._ws.subscribe(symbols=symbols, data_type="SymbolUpdate")
            logger.info("FyersDataBroker: subscribed %s", symbols)
        self._ws_ready.set()

    def _on_ws_close(self, msg):
        logger.warning("FyersDataBroker: WebSocket closed — %s", msg)

    def _on_ws_error(self, msg):
        logger.error("FyersDataBroker: WebSocket error — %s", msg)

    def _on_tick_raw(self, raw: dict) -> None:
        """
        Fyers WS message callback — WS thread mein chalta hai.
        Tick banao aur asyncio loop mein thread-safe tarike se bhejo.
        """
        symbol = raw.get("symbol", "")
        if symbol not in self._subscriptions:
            return

        try:
            tick = Tick(
                symbol=symbol,
                ltp=float(raw.get("ltp", 0.0)),
                timestamp=datetime.fromtimestamp(raw.get("timestamp", 0)),
                volume=int(raw.get("vol_traded_today", 0)),
                bid=float(raw.get("bid_price", 0.0)),
                ask=float(raw.get("ask_price", 0.0)),
            )
        except Exception as exc:
            logger.error("FyersDataBroker: tick parse error — %s | raw=%s", exc, raw)
            return

        callback = self._subscriptions.get(symbol)
        if callback and self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(callback, tick)