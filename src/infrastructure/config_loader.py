from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


def _parse_timeframe_seconds(tf) -> int:
    """
    Timeframe ko hamesha SECONDS mein return karta hai.

    Examples:
        "30s"  ->  30   (30 seconds)
        "15s"  ->  15   (15 seconds)
        "5m"   -> 300   (5 minutes)
        "1"    ->  60   (default: minutes, so 1 min = 60 sec)
        1      ->  60
    """
    if isinstance(tf, str):
        tf = tf.strip()
        if tf.endswith("s"):
            return int(tf[:-1])
        elif tf.endswith("m"):
            return int(tf[:-1]) * 60
    return int(tf) * 60  # number without unit = minutes


@dataclass
class SymbolConfig:
    name: str                          # Signal symbol (candle yahan se banega)
    mode: str                          # "tick" | "candle"
    timeframe: int = 60                # Internally ALWAYS seconds
    order_symbol: Optional[str] = None # Order yahan place hoga (None = same as name)

    @property
    def effective_order_symbol(self) -> str:
        """Agar order_symbol set nahi hai toh signal symbol hi use karo."""
        return self.order_symbol or self.name


@dataclass
class StrategyConfig:
    id: str
    module: str
    enabled: bool = True
    max_trades: int = 1
    symbols: List[SymbolConfig] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BrokerConfig:
    data: str
    order: str


@dataclass
class AppConfig:
    brokers: BrokerConfig
    strategies: List[StrategyConfig]


def load_config(path: str = "config/settings.yml") -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path.resolve()}")

    with config_path.open() as f:
        raw: Dict = yaml.safe_load(f)

    broker_raw = raw.get("brokers", {})
    brokers = BrokerConfig(
        data=broker_raw["data"],
        order=broker_raw["order"],
    )

    strategies: List[StrategyConfig] = []
    for s in raw.get("strategies", []):
        symbols = [
            SymbolConfig(
                name=sym["name"],
                mode=sym.get("mode", "candle"),
                timeframe=_parse_timeframe_seconds(sym.get("timeframe", 1)),
                order_symbol=sym.get("order_symbol", None),
            )
            for sym in s.get("symbols", [])
        ]
        strategies.append(
            StrategyConfig(
                id=s["id"],
                module=s["module"],
                enabled=s.get("enabled", True),
                max_trades=s.get("max_trades", 1),
                symbols=symbols,
                params=s.get("params", {}),
            )
        )

    return AppConfig(brokers=brokers, strategies=strategies)