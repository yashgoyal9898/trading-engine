# test/test_phase1.py
"""
Run: pytest test/test_phase1.py -v
All should pass before moving to Phase 2.
"""
from datetime import datetime

import pytest

from src.core.enums import Mode, OrderSide, OrderType, TradeStatus
from src.core.data_model import Candle, Signal, Tick, TradeData
from src.infrastructure.config_loader import load_config


# --- enums ---

def test_enums_values():
    assert OrderSide.BUY.value == "BUY"
    assert Mode.CANDLE.value == "candle"
    assert TradeStatus.OPEN.value == "OPEN"


# --- data model ---

def test_tick_creation():
    t = Tick(symbol="NSE:NIFTY50-INDEX", ltp=22500.0, timestamp=datetime.now())
    assert t.symbol == "NSE:NIFTY50-INDEX"
    assert t.volume == 0


def test_candle_valid():
    c = Candle(
        symbol="NSE:NIFTY50-INDEX",
        timeframe=1800,
        open=22000.0, high=22500.0, low=21800.0, close=22300.0,
        volume=100000,
        timestamp=datetime(2024, 1, 1, 9, 15),
    )
    assert c.is_closed is False


def test_candle_invalid_high():
    with pytest.raises(ValueError):
        Candle(
            symbol="TEST", timeframe=1800,
            open=100.0, high=90.0,   # high < open -> invalid
            low=80.0, close=95.0,
            volume=0, timestamp=datetime.now(),
        )


def test_signal_creation():
    s = Signal(
        symbol="NSE:NIFTY50-INDEX",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=50,
    )
    assert s.price == 0.0


def test_trade_pnl_buy():
    t = TradeData(
        trade_id="T001", strategy_id="STRAT_ONE",
        symbol="NSE:NIFTY50-INDEX", side=OrderSide.BUY,
        quantity=50, entry_price=22000.0, exit_price=22300.0,
    )
    pnl = t.compute_pnl()
    assert pnl == 15000.0  # 300 * 50


def test_trade_pnl_sell():
    t = TradeData(
        trade_id="T002", strategy_id="STRAT_ONE",
        symbol="NSE:NIFTY50-INDEX", side=OrderSide.SELL,
        quantity=50, entry_price=22000.0, exit_price=21700.0,
    )
    pnl = t.compute_pnl()
    assert pnl == 15000.0  # (22000 - 21700) * 50


# --- config loader ---

def test_load_config(tmp_path):
    yml = tmp_path / "settings.yml"
    yml.write_text("""
brokers:
  data: fyers
  order: fyers

strategies:
  - id: STRATEGY_ONE
    module: strategy_one
    enabled: true
    max_trades: 1
    symbols:
      - name: NSE:NIFTY50-INDEX
        mode: candle
        timeframe: 30
""")
    cfg = load_config(str(yml))
    assert cfg.brokers.data == "fyers"
    assert len(cfg.strategies) == 1
    strat = cfg.strategies[0]
    assert strat.id == "STRATEGY_ONE"
    # BUG FIX: timeframe: 30 (minutes) → _parse_timeframe_seconds → 1800 seconds
    assert strat.symbols[0].timeframe == 1800


def test_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("nonexistent.yml")