#strategy_one.py file
import asyncio
from strategy_one_logic import check_strategy_condition, start_trailing_sl, save_order_details_to_global
from active_order_state import ORDER_BOOK, order_to_dict
from csv_logging import log_trade 
from logger import logger
from event_bus import event_bus

async def strategy_one(ws_mgr, loop, max_trades):
    candle_queue = event_bus.subscribe("candle")
    tick_queue = event_bus.subscribe("tick")
    trade_close_queue = event_bus.subscribe("trade_close")
    
    trades_done = 0
    stop_event = asyncio.Event()
    active_order_id = None   
    active_strike_price_name = None

    # to skil first candle 
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

    #tick consumer for trailling when order get placed 
    async def tick_consumer():
        nonlocal active_order_id
        stop_task = asyncio.create_task(stop_event.wait())
        try:
            while True:
                tick_task = asyncio.create_task(tick_queue.get())
                done, _ = await asyncio.wait(
                    [tick_task, stop_task],
                    return_when=asyncio.FIRST_COMPLETED
                )

                if stop_task in done:  
                    tick_task.cancel()
                    break

                symbol, tick = tick_task.result()
                if active_order_id:
                    await start_trailing_sl(active_order_id, symbol, tick)
        finally:
            stop_task.cancel()
    
    #order / postion checking consumer-- when trade open and close listen to that 
    async def trade_close_consumer():
        nonlocal active_order_id, trades_done, active_strike_price_name
        while not stop_event.is_set():
            try:
                pos = await asyncio.wait_for(trade_close_queue.get(), timeout=0.5)
                ws_mgr.unsubscribe_symbol(active_strike_price_name)

                #after trade close save the trade details to the csv-----------------
                if ORDER_BOOK.get(active_order_id):
                    await log_trade(trades_done, active_order_id, order_to_dict(ORDER_BOOK.get(active_order_id)))
                    ORDER_BOOK.remove(active_order_id)
                
                logger.info(f"[strategy_one] Trade {trades_done} closed")
                
                active_strike_price_name=None
                active_order_id = None

            except asyncio.TimeoutError:
                pass

    # ---------------- Run ALl Consumers ----------------
    await asyncio.gather(
        candle_consumer(),
        tick_consumer(),
        trade_close_consumer()
    )

    logger.info("[Strategy 1 Ended] ")

    return


