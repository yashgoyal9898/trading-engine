import asyncio
from typing import Callable, Any, Dict, List, Tuple
from utils.error_handling import error_handling

@error_handling
class EventBus:
    # shared across all subscribers globally
    _subscribers: Dict[str, List[Tuple[asyncio.Queue, Callable[[Any], bool]]]] = {}

    @classmethod
    def subscribe(cls, event_type: str, filter_fn: Callable[[Any], bool] = None) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=1000)
        cls._subscribers.setdefault(event_type, []).append((q, filter_fn))
        return q

    @classmethod
    async def publish(cls, event_type: str, data: Any) -> None:
        for q, filter_fn in cls._subscribers.get(event_type, []):
            if filter_fn is None or filter_fn(data):
                try:
                    q.put_nowait(data)
                except asyncio.QueueFull:
                    _ = await q.get()
                    await q.put(data)
