import asyncio
from typing import Callable, Any, Dict, List, Tuple
from utils.error_handling import error_handling

@error_handling
class EventBus:
    _subscribers: Dict[str, List[Tuple[asyncio.Queue, Callable[[Any], bool]]]] = {}

    @classmethod
    def subscribe(cls, event_type: str, filter_fn: Callable[[Any], bool] = None) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=1000)
        cls._subscribers.setdefault(event_type, []).append((q, filter_fn))
        return q

    @classmethod
    async def publish(cls, event_type: str, data: Any) -> None:
        subscribers = cls._subscribers.get(event_type, [])
        if not subscribers:
            return

        for q, filter_fn in subscribers:
            if filter_fn is None or filter_fn(data):
                if q.full():
                    q.get_nowait()  # Drop oldest
                q.put_nowait(data)