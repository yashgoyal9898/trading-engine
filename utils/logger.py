import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional
import aiofiles
import logging
import os

class LoggerManager:
    _instance: Optional['LoggerManager'] = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, log_dir: Optional[Path] = None):
        if self._initialized:
            return

        # Logging directory
        self.log_dir = log_dir or Path.cwd() / "logger_files" / "logs"
        os.makedirs(self.log_dir, exist_ok=True)

        # Async queue and task
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None

        # Formatter for terminal and file output
        self._formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        self._initialized = True

    def _get_log_file(self) -> Path:
        return self.log_dir / f"main_script_{datetime.now():%Y-%m-%d}.log"

    async def _log_worker(self):
        file_path = self._get_log_file()
        async with aiofiles.open(file_path, "a", encoding="utf-8") as f:
            while True:
                record = await self._queue.get()
                if record is None:  # Sentinel to stop
                    break

                # Simple text log line
                log_line = self._formatter.format(record) + "\n"
                await f.write(log_line)
                await f.flush()

                # Terminal output
                print(log_line, end='')

                self._queue.task_done()

    async def start(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        if self._worker_task is None or self._worker_task.done():
            self._loop = loop or asyncio.get_running_loop()
            self._worker_task = self._loop.create_task(self._log_worker())

    async def stop(self):
        if self._worker_task and not self._worker_task.done():
            await self._queue.put(None)
            try:
                await asyncio.wait_for(self._worker_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass

    def _log(self, level: int, msg: str):
        record = logging.LogRecord(
            name=__name__,
            level=level,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None
        )
        self._queue.put_nowait(record)

    # Public API
    def debug(self, msg: str): self._log(logging.DEBUG, msg)
    def info(self, msg: str): self._log(logging.INFO, msg)
    def warning(self, msg: str): self._log(logging.WARNING, msg)
    def error(self, msg: str): self._log(logging.ERROR, msg)
    def critical(self, msg: str): self._log(logging.CRITICAL, msg)

logger = LoggerManager()
