import asyncio
from utils.logger import logger
from utils.error_handling import error_handling
from .tick_processor import TickProcessor
from .candle_builder import CandleBuilder
from websocket_manager.fyers_broker.broker_interface import BrokerInterface
from .base_interface import BaseWSManager

@error_handling
class FyersWSManager(BaseWSManager):
    def __init__(
        self, 
        data_broker: BrokerInterface,
        order_broker: BrokerInterface = None,
        tick_processor=None, 
        candle_builder=None
    ):
        self.data_broker = data_broker
        self.order_broker = order_broker
        self.symbols = {}
        self._running = False
        self.tick_processor = tick_processor or TickProcessor()
        self.candle_builder = candle_builder or CandleBuilder(self.tick_processor)
        self.tick_queue = asyncio.Queue()
        self.log = logger

    async def start(self):
        if self._running:
            return
        self._running = True
        
        # Start data broker connection
        await self.data_broker.connect(self.tick_queue)
        await self.order_broker.connect(self.tick_queue)
        
        # Wait until data broker is connected
        while not self.data_broker.is_connected() and not self.order_broker.is_connected():
            await asyncio.sleep(0.1)

        # Start queue processor
        asyncio.create_task(self._process_broker_msg_queue())
    
    async def stop(self):
        if not self._running:
            return
        self._running = False
        
        await self.data_broker.disconnect()
        await self.order_broker.disconnect()
        
        self.log.info("[Manager] Stopped all websockets")
    
    def subscribe_symbol(self, symbol, mode="candle", timeframe=30):
        if symbol not in self.symbols:
            self.symbols[symbol] = {"mode": mode, "timeframe": timeframe}
            if self._running and self.data_broker.is_connected():
                self.data_broker.subscribe([symbol])
    
    def unsubscribe_symbol(self, symbol):
        if symbol in self.symbols:
            if self._running and self.data_broker.is_connected():
                self.data_broker.unsubscribe([symbol])
            del self.symbols[symbol]
    
    async def _process_broker_msg_queue(self):
        while self._running:
            message = await self.tick_queue.get()
            if not message:
                continue
            symbol = message.get("symbol")
            if not symbol or symbol not in self.symbols:
                continue
            cfg = self.symbols[symbol]
            
            if cfg["mode"] == "tick":
                await self.tick_processor.process_tick(symbol, message, publish=True)
            else:
                if await self.tick_processor.process_tick(symbol, message, publish=False):
                    await self.candle_builder.process_candle_tick(
                        symbol, message, cfg["timeframe"]
                    )
    
