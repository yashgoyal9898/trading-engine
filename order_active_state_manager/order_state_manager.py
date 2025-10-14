import asyncio
from typing import Dict
from utils.error_handling import error_handling
from data_model.data_model import TradeData

@error_handling
class TradeManager:
    def __init__(self, event_bus, strategy_id: str):
        self.event_bus = event_bus
        self.strategy_id = strategy_id
        self._trades: Dict[str, TradeData] = {}  # in-memory trades for this strategy
        self._lock = asyncio.Lock()

    async def add_trade(self, trade_no, main_order_id: str, main, stop, target) -> TradeData:
        trade_data = TradeData(
            trade_no=trade_no,
            strategy_id=self.strategy_id,
            order_id=main_order_id,
            stop_order_id=stop.get("id") if stop else None,
            target_order_id=target.get("id") if target else None,
            symbol=main.get("symbol"),
            position_id=None,
            qty=main.get("qty"),
            side="BUY" if target and main.get("tradedPrice") < target.get("limitPrice", float('inf')) else "SELL",
            entry_price=main.get("tradedPrice"),
            initial_stop_price=stop.get("stopPrice") if stop else None,
            target_price=target.get("limitPrice") if target else None,
            initial_sl_points=(stop.get("stopPrice") - main.get("tradedPrice")) if stop else None,
            target_points=(target.get("limitPrice") - main.get("tradedPrice")) if target else None,
            trailing_levels=[
                {"threshold": main.get("tradedPrice") + 3, "new_stop": main.get("tradedPrice") + 0.1, "msg": "breakeven", "hit": False},
                {"threshold": main.get("tradedPrice") + 10, "new_stop": main.get("tradedPrice") + 0.2, "msg": "1st trail locked profit", "hit": False},
            ] if main.get("tradedPrice") else [],
        )

        async with self._lock:
            self._trades[main_order_id] = trade_data

        return trade_data

    async def close_trade(self, main_order_id: str) -> None:
        async with self._lock:
            trade = self._trades.pop(main_order_id, None)
            if trade:
                await self.event_bus.publish("trade_close", trade)
