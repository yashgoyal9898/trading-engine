from utils.logger import logger
from utils.error_handling import error_handling
from order_active_state_manager.order_state_manager import TradeManager

@error_handling
class StrategyOneTrailing:
    async def start_trailing_sl(self, fyers_order_placement, strategy_id: str, symbol: str, order_id: str, tick: dict):
        trade_data = await TradeManager.get_trade(strategy_id, order_id)
        if not trade_data or not tick:
            return

        tick_ltp = tick.get("ltp")
        if tick_ltp is None:
            return

        stop_order_id = trade_data.stop_order_id
        for level in trade_data.trailing_levels:
            if any(hist["level"] == level["msg"] for hist in trade_data.trailing_history):
                continue

            if tick_ltp > level["threshold"]:
                try:
                    res = await fyers_order_placement.modify_order(
                        stop_order_id,
                        order_type=4,
                        limit_price=level["new_stop"],
                        stop_price=level["new_stop"],
                        qty=1,
                    )
                except Exception as e:
                    logger.error(f"[{strategy_id}] Trailing SL Error {symbol} | {level['msg']} | {e}")
                    continue

                if res.get('code') == 1102:
                    # Update trade trailing history
                    await TradeManager.update_trailing_history(strategy_id, order_id, {
                        "ltp": tick_ltp,
                        "level": level["msg"],
                        "stop_price": level["new_stop"]
                    })
                    logger.info(f"[{strategy_id}] Trailing SL updated {symbol} | {level['msg']} LTP: {tick_ltp}")
                    break
                else:
                    logger.warning(f"[{strategy_id}] Trailing SL failed {symbol} | {level['msg']} Response: {res}")

strategy_one_trailing = StrategyOneTrailing()
