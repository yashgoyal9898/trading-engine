# error_handling.py
import asyncio
import functools
import traceback
import time
from typing import Any, Callable, Optional
from utils.logger import logger

class ErrorHandling:
    def __init__(self, retries: int = 0, re_raise: bool = False, backoff: float = 0, exclude: tuple[str, ...] = ()):
        self.retries = retries
        self.re_raise = re_raise
        self.backoff = backoff
        self.exclude = exclude

    def _log_exception(self, func_name: str, exc: Exception, is_async: bool):
        kind = "async" if is_async else "sync"
        logger.error(f"[ERROR] {kind} function '{func_name}' failed: {exc}\n{traceback.format_exc()}")

    def _wrap(self, func: Callable):
        is_async = asyncio.iscoroutinefunction(func)

        async def async_call(*args, **kwargs):
            return await func(*args, **kwargs)

        def sync_call(*args, **kwargs):
            return func(*args, **kwargs)

        call_func = async_call if is_async else sync_call
        sleep_func = asyncio.sleep if is_async else time.sleep

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            attempt = 0
            while attempt <= self.retries:
                try:
                    return await call_func(*args, **kwargs)
                except Exception as e:
                    self._log_exception(func.__name__, e, is_async)
                    attempt += 1
                    if attempt <= self.retries and self.backoff > 0:
                        await sleep_func(self.backoff) if is_async else sleep_func(self.backoff)
                    if attempt > self.retries and self.re_raise:
                        raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            attempt = 0
            while attempt <= self.retries:
                try:
                    return call_func(*args, **kwargs)
                except Exception as e:
                    self._log_exception(func.__name__, e, is_async)
                    attempt += 1
                    if attempt <= self.retries and self.backoff > 0:
                        sleep_func(self.backoff)
                    if attempt > self.retries and self.re_raise:
                        raise

        return async_wrapper if is_async else sync_wrapper

    def __call__(self, obj: Optional[Any] = None):
        # Used as @ErrorHandling() or @ErrorHandling
        if obj is None:
            return self

        # Handle class decoration
        if isinstance(obj, type):
            for name, attr in vars(obj).items():
                if callable(attr) and name not in self.exclude and (not name.startswith("__") or name == "__init__"):
                    setattr(obj, name, self(attr))
            return obj

        # Handle function/coroutine
        return self._wrap(obj)

# ----------------- Usage -----------------
error_handling = ErrorHandling(retries=3, re_raise=True, backoff=5)
