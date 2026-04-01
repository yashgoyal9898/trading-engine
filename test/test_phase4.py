# test/test_phase4.py
"""
Run: pytest test/test_phase4.py -v

Strategy One logic:
  candle_range = high - low
  body        = abs(close - open)
  body_pct    = body / range * 100
  Signal if body_pct > body_pct_threshold:
    close > open → BUY  order_symbol
    close < open → SELL order_symbol
"""
from datetime import datetime

import pytest

from src.core.data_model import Candle, TradeData
from src.core.enums import OrderSide, TradeStatus
from src.strategies.strategy_one.config import StrategyOneParams
from src.strategies.strategy_one.logic import compute_entry, compute_exit
from src.strategies.strategy_one.handler import Handler
from src.infrastructure.config_loader import StrategyConfig, SymbolConfig

TF = 1800  # 30 minutes in seconds


def make_candle(open_, high, low, close, symbol="NSE:NIFTY50-INDEX", tf=TF):
    return Candle(
        symbol=symbol, timeframe=tf,
        open=open_, high=high, low=low, close=close,
        volume=1000,
        timestamp=datetime(2024, 1, 1, 9, 15),
        is_closed=True,
    )


# ------------------------------------------------------------------ #
#  Pure logic tests — compute_entry (Bug Fix: added order_symbol arg)
# ------------------------------------------------------------------ #

def test_entry_flat_candle_skipped():
    """Doji/flat candle (range < 0.01) → None."""
    params = StrategyOneParams(body_pct_threshold=10.0)
    # range = 0.005 < 0.01 → skip
    candle = make_candle(22000.000, 22000.005, 22000.000, 22000.003)
    result = compute_entry(candle, [], params, "NSE:IDEA-EQ")
    assert result is None


def test_entry_small_body_no_signal():
    """body_pct <= threshold → no signal."""
    params = StrategyOneParams(body_pct_threshold=50.0)
    # body=50, range=200, body_pct=25% < 50%
    candle = make_candle(22000, 22100, 21900, 22050)
    result = compute_entry(candle, [], params, "NSE:IDEA-EQ")
    assert result is None


def test_entry_bullish_signal():
    """Large bullish body → BUY on order_symbol."""
    params = StrategyOneParams(body_pct_threshold=10.0)
    # body=90, range=110, body_pct=81.8% > 10%, close>open → BUY
    candle = make_candle(22000, 22100, 21990, 22090)
    result = compute_entry(candle, [], params, "NSE:IDEA-EQ")
    assert result is not None
    assert result.side == OrderSide.BUY
    assert result.symbol == "NSE:IDEA-EQ"   # order on IDEA, not NIFTY


def test_entry_bearish_signal():
    """Large bearish body → SELL on order_symbol."""
    params = StrategyOneParams(body_pct_threshold=10.0)
    # body=90, range=120, body_pct=75% > 10%, close<open → SELL
    candle = make_candle(22100, 22110, 21990, 22010)
    result = compute_entry(candle, [], params, "NSE:IDEA-EQ")
    assert result is not None
    assert result.side == OrderSide.SELL
    assert result.symbol == "NSE:IDEA-EQ"


def test_entry_uses_order_symbol_not_signal_symbol():
    """Signal from NIFTY → order on IDEA-EQ."""
    params = StrategyOneParams(body_pct_threshold=10.0)
    candle = make_candle(22000, 22100, 21990, 22090, symbol="NSE:NIFTY50-INDEX")
    result = compute_entry(candle, [], params, "NSE:IDEA-EQ")
    assert result is not None
    assert result.symbol == "NSE:IDEA-EQ"


# ------------------------------------------------------------------ #
#  compute_exit
# ------------------------------------------------------------------ #

def test_exit_sl_hit():
    params = StrategyOneParams()
    trade = TradeData(
        trade_id="T1", strategy_id="S1",
        symbol="NSE:IDEA-EQ", side=OrderSide.BUY,
        quantity=50, entry_price=22000.0, sl=21900.0,
    )
    candle = make_candle(21950, 21980, 21880, 21900)  # low=21880 < sl=21900
    result = compute_exit(candle, trade, params)
    assert result is not None
    assert result.tag == "SL_HIT"


def test_exit_target_hit():
    params = StrategyOneParams()
    trade = TradeData(
        trade_id="T1", strategy_id="S1",
        symbol="NSE:IDEA-EQ", side=OrderSide.BUY,
        quantity=50, entry_price=22000.0, sl=21900.0, target=22300.0,
    )
    candle = make_candle(22100, 22350, 22080, 22200)  # high=22350 > target=22300
    result = compute_exit(candle, trade, params)
    assert result is not None
    assert result.tag == "TARGET_HIT"


def test_exit_no_sl_target_returns_none():
    """Default sl=0.0 and target=0.0 → no exit."""
    params = StrategyOneParams()
    trade = TradeData(
        trade_id="T1", strategy_id="S1",
        symbol="NSE:IDEA-EQ", side=OrderSide.BUY,
        quantity=50, entry_price=22000.0,
        # sl=0.0, target=0.0 by default
    )
    candle = make_candle(21500, 21600, 21400, 21550)
    result = compute_exit(candle, trade, params)
    assert result is None


# ------------------------------------------------------------------ #
#  Handler integration
# ------------------------------------------------------------------ #

def make_strategy_config():
    return StrategyConfig(
        id="STRATEGY_ONE",
        module="strategy_one",
        enabled=True,
        max_trades=1,
        symbols=[SymbolConfig(
            name="NSE:NIFTY50-INDEX",
            mode="candle",
            timeframe=TF,
            order_symbol="NSE:IDEA-EQ",
        )],
        params={"body_pct_threshold": 10.0},
    )


class _MockBroker:
    is_connected = True
    async def place_order(self, sig): return "ORD_001"
    async def cancel_order(self, oid): return True
    async def get_order_status(self, oid): return {}
    async def get_positions(self): return []
    async def connect(self): pass
    async def disconnect(self): pass


@pytest.mark.asyncio
async def test_handler_on_candle_entry():
    from src.managers.trade_state_manager import TradeStateManager
    from src.managers.order_placement_manager import OrderPlacementManager
    from src.managers.candle_manager import CandleManager

    tsm = TradeStateManager()
    opm = OrderPlacementManager(_MockBroker(), tsm)
    cm  = CandleManager()

    handler = Handler(make_strategy_config())
    handler.wire(opm, tsm, cm)
    await handler.start()

    # body=90, range=110, body_pct=81.8% > 10% → BUY signal
    candle = make_candle(22000, 22100, 21990, 22090)
    await handler.on_candle(candle)

    assert tsm.open_trade_count("STRATEGY_ONE") == 1


@pytest.mark.asyncio
async def test_handler_max_trades_respected():
    from src.managers.trade_state_manager import TradeStateManager
    from src.managers.order_placement_manager import OrderPlacementManager
    from src.managers.candle_manager import CandleManager

    tsm = TradeStateManager()
    opm = OrderPlacementManager(_MockBroker(), tsm)
    cm  = CandleManager()

    handler = Handler(make_strategy_config())  # max_trades=1
    handler.wire(opm, tsm, cm)
    await handler.start()

    candle = make_candle(22000, 22100, 21990, 22090)
    await handler.on_candle(candle)
    await handler.on_candle(candle)  # second call — should NOT open another trade

    assert tsm.open_trade_count("STRATEGY_ONE") == 1