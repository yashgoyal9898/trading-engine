# src/infrastructure/logger.py
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Self
import aiofiles
import logging
from contextlib import asynccontextmanager


class LoggerManager:
    _instance: 'LoggerManager | None' = None

    def __new__(cls, *args, **kwargs) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, log_dir: Path | None = None) -> None:
        if hasattr(self, '_initialized'):
            return

        self.log_dir = log_dir or Path.cwd() / "logger_files" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self._queue: asyncio.Queue[logging.LogRecord | None] | None = None
        self._worker_task: asyncio.Task | None = None
        self._formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self._initialized = True

    @property
    def _log_file(self) -> Path:
        return self.log_dir / f"TS_{datetime.now():%Y-%m-%d}.log"

    async def _log_worker(self) -> None:
        async with aiofiles.open(self._log_file, "a", encoding="utf-8") as f:
            while True:
                record = await self._queue.get()
                if record is None:
                    self._queue.task_done()
                    break
                try:
                    log_line = f"{self._formatter.format(record)}\n"
                    await asyncio.gather(
                        f.write(log_line),
                        asyncio.to_thread(print, log_line, end='')
                    )
                except Exception:
                    pass
                finally:
                    self._queue.task_done()

    async def start(self) -> None:
        # BUG FIX: Singleton ka queue purani event loop se bound hota hai.
        # Har start() pe fresh queue banao taki nayi loop ke saath kaam kare.
        # Yeh test isolation ke liye zaroori hai (har test ki apni loop hoti hai).
        # Production mein sirf ek baar start() hoti hai, koi fark nahi padta.
        if self._worker_task is not None and not self._worker_task.done():
            return  # already running — kuch mat karo

        # Nayi loop ke liye fresh queue
        self._queue = asyncio.Queue()
        self._worker_task = asyncio.create_task(self._log_worker())

    async def stop(self) -> None:
        if self._worker_task and not self._worker_task.done():
            await self._queue.put(None)
            await self._queue.join()
            try:
                await asyncio.wait_for(self._worker_task, timeout=3.0)
            except asyncio.TimeoutError:
                self._worker_task.cancel()
                with asyncio.suppress(asyncio.CancelledError):
                    await self._worker_task
        # Reset karo taki agla start() fresh queue bana sake
        self._worker_task = None
        self._queue = None

    def _log(self, level: int, msg: str) -> None:
        if self._queue is None:
            return  # logger start nahi hua — silently drop karo
        record = logging.LogRecord(
            name=__name__, level=level, pathname="", lineno=0,
            msg=msg, args=(), exc_info=None
        )
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            pass

    def debug(self, msg: str) -> None: self._log(logging.DEBUG, msg)
    def info(self, msg: str) -> None: self._log(logging.INFO, msg)
    def warning(self, msg: str) -> None: self._log(logging.WARNING, msg)
    def error(self, msg: str) -> None: self._log(logging.ERROR, msg)
    def critical(self, msg: str) -> None: self._log(logging.CRITICAL, msg)

    @asynccontextmanager
    async def lifespan(self):
        await self.start()
        try:
            yield self
        finally:
            await self.stop()


logger = LoggerManager()