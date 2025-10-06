import asyncio
from typing import ClassVar, Dict, Optional, List
from utils.error_handling import error_handling
from data_model.data_model import TradeData

@error_handling
class TradeManager:
    # Nested dict: {strategy_id: {order_id: TradeData}}
    _registry: ClassVar[Dict[str, Dict[str, TradeData]]] = {}
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    _trade_counter: ClassVar[Dict[str, int]] = {}  # auto trade numbering per strategy

    @classmethod
    async def add_trade(
        cls, fyers_order_placement, strategy_id: str, main_order_id: str, position_id: str, symbol: str
    ) -> TradeData:
        main, stop, target = await fyers_order_placement.get_main_stop_target_orders(main_order_id)
        if not main:
            raise ValueError(f"No main order found for {main_order_id}")

        # Auto trade number per strategy
        cls._trade_counter[strategy_id] = cls._trade_counter.get(strategy_id, 0) + 1
        trade_no = cls._trade_counter[strategy_id]

        trade_data = TradeData(
            strategy_id=strategy_id,
            trade_no=trade_no,
            order_id=main_order_id,
            stop_order_id=stop.get("id") if stop else None,
            target_order_id=target.get("id") if target else None,
            symbol=symbol,
            position_id=position_id,
            qty=1,
            side="BUY" if target and main.get("tradedPrice") < target.get("limitPrice", float('inf')) else "SELL",
            entry_price=main.get("tradedPrice"),
            initial_stop_price=stop.get("stopPrice") if stop else None,
            target_price=target.get("limitPrice") if target else None,
            initial_sl_points=(stop.get("stopPrice") - main.get("tradedPrice")) if stop else None,
            target_points=(target.get("limitPrice") - main.get("tradedPrice")) if target else None,
            trailing_levels=[
                {"threshold": main.get("tradedPrice") + 3, "new_stop": main.get("tradedPrice") + 0.1, "msg": "breakeven"},
                {"threshold": main.get("tradedPrice") + 10, "new_stop": main.get("tradedPrice") + 0.2, "msg": "1st trail locked profit"},
            ] if main.get("tradedPrice") else [],
            trailing_history=[]
        )

        async with cls._lock:
            cls._registry.setdefault(strategy_id, {})[main_order_id] = trade_data

        return trade_data

    @classmethod
    async def get_trade(cls, strategy_id: str, main_order_id: str) -> Optional[TradeData]:
        async with cls._lock:
            return cls._registry.get(strategy_id, {}).get(main_order_id)

    @classmethod
    async def close_trade(cls, strategy_id: str, main_order_id: str) -> Optional[TradeData]:
        async with cls._lock:
            return cls._registry.get(strategy_id, {}).pop(main_order_id, None)

    @classmethod
    async def list_trades_for_strategy(cls, strategy_id: str) -> List[TradeData]:
        async with cls._lock:
            return list(cls._registry.get(strategy_id, {}).values())

    @classmethod
    async def list_all_trades(cls) -> List[TradeData]:
        async with cls._lock:
            trades = []
            for strategy_trades in cls._registry.values():
                trades.extend(strategy_trades.values())
            return trades

    @classmethod
    async def update_trailing_history(cls, strategy_id: str, order_id: str, new_hist: dict):
        async with cls._lock:
            trade = cls._registry.get(strategy_id, {}).get(order_id)
            if trade:
                trade.trailing_history.append(new_hist)
                return trade
