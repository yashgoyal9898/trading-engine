from order_management import place_order, modify_order, get_main_stop_target_orders
from datetime import datetime, timedelta
import calendar
from utils.logger import logger
from active_order_state import ActiveOrderState, ORDER_BOOK
import math

async def check_strategy_condition(symbol, candle):
    o, h, l, c = candle["open"], candle["high"], candle["low"], candle["close"]

    ce_symbol, pe_symbol = await find_strike_price_atm(candle["close"])
    
    logger.info( f"[Candle] {candle['time']} | {symbol} | " f"open: {o}, high: {h}, low: {l}, close: {c}" )

    if h == l:
        return False, None, None

    body_percentage = abs(c - o) / (h - l) * 100

    if body_percentage < 5:
        return False, None, None

    if c != o:  # skip doji-like candles where open == close
        side = 1 if c > o else 1   # 1 = BUY, -1 = SELL
        stop_loss, take_profit = 0.5, 2.0
        strike_price_name = ce_symbol if c > o else pe_symbol 

        order_response = await place_order(symbol="NSE:IDEA-EQ", qty=1, order_type=2, side=side, stop_loss=stop_loss, take_profit=take_profit)
        
        order_id = order_response.get("id")

        return True, order_id, strike_price_name

    return False, None, None


async def save_order_details_to_global(order_id: str, strike_price_name: str) -> ActiveOrderState:
    
    main, stop, target = await get_main_stop_target_orders(order_id)

    if not main:
        raise ValueError(f"No main order found for {order_id}")

    stop_order_id = stop.get("id") if stop else None
    target_order_id = target.get("id") if target else None

    entry_price = main.get("tradedPrice")
    initial_stop_price = stop.get("stopPrice") if stop else None
    target_price = target.get("limitPrice") if target else None

    # Precompute trailing levels
    trailing_levels = []
    if entry_price:
        trailing_levels = [
            {"threshold": entry_price + 3, "new_stop": entry_price + 0.1, "msg": "breakeven"},
            {"threshold": entry_price + 10, "new_stop": entry_price + 0.2, "msg": "1st trail locked profit"},
        ]

    order = ActiveOrderState(
        main_order_id=order_id,
        stop_order_id=stop_order_id,
        target_order_id=target_order_id,
        symbol=strike_price_name,
        entry_price=entry_price,
        initial_stop_price=initial_stop_price,
        target_price=target_price,
        trailing_levels=trailing_levels,
    )

    ORDER_BOOK.add(order_id, order)
    return order



async def start_trailing_sl(active_order_id: str, symbol: str, tick: dict):
    order_obj = ORDER_BOOK.get(active_order_id)
    if not order_obj:
        return

    tick_ltp = tick.get("ltp")
    if tick_ltp is None:
        return

    stop_order_id = order_obj.stop_order_id

    for level in order_obj.trailing_levels:
    # Skip if already applied successfully
        if any(hist["level"] == level["msg"] for hist in order_obj.trailing_history):
            continue

        if tick_ltp > level["threshold"]:
            try:
                res = await modify_order(
                    stop_order_id,
                    order_type=4,
                    limit_price=level["new_stop"],
                    stop_price=level["new_stop"],
                    qty=1,
                )
            except Exception as e:
                logger.error(f"[Trailing SL Error] {symbol} | Level: {level['msg']} | {e}")
                # Do NOT break; will retry on next tick
                continue

            if res.get('code') == 1102:
                # Record successful update
                order_obj.trailing_history.append({
                    "ltp": tick_ltp,
                    "level": level["msg"],
                    "stop_price": level["new_stop"]
                })

                logger.info(
                    f"[Trailing SL Update] {symbol} | Time: {tick.get('exch_feed_time')} "
                    f"New Stop: {level['new_stop']} ({level['msg']}) LTP: {tick_ltp}"
                )

                # Only stop processing after success
                break
            else:
                # Modification failed, log it and retry on next tick
                logger.warning(f"[Trailing SL Failed] {symbol} | Level: {level['msg']} | Response: {res}")
                continue


MONTH_ABBR = ['', 'JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']

async def next_tuesday_expiry(base_date: str = None) -> tuple[str, bool]:
    # Use passed date or today
    today = datetime.today()
    # today = datetime.strptime("2025-10-12", "%Y-%m-%d") 

    # Find next Tuesday
    days_ahead = (1 - today.weekday()) % 7  # Tuesday = 1 (Mon=0)
    days_ahead = days_ahead or 7            # if today is Tue, take next week
    tuesday = today + timedelta(days=days_ahead)

    # Last Tuesday of the month
    last_day = calendar.monthrange(tuesday.year, tuesday.month)[1]
    last_tuesday = last_day - ((datetime(tuesday.year, tuesday.month, last_day).weekday() - 1) % 7)

    if tuesday.day == last_tuesday:
        # Monthly expiry → YY + MON_ABBR
        expiry_str = f"{tuesday.year % 100}{MONTH_ABBR[tuesday.month]}"
        return expiry_str, True
    else:
        # Weekly expiry → YYMMDD
        expiry_str = f"{tuesday.year % 100}{tuesday.month}{tuesday.day:02d}"
        return expiry_str, False


async def find_strike_price_atm(spot_price: float):
    ce_strike = math.floor(spot_price / 50) * 50
    pe_strike = math.ceil(spot_price / 50) * 50

    expiry_str, _ = await next_tuesday_expiry()

    ce_symbol = f"NSE:NIFTY{expiry_str}{ce_strike}CE"
    pe_symbol = f"NSE:NIFTY{expiry_str}{pe_strike}PE"

    return ce_symbol, pe_symbol

