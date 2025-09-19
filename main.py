#main.py file
import asyncio
from websocket_manager.position_manager.fyers_position_webscoket import FyersOrderManager
from websocket_manager.data_manager.fyers_data_websocket import FyersWSManager
from strategy.strategy_one import strategy_one  
from utils.logger import logger
from centeral_hub.event_bus import event_bus
from utils.error_handling import error_handling
import os

@error_handling
async def main():
    logger.info("ALGO STARTED")
    
    loop = asyncio.get_running_loop()

    #data and postion websocket
    ws_mgr = FyersWSManager.get_instance()
    await ws_mgr.start()
    order_mgr = FyersOrderManager.get_instance()
    await order_mgr.connect()

    #event bus started 
    event_bus.start(ws_mgr, order_mgr, loop)
    
    logger.info("ALL RESOURCES SUBSCIBED")

    #strategies
    await strategy_one("strategy_one", ws_mgr, loop, max_trades=1)

    #stop websocket 
    await ws_mgr.stop()
    await order_mgr.stop()

    logger.info("[Main] Program terminated....................")
    
    os._exit(0)

if __name__ == "__main__":
    asyncio.run(main())
