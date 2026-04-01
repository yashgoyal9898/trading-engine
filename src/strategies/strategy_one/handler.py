from __future__ import annotations

from typing import Dict, List, Optional

from ...core.data_model import Candle, Signal, TradeData
from ...infrastructure.config_loader import StrategyConfig
from ..base_strategy import BaseStrategy
from .config import StrategyOneParams
from .logic import compute_entry, compute_exit


class Handler(BaseStrategy):
    """
    Strategy One Handler.

    Key concept:
        Signal symbol  → candle yahan se banta hai  (e.g. NSE:NIFTY50-INDEX)
        Order symbol   → order yahan jayega           (e.g. NSE:IDEA-EQ)

    Mapping config se automatically banta hai.
    """

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        self._params = StrategyOneParams.from_dict(config.params)
        self._history: Dict[str, List[Candle]] = {}
        self._MAX_HISTORY = 50

        # signal_symbol → order_symbol mapping
        # Agar order_symbol set nahi hai toh signal_symbol hi use hoga
        self._order_symbol: Dict[str, str] = {
            sym.name: sym.effective_order_symbol
            for sym in config.symbols
        }

    def entry_signal(self, candle: Candle) -> Optional[Signal]:
        history = self._history.get(candle.symbol, [])

        # Order symbol nikalo — candle ka symbol ≠ order ka symbol ho sakta hai
        order_sym = self._order_symbol.get(candle.symbol, candle.symbol)

        signal = compute_entry(candle, history, self._params, order_sym)

        # History update karo
        history.append(candle)
        if len(history) > self._MAX_HISTORY:
            history.pop(0)
        self._history[candle.symbol] = history

        return signal

    def exit_signal(self, candle: Candle, trade: TradeData) -> Optional[Signal]:
        return compute_exit(candle, trade, self._params)