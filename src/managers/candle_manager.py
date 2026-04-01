from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from ..core.data_model import Candle, Tick
from ..core.interfaces.icandle_builder import ICandleBuilder

logger = logging.getLogger(__name__)

# Key: (symbol, timeframe_in_seconds)
_BuilderKey = Tuple[str, int]


class TimeframeCandleBuilder(ICandleBuilder):
    """
    Ticks se OHLCV candles banata hai.
    timeframe ab SECONDS mein hai (minutes nahi).
    30s candle, 15s candle, 60s candle — sab kuch kaam karta hai.
    """

    def __init__(self, symbol: str, timeframe_seconds: int) -> None:
        self.symbol = symbol
        self.timeframe = timeframe_seconds   # seconds mein
        self._current: Optional[Candle] = None
        self._bar_open_time: Optional[datetime] = None

    def update(self, tick: Tick) -> Optional[Candle]:
        """
        Tick do, agar bar band hua toh closed Candle milega, warna None.
        """
        bar_time = self._get_bar_open(tick.timestamp)

        if self._current is None or bar_time > self._bar_open_time:
            # Naya bar shuru hua
            closed = None
            if self._current is not None:
                self._current.is_closed = True
                closed = self._current

            self._bar_open_time = bar_time
            self._current = Candle(
                symbol=self.symbol,
                timeframe=self.timeframe,
                open=tick.ltp,
                high=tick.ltp,
                low=tick.ltp,
                close=tick.ltp,
                volume=tick.volume,
                timestamp=bar_time,
                is_closed=False,
            )
            return closed
        else:
            # Same bar chal raha hai, update karo
            self._current.high = max(self._current.high, tick.ltp)
            self._current.low = min(self._current.low, tick.ltp)
            self._current.close = tick.ltp
            self._current.volume += tick.volume
            return None

    def get_current(self) -> Optional[Candle]:
        return self._current

    def reset(self) -> None:
        self._current = None
        self._bar_open_time = None

    def _get_bar_open(self, ts: datetime) -> datetime:
        """
        Timestamp ko nearest timeframe boundary pe truncate karta hai.
        Seconds mein kaam karta hai — 30s, 15s, 60s, 1800s sab.

        Example (30s timeframe):
            09:15:07 -> 09:15:00
            09:15:31 -> 09:15:30
        """
        epoch = int(ts.timestamp())
        bar_epoch = (epoch // self.timeframe) * self.timeframe
        return datetime.fromtimestamp(bar_epoch)


class CandleManager:
    """
    Har (symbol, timeframe) ke liye ek builder.
    Multiple strategies ek hi symbol subscribe kar sakti hain — deduplication yahan hota hai.
    """

    def __init__(self) -> None:
        self._builders: Dict[_BuilderKey, TimeframeCandleBuilder] = {}
        self._listeners: Dict[_BuilderKey, List[Callable[[Candle], None]]] = {}

    def register(
        self,
        symbol: str,
        timeframe_seconds: int,
        on_candle: Callable[[Candle], None],
    ) -> None:
        """(symbol, timeframe_seconds) ke liye closed-candle callback register karo."""
        key = (symbol, timeframe_seconds)
        if key not in self._builders:
            self._builders[key] = TimeframeCandleBuilder(symbol, timeframe_seconds)
            self._listeners[key] = []
        self._listeners[key].append(on_candle)
        logger.info(
            "CandleManager: registered %s tf=%ds", symbol, timeframe_seconds
        )

    def on_tick(self, tick: Tick) -> None:
        """SymbolManager har tick pe yeh call karta hai."""
        for (sym, tf), builder in self._builders.items():
            if sym != tick.symbol:
                continue
            closed = builder.update(tick)
            if closed is not None:
                for cb in self._listeners.get((sym, tf), []):
                    try:
                        cb(closed)
                    except Exception:
                        logger.exception(
                            "Candle listener error for %s tf=%ds", sym, tf
                        )

    def get_current(self, symbol: str, timeframe_seconds: int) -> Optional[Candle]:
        b = self._builders.get((symbol, timeframe_seconds))
        return b.get_current() if b else None