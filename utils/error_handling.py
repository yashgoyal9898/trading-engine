#error_handling.py
import functools
import traceback
import inspect
from typing import Any, Callable, Optional, Union, Type
from utils.logger import logger

def _handle_exception(func_name: str, exception: Exception, is_async: bool = False) -> None:
    kind = "async" if is_async else "sync"
    msg = f"[ERROR] Exception in {kind} function '{func_name}': {exception}"
    logger.error(f"{msg}\n{traceback.format_exc()}")

def error_handling(
    obj: Optional[Union[Callable[..., Any], Type[Any]]] = None, 
    *, 
    re_raise: bool = False,
    exclude: tuple[str, ...] = ()
) -> Union[Callable[..., Any], Type[Any]]:
    """
    Decorator for automatic exception handling.
    Works for both functions and classes.
    Logs exceptions and optionally re-raises them.
    """

    if obj is None:
        return lambda f: error_handling(f, re_raise=re_raise, exclude=exclude)

    # Case 1: Class
    if inspect.isclass(obj):
        for name, attr in vars(obj).items():
            if callable(attr) and (name not in exclude) and (not name.startswith("__") or name == "__init__"):
                setattr(obj, name, error_handling(attr, re_raise=re_raise))
        return obj

    # Case 2: Coroutine function
    if inspect.iscoroutinefunction(obj):
        @functools.wraps(obj)
        async def async_wrapper(*args, **kwargs):
            try:
                return await obj(*args, **kwargs)
            except Exception as e:
                _handle_exception(obj.__name__, e, is_async=True)
                if re_raise:
                    raise
        return async_wrapper

    # Case 3: Sync function
    @functools.wraps(obj)
    def sync_wrapper(*args, **kwargs):
        try:
            return obj(*args, **kwargs)
        except Exception as e:
            _handle_exception(obj.__name__, e, is_async=False)
            if re_raise:
                raise
    return sync_wrapper
