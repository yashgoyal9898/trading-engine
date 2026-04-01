from __future__ import annotations

import asyncio
import logging
import signal

import uvloop  # noqa: F401 — main.py mein uvloop.install() call hoti hai
               # yahan import sirf clarity ke liye hai ki hum uvloop use kar rahe hain

import src.broker  # noqa: F401 — Fyers data+order broker register hote hain yahan

from .broker.registry import BrokerRegistry
from .infrastructure.config_loader import AppConfig
from .infrastructure.logger import logger
from .managers.candle_manager import CandleManager
from .managers.order_placement_manager import OrderPlacementManager
from .managers.symbol_manager import SymbolManager
from .managers.trade_state_manager import TradeStateManager
from .strategies.registry import StrategyRegistry

_log = logging.getLogger(__name__)


class Engine:
    """
    Poore system ka ek orchestrator.

    Start order:
        1. Logger
        2. Brokers connect
        3. Managers banao
        4. Strategies load + wire
        5. Symbols subscribe
        6. Strategies start

    Stop order (bilkul ulta):
        1. Strategies stop
        2. Brokers disconnect
        3. Logger flush + stop
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._data_broker = None
        self._order_broker = None
        self._symbol_manager: SymbolManager | None = None
        self._candle_manager: CandleManager | None = None
        self._trade_state_manager: TradeStateManager | None = None
        self._order_placement_manager: OrderPlacementManager | None = None
        self._strategies = []
        self._running = False

    # ------------------------------------------------------------------ #
    #  Startup
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        # 1. Logger sabse pehle start karo
        await logger.start()
        logger.info("=== Engine starting ===")

        # 2. Brokers
        self._data_broker = BrokerRegistry.get_data_broker(
            self._config.brokers.data
        )
        self._order_broker = BrokerRegistry.get_order_broker(
            self._config.brokers.order
        )
        await self._data_broker.connect()
        await self._order_broker.connect()
        logger.info(
            f"Brokers connected: data={self._config.brokers.data} "
            f"order={self._config.brokers.order}"
        )

        # 3. Managers
        self._candle_manager = CandleManager()
        self._trade_state_manager = TradeStateManager()
        self._symbol_manager = SymbolManager(self._data_broker)
        self._order_placement_manager = OrderPlacementManager(
            self._order_broker, self._trade_state_manager
        )

        # 4. Strategies load + wire
        self._strategies = StrategyRegistry.load(self._config.strategies)
        for strat in self._strategies:
            strat.wire(
                self._order_placement_manager,
                self._trade_state_manager,
                self._candle_manager,
            )

        # 5. Symbols subscribe
        for strat_cfg in self._config.strategies:
            if not strat_cfg.enabled:
                continue
            for sym_cfg in strat_cfg.symbols:
                if sym_cfg.mode == "candle":
                    self._candle_manager.register(
                        sym_cfg.name,
                        sym_cfg.timeframe,
                        self._make_candle_dispatcher(sym_cfg.name, sym_cfg.timeframe),
                    )
                await self._symbol_manager.subscribe(
                    sym_cfg.name,
                    self._candle_manager.on_tick,
                )

        # 6. Strategies start — uvloop event loop pe run honge (main.py ne install kiya hai)
        await asyncio.gather(*[s.start() for s in self._strategies])

        self._running = True
        logger.info(
            f"=== Engine running | strategies={len(self._strategies)} ==="
        )

    # ------------------------------------------------------------------ #
    #  Shutdown
    # ------------------------------------------------------------------ #

    async def stop(self) -> None:
        logger.info("=== Engine shutting down ===")
        self._running = False

        # 1. Strategies pehle band karo
        if self._strategies:
            await asyncio.gather(
                *[s.stop() for s in self._strategies],
                return_exceptions=True,
            )

        # 2. Brokers disconnect
        if self._data_broker:
            await self._data_broker.disconnect()
        if self._order_broker:
            await self._order_broker.disconnect()

        logger.info("=== Engine stopped ===")

        # 3. Logger sabse last — sab logs flush ho jayein
        await logger.stop()

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _make_candle_dispatcher(self, symbol: str, timeframe: int):
        """
        Closed candle ko uss (symbol, timeframe) ko watch karne
        wali saari strategies tak pohonchata hai.
        return type: sync wrapper (CandleManager sync callback expect karta hai)
        """
        strategies = self._strategies
        config_strategies = self._config.strategies

        async def _dispatch(candle):
            tasks = []
            for strat in strategies:
                cfg = next(
                    (s for s in config_strategies if s.id == strat.strategy_id),
                    None,
                )
                if cfg is None:
                    continue
                for sym in cfg.symbols:
                    if sym.name == symbol and sym.timeframe == timeframe:
                        tasks.append(strat.on_candle(candle))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        def _sync_wrapper(candle):
            # uvloop event loop chal raha hai, create_task safe hai
            asyncio.get_event_loop().create_task(_dispatch(candle))

        return _sync_wrapper

    async def run_forever(self) -> None:
        """SIGINT / SIGTERM aane tak block karo, phir graceful stop."""
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def _on_signal():
            logger.info("Shutdown signal received")
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _on_signal)

        await stop_event.wait()
        await self.stop()