from utils.logger import logger
from utils.error_handling import error_handling
from data_model.data_model import Tick

@error_handling
class TrailingManager:
    async def start_trailing_sl(fyers_order_placement, trailing_levels, stop_order_id, qty, tick: Tick):
        tick_ltp = tick.ltp
        if tick_ltp is None or not trailing_levels or not stop_order_id:
            return

        for level in trailing_levels:
            if level.get("hit"):
                continue

            if tick_ltp > level.get("threshold", float("inf")):
                res = await fyers_order_placement.modify_order(
                    stop_order_id,
                    order_type=4,
                    limit_price=level.get("new_stop"),
                    stop_price=level.get("new_stop"),
                    qty=qty,
                )

                if res.get('code') == 1102:
                    level["hit"] = True  # Mark as triggered
                    logger.info(f"Trailing SL updated | {level.get('msg')} LTP: {tick_ltp}")
                    break  # Only trigger one level per tick
