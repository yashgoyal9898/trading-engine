import asyncio
from abc import ABC, abstractmethod
from utils.logger import logger
from utils.error_handling import error_handling

@error_handling
class BaseWSManager(ABC):
    def __init__(self):
        self.symbols = {}
        self._running = False
        self.tick_queue = asyncio.Queue()
        self.log = logger

    @abstractmethod
    async def start(self):
        """
        Start data and order brokers, and queue processing.
        Must be implemented by subclass.
        """
        pass

    @abstractmethod
    async def stop(self):
        """
        Stop all brokers and clean up.
        Must be implemented by subclass.
        """
        pass

    @abstractmethod
    def subscribe_symbol(self, symbol, mode="candle", timeframe=30):
        """
        Subscribe to symbol updates.
        Must be implemented by subclass.
        """
        pass

    @abstractmethod
    def unsubscribe_symbol(self, symbol):
        """
        Unsubscribe from symbol updates.
        Must be implemented by subclass.
        """
        pass

