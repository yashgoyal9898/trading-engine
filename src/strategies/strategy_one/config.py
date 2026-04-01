from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StrategyOneParams:
    """
    settings.yml ke `params:` section se load hota hai.
    """
    body_pct_threshold: float = 10.0   # Candle body > 10% of range = entry signal

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyOneParams":
        return cls(
            body_pct_threshold=float(d.get("body_pct_threshold", 10.0)),
        )