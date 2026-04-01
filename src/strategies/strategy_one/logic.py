from __future__ import annotations

from typing import List, Optional

from ...core.data_model import Candle, Signal, TradeData
from ...core.enums import OrderSide, OrderType
from .config import StrategyOneParams


def compute_entry(
    candle: Candle,
    history: List[Candle],
    params: StrategyOneParams,
    order_symbol: str,            # Yeh symbol pe order jayega (signal_symbol se alag ho sakta hai)
) -> Optional[Signal]:
    """
    Pure function — koi side effect nahi, koi I/O nahi.

    Logic:
        candle_range = high - low
        body = abs(close - open)
        body_pct = body / range * 100

        Agar body_pct > threshold:
            - Bullish (close > open) → BUY order_symbol
            - Bearish (close < open) → SELL order_symbol
    """
    candle_range = candle.high - candle.low

    # Doji ya flat candle — skip karo
    if candle_range < 0.01:
        return None

    body = abs(candle.close - candle.open)
    body_pct = (body / candle_range) * 100.0

    if body_pct <= params.body_pct_threshold:
        return None   # Body chhoti hai, signal nahi

    # Bullish = green candle, Bearish = red candle
    side = OrderSide.BUY if candle.close > candle.open else OrderSide.SELL

    return Signal(
        symbol=order_symbol,        # Signal wale symbol pe nahi, ORDER wale pe
        side=side,
        order_type=OrderType.MARKET,
        quantity=1,
        tag=f"BODY_{body_pct:.1f}pct_{'BULL' if side == OrderSide.BUY else 'BEAR'}",
    )


def compute_exit(
    candle: Candle,
    trade: TradeData,
    params: StrategyOneParams,
) -> Optional[Signal]:
    """SL ya target hit hone pe exit."""
    if trade.sl > 0 and candle.low <= trade.sl:
        return Signal(
            symbol=trade.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=trade.quantity,
            price=trade.sl,
            tag="SL_HIT",
        )
    if trade.target > 0 and candle.high >= trade.target:
        return Signal(
            symbol=trade.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=trade.quantity,
            price=trade.target,
            tag="TARGET_HIT",
        )
    return None