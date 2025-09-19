from fyers_apiv3.FyersWebsocket import order_ws
import asyncio
from utils.error_handling import error_handling
from utils.logger import logger
from dotenv import load_dotenv
import os

load_dotenv()

@error_handling
class FyersOrderManager:
    _instance = None

    @staticmethod
    def get_instance():
        if FyersOrderManager._instance is None:
            FyersOrderManager._instance = FyersOrderManager()
        return FyersOrderManager._instance

    def __init__(self):
        if FyersOrderManager._instance is not None:
            raise Exception("This class is a singleton! Use get_instance() instead.")

        client_id = os.getenv("CLIENT_ID")
        access_token = os.getenv("FYERS_ACCESS_TOKEN")
        if not client_id or not access_token:
            raise ValueError("Missing CLIENT_ID or FYERS_ACCESS_TOKEN in environment")

        self.access_token = f"{client_id}:{access_token}"

        self.callbacks = []         # list of callback functions
        self.events = {}            # symbol -> asyncio.Event

        self.fyers = order_ws.FyersOrderSocket(
            access_token=self.access_token,
            write_to_file=False,
            log_path=None,
            on_connect=self.on_open,
            on_close=self.on_close,
            on_error=self.on_error,
            on_positions=self.on_position,
        )

        self._task = None  # asyncio task running the socket

    # ---------------- WebSocket Callbacks ----------------
    def on_open(self):
        self.fyers.subscribe(data_type="OnPositions")

    def on_close(self, msg):
        logger.info(f"[Order WS] Closed: {msg}")

    def on_error(self, msg):
        logger.error(f"[Order WS] Error: {msg}")

    # ---------------- Position Handler ----------------
    def on_position(self, msg):
        positions = msg.get("positions")
        if not positions:
            return

        positions_list = positions if isinstance(positions, list) else [positions]

        for pos in positions_list:
            symbol = pos.get("symbol")

            # fire callbacks
            for cb in self.callbacks:
                cb(pos)

            # release waiters
            event = self.events.get(symbol)
            if event:
                event.set()
                self.events.pop(symbol, None)

    # ---------------- Public Methods ----------------
    async def connect(self):
        loop = asyncio.get_running_loop()
        self._task = loop.run_in_executor(None, self.fyers.connect)

    async def stop(self):
        if self.fyers:
            try:
                self.fyers.keep_running = False
                if hasattr(self.fyers, "ws") and self.fyers.ws:
                    self.fyers.ws.close(status=1000, reason="Normal Closure")

                if self._task:
                    # cancel executor task
                    self._task.cancel()
                logger.info("[Order WS] Closed cleanly.")
            except Exception as e:
                logger.error(f"[Order WS] Exception during close: {e}")

    def register_close_callback(self, callback):
        if callable(callback):
            self.callbacks.append(callback)

    async def wait_for_trade_close(self, symbol: str):
        event = asyncio.Event()
        self.events[symbol] = event
        await event.wait()
        self.events.pop(symbol, None)
