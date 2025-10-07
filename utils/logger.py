import asyncio
import aiofiles
import os
from datetime import datetime
import atexit

class Logger:
    def __init__(self, log_dir=None):
        self.log_dir = log_dir or os.path.join(os.getcwd(), "logger_files", "logs")
        os.makedirs(self.log_dir, exist_ok=True)

        self.log_file = self._get_log_file()
        self.log_queue = asyncio.Queue()
        self._worker_started = False
        self._worker_task = None

        # ensure flush on exit
        atexit.register(self._flush_on_exit)

    def _get_log_file(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.log_dir, f"main_script_{today_str}.log")

    def _get_timestamp(self):
        dt = datetime.now()
        millis = dt.microsecond // 1000
        return f"{dt.strftime('%Y-%m-%d %H:%M:%S')}.{millis:03d}"

    async def _log_worker(self):
        while True:
            level, msg, timestamp = await self.log_queue.get()
            log_line = f"[{timestamp}] [{level}] {msg}\n"
            try:
                async with aiofiles.open(self._get_log_file(), "a") as f:
                    await f.write(log_line)
            except Exception as e:
                print(f"[LOGGER ERROR] Failed to write log: {e}")
            self.log_queue.task_done()

    def _start_worker(self):
        if not self._worker_started:
            try:
                loop = asyncio.get_running_loop()
                self._worker_task = loop.create_task(self._log_worker())
                self._worker_started = True
            except RuntimeError:
                pass

    def _log(self, level, msg):
        timestamp = self._get_timestamp()
        log_line = f"[{timestamp}] [{level}] {msg}"
        print(log_line)  # terminal output

        try:
            loop = asyncio.get_running_loop()
            self._start_worker()
            self.log_queue.put_nowait((level, msg, timestamp))
        except RuntimeError:
            with open(self._get_log_file(), "a") as f:
                f.write(f"{log_line}\n")

    # Public API
    def info(self, msg):
        self._log("INFO", msg)

    def error(self, msg):
        self._log("ERROR", msg)

    def debug(self, msg):
        self._log("DEBUG", msg)
    
    def warning(self, msg):
        self._log("WARNING", msg)

    async def flush(self):
        if self._worker_started:
            await self.log_queue.join()

    def _flush_on_exit(self):
        if self._worker_started:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.flush())
                else:
                    loop.run_until_complete(self.flush())
            except RuntimeError:
                pass

# Create a logger instance
logger = Logger()
