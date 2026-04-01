from __future__ import annotations

import logging
from typing import Dict, List, Optional

from fyers_apiv3 import fyersModel

from ...core.data_model import Signal, TradeData
from ...core.enums import OrderSide, OrderType, TradeStatus
from ...core.interfaces.iorder_broker import IOrderBroker
from ..registry import register_order_broker

logger = logging.getLogger(__name__)


@register_order_broker("fyers")
class FyersOrderBroker(IOrderBroker):
    """
    Fyers REST API order broker.
    """

    def __init__(self, client_id: str, access_token: str, **kwargs):
        self._client_id = client_id
        # Fyers token format: "APP_ID:token"
        self._token = f"{client_id}:{access_token}"
        self._connected = False
        self._fyers: Optional[fyersModel.FyersModel] = None

    async def connect(self) -> None:
        self._fyers = fyersModel.FyersModel(
            client_id=self._client_id,
            is_async=False,
            token=self._token,
            log_path="",
        )
        self._connected = True
        logger.info("FyersOrderBroker: connected")

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("FyersOrderBroker: disconnected")

    async def place_order(self, signal: Signal) -> str:
        order_dict = {
            "symbol":       signal.symbol,
            "qty":          signal.quantity,
            "type":         self._map_order_type(signal.order_type),
            "side":         1 if signal.side == OrderSide.BUY else -1,
            "productType":  "INTRADAY",
            "limitPrice":   signal.price,
            "stopPrice":    signal.sl,
            "validity":     "DAY",
            "disclosedQty": 0,
            "offlineOrder": False,
        }
        response = self._fyers.place_order(data=order_dict)
        logger.info("FyersOrderBroker: place_order response — %s", response)

        if response.get("s") != "ok":
            raise RuntimeError(f"Order placement failed: {response}")

        return str(response.get("id", ""))

    async def cancel_order(self, order_id: str) -> bool:
        response = self._fyers.cancel_order(data={"id": order_id})
        logger.info("FyersOrderBroker: cancel_order response — %s", response)
        return response.get("s") == "ok"

    async def get_order_status(self, order_id: str) -> Dict:
        response = self._fyers.order_detail(data={"id": order_id})
        return response or {}

    async def get_positions(self) -> List[TradeData]:
        response = self._fyers.positions()
        # Raw positions ko TradeData mein map karna future mein karo
        return []

    @property
    def is_connected(self) -> bool:
        return self._connected

    @staticmethod
    def _map_order_type(order_type: OrderType) -> int:
        return {
            OrderType.MARKET: 2,
            OrderType.LIMIT:  1,
            OrderType.SL:     4,
            OrderType.SL_M:   3,
        }[order_type]