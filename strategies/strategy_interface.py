# strategies/base_strategy.py
import abc
from typing import Optional
from data_model.data_model import TradeData

class BaseStrategy(abc.ABC):
    def __init__(self, event_bus, strategy_id, ws_mgr, loop, max_trades: int = 1):
        self.event_bus = event_bus
        self.strategy_id = strategy_id
        self.ws_mgr = ws_mgr
        self.loop = loop
        self.max_trades = max_trades
        self.active_order_id: Optional[str] = None
        self.active_trade_data_obj: Optional[TradeData] = None
        self.trades_done: int = 0

    # ------------------ Max Trade Check ------------------
    @abc.abstractmethod
    def is_max_trade_reached(self) -> bool:
        """Check if the maximum number of trades has been reached."""

    # ------------------ Position Management ------------------
    @abc.abstractmethod
    async def manage_position(self, pos: dict):
        """Handle position updates from broker."""

    # ------------------ Consumers ------------------
    @abc.abstractmethod
    async def candle_consumer(self):
        """Consume candle events."""

    @abc.abstractmethod
    async def tick_consumer(self):
        """Consume tick events."""

    @abc.abstractmethod
    async def broker_postion_consumer(self):
        """Consume broker position events."""

    # ------------------ Run ------------------
    @abc.abstractmethod
    async def run(self):
        """Run the strategy and manage tasks."""
