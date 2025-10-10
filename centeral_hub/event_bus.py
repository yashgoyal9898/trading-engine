import asyncio
from collections import defaultdict
from collections.abc import Callable
from typing import Any

class EventBus:
    __slots__ = ('_subscribers',)
    
    def __init__(self):
        self._subscribers: dict[str, list[tuple[asyncio.Queue, Callable[[Any], bool] | None]]] = defaultdict(list)

    def subscribe(self, event_type: str, filter_fn: Callable[[Any], bool] | None = None, maxsize: int = 1000) -> asyncio.Queue:
        q = asyncio.Queue(maxsize)
        self._subscribers[event_type].append((q, filter_fn))
        return q

    async def publish(self, event_type: str, data: Any) -> None:
        tasks = [q.put(data) for q, f in self._subscribers.get(event_type, []) if not f or f(data)]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
