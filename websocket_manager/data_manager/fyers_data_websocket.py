# fyers_data_websocket.py
import os
import threading
import asyncio
from dotenv import load_dotenv
from fyers_apiv3.FyersWebsocket import data_ws
from utils.logger import logger
from .base import BaseWSManager
from utils.error_handling import error_handling

load_dotenv()

@error_handling
class FyersTransport:
    def __init__(self, access_token, reconnect=True, litemode=False, write_to_file=False):
        self._socket = None
        self._opts = {
            "access_token": access_token,
            "reconnect": reconnect,
            "litemode": litemode,
            "write_to_file": write_to_file,
        }
        self._thread = None
        self._running = False
        self._queue = None
        self._loop = None

    def start(self, loop, queue: asyncio.Queue, on_open=None, on_error=None, on_close=None):
        self._queue = queue
        self._loop = loop
        self._running = True
        self._thread = threading.Thread(
            target=self._run_ws, args=(on_open, on_error, on_close), daemon=True
        )
        self._thread.start()

    def _run_ws(self, on_open, on_error, on_close):
        def _on_message(message):
            if self._running and self._loop:
                asyncio.run_coroutine_threadsafe(self._queue.put(message), self._loop)

        self._socket = data_ws.FyersDataSocket(
            on_connect=on_open,
            on_message=_on_message,
            on_error=on_error,
            on_close=on_close,
            **self._opts
        )
        self._socket.connect()
        self._socket.keep_running()

    def subscribe(self, symbols, topic=None):
        if self._socket:
            self._socket.subscribe(symbols, topic or "SymbolUpdate")

    def unsubscribe(self, symbols):
        if self._socket:
            self._socket.unsubscribe(symbols)

    def close(self):
        self._running = False
        if self._socket:
            self._socket.close_connection()

@error_handling
class FyersWSManager(BaseWSManager):
    _instance = None
    _lock = threading.Lock()

    @staticmethod
    def get_instance():
        if FyersWSManager._instance is None:
            with FyersWSManager._lock:
                if FyersWSManager._instance is None:
                    FyersWSManager._instance = FyersWSManager()
        return FyersWSManager._instance

    def __init__(self, access_token=None):
        token = access_token or os.getenv("FYERS_ACCESS_TOKEN")
        if not token:
            logger.warning("FYERS_ACCESS_TOKEN is empty.")
        super().__init__(transport=FyersTransport(token))
