import asyncio
from strategy_one_logic import check_strategy_condition, start_trailing_sl, save_order_details_to_global
from active_order_state import ORDER_BOOK, order_to_dict
from utils.csv_builder import log_trade 
from utils.logger import logger
from event_bus import event_bus


async def strategy_one(ws_mgr, loop, max_trades):
    strategy_id = "STRA_1"
    
    candle_queue = event_bus.subscribe("candle")
    tick_queue = event_bus.subscribe("tick")
    trade_close_queue = event_bus.subscribe("trade_close")
    
    trades_done = 0
    stop_event = asyncio.Event()
    active_order_id = None   
    active_strike_price_name = None
    
    # Skip first candle 
    _ = await candle_queue.get()
    logger.info("first candle")
    
    # ---------------- Consumers ----------------
    async def candle_consumer():
        nonlocal trades_done, active_order_id, active_strike_price_name
        while not stop_event.is_set():
            symbol, candle = await candle_queue.get()
            
            if trades_done < max_trades and active_order_id is None:
                condition_met, active_order_id, active_strike_price_name = await check_strategy_condition(symbol, candle)
                if condition_met:
                    trades_done += 1
                    await save_order_details_to_global(active_order_id, active_strike_price_name)
                    ws_mgr.subscribe_symbol(
                        active_strike_price_name,
                        mode="tick",
                        callback=lambda sym, tick: event_bus.tick_callback(loop, sym, tick)
                    )
                    logger.info(f"Order placed with ID: {active_order_id}")
            
            if active_order_id is None and trades_done >= max_trades:
                logger.info(f"[Max trade Limit Reached | Trade Done: {trades_done} | Max Trade Limit: {max_trades}]")
                stop_event.set()
                break

    async def tick_consumer():
        nonlocal active_order_id
        while not stop_event.is_set():
            processed = False
            while True:
                if tick_queue.empty():
                    break
                symbol, tick = tick_queue.get_nowait()
                processed = True
                if active_order_id:
                    await start_trailing_sl(active_order_id, symbol, tick)
            
            if not processed:
                await asyncio.sleep(0.001)

    async def trade_close_consumer():
        nonlocal active_order_id, trades_done, active_strike_price_name
        while not stop_event.is_set():
            if trade_close_queue.empty():
                await asyncio.sleep(0.01)
                continue
                
            pos = trade_close_queue.get_nowait()
            ws_mgr.unsubscribe_symbol(active_strike_price_name)
            
            # Save trade details to CSV
            if ORDER_BOOK.get(active_order_id):
                await log_trade(trades_done, active_order_id, order_to_dict(ORDER_BOOK.get(active_order_id)))
                ORDER_BOOK.remove(active_order_id)
            
            logger.info(f"[strategy_one] Trade {trades_done} closed")
            
            active_strike_price_name = None
            active_order_id = None

    # ---------------- Run All Consumers ----------------
    await asyncio.gather(
        candle_consumer(),
        tick_consumer(), 
        trade_close_consumer()
    )
    
    logger.info("[Strategy 1 Ended]")
    return
