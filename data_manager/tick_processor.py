from collections import deque
from typing import Dict, Deque, List
from data_model.data_model import Tick

class TickProcessor:
    __slots__ = ('event_bus', 'tick_buffer', 'last_tick_time', 'max_ticks')
    
    def __init__(self, event_bus, max_ticks: int = 1000):
        self.event_bus = event_bus
        self.tick_buffer: Dict[str, Deque[Tick]] = {}
        self.last_tick_time: Dict[str, float] = {}
        self.max_ticks = max_ticks

    async def process_tick(self, tick: Tick, publish: bool = True) -> bool:
        if tick.ltp is None or tick.timestamp is None:
            return False
    
        if tick.symbol not in self.tick_buffer:
            self.tick_buffer[tick.symbol] = deque(maxlen=self.max_ticks)

        self.tick_buffer[tick.symbol].append(tick)
        self.last_tick_time[tick.symbol] = tick.timestamp

        if publish:
            await self.event_bus.publish("tick", tick)

        return True

    def get_ticks_in_range(self, symbol: str, start: float, end: float) -> List[Tick]:
        if buf := self.tick_buffer.get(symbol):
            return [t for t in buf if start <= t.timestamp < end]
        return []

    def cleanup_old_ticks(self, symbol: str, cutoff: float) -> None:
        if buf := self.tick_buffer.get(symbol):
            while buf and buf[0].timestamp < cutoff:
                buf.popleft()

    def cleanup_inactive_symbols(self, current_time: float, ttl: int = 3600) -> int:
        cutoff = current_time - ttl
        inactive = [s for s, ts in self.last_tick_time.items() if ts < cutoff]
        for symbol in inactive:
            self.tick_buffer.pop(symbol, None)
            self.last_tick_time.pop(symbol, None)
        return len(inactive)
