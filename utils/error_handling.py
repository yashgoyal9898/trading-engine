import functools
import asyncio
import traceback
from utils.logger import logger

def _handle_exception(func_name, exception):
    """Centralized exception handling."""
    msg = f"[ERROR] Exception in function: {func_name}: | {exception}"
    trace_str = traceback.format_exc()
    # Single clean log call
    logger.error(f"{msg}\n{trace_str}")

def error_handling(func=None, *, re_raise=False):
    """
    Decorator to handle exceptions for sync and async functions.

    Args:
        re_raise (bool): If True, exceptions are re-raised after logging.
    """
    if func is None:
        # Support using decorator with or without parentheses
        return lambda f: error_handling(f, re_raise=re_raise)
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                # handle async result
                return _async_wrapper(result, func.__name__)
            return result
        except Exception as e:
            _handle_exception(func.__name__, e)
            if re_raise:
                raise

    async def _async_wrapper(coro, func_name):
        try:
            return await coro
        except Exception as e:
            _handle_exception(func_name, e)
            if re_raise:
                raise

    return sync_wrapper
