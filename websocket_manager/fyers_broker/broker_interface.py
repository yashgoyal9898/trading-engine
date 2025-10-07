from abc import ABC, abstractmethod
import asyncio

class BrokerInterface(ABC):
    
    @abstractmethod
    async def connect(self, queue: asyncio.Queue):
        """Connect broker and push messages into the provided queue"""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Disconnect broker"""
        pass
    
    @abstractmethod
    def subscribe(self, symbols: list):
        """Subscribe to symbols"""
        pass
    
    @abstractmethod
    def unsubscribe(self, symbols: list):
        """Unsubscribe from symbols"""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Return connection status"""
        pass
