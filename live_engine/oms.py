"""
oms.py — Order Management System with State Machine.
Tracks every order through its lifecycle and handles orphan recovery.
"""

import time
import asyncio
import logging
from enum import Enum, auto
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Order State Machine
# ─────────────────────────────────────────────────────────────────────

class OrderState(Enum):
    PENDING_SUBMIT = auto()
    NEW = auto()
    PARTIALLY_FILLED = auto()
    FILLED = auto()
    PENDING_CANCEL = auto()
    CANCELED = auto()
    REJECTED = auto()
    EXPIRED = auto()
    ORPHANED = auto()


@dataclass
class ManagedOrder:
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float | None = None
    state: OrderState = OrderState.PENDING_SUBMIT
    exchange_order_id: int | None = None
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    submit_ts: float = 0.0
    last_update_ts: float = 0.0
    retry_count: int = 0
    tags: dict = field(default_factory=dict)  # SL/TP/ENTRY metadata


TERMINAL_STATES = frozenset({
    OrderState.FILLED, OrderState.CANCELED,
    OrderState.REJECTED, OrderState.EXPIRED,
})

_STATE_MAP = {
    "NEW": OrderState.NEW,
    "PARTIALLY_FILLED": OrderState.PARTIALLY_FILLED,
    "FILLED": OrderState.FILLED,
    "CANCELED": OrderState.CANCELED,
    "REJECTED": OrderState.REJECTED,
    "EXPIRED": OrderState.EXPIRED,
}


class OrderMonitor:
    """
    Core OMS — tracks every order's exact state via User Data Stream.
    Handles orphan detection and REST fallback reconciliation.
    """
    ORPHAN_TIMEOUT_SEC = 5.0
    MAX_RETRIES = 3

    def __init__(self):
        self.orders: dict[str, ManagedOrder] = {}
        self._fill_callbacks: list = []

    def register_fill_callback(self, cb):
        self._fill_callbacks.append(cb)

    def on_order_submitted(self, order: ManagedOrder):
        order.state = OrderState.PENDING_SUBMIT
        order.submit_ts = time.monotonic()
        self.orders[order.client_order_id] = order
        logger.info(f"[OMS] Submitted: {order.client_order_id} "
                     f"{order.side} {order.quantity} {order.symbol}")

    def on_user_data_update(self, data: dict):
        """Called when ORDER_TRADE_UPDATE arrives from User Data Stream."""
        coid = data.get("c", "")
        status = data.get("X", "")
        order = self.orders.get(coid)

        if not order:
            logger.warning(f"[OMS] Unknown order update: {coid}")
            return

        prev_state = order.state
        new_state = _STATE_MAP.get(status)
        if new_state is None:
            logger.warning(f"[OMS] Unknown status '{status}' for {coid}")
            return

        order.state = new_state
        order.filled_qty = float(data.get("z", 0))
        order.avg_fill_price = float(data.get("ap", 0))
        order.exchange_order_id = int(data.get("i", 0))
        order.last_update_ts = time.monotonic()

        logger.info(f"[OMS] {coid}: {prev_state.name} → {new_state.name} "
                     f"filled={order.filled_qty}/{order.quantity}")

        if new_state == OrderState.FILLED:
            for cb in self._fill_callbacks:
                cb(order)

    async def check_orphans(self, rest_client):
        """Periodic sweep: recover orders stuck in PENDING_SUBMIT."""
        now = time.monotonic()
        for coid, order in list(self.orders.items()):
            if order.state != OrderState.PENDING_SUBMIT:
                continue
            if now - order.submit_ts < self.ORPHAN_TIMEOUT_SEC:
                continue

            logger.warning(f"[OMS] Orphan detected: {coid} "
                           f"(age={now - order.submit_ts:.1f}s)")
            try:
                resp = await rest_client.get_order(
                    symbol=order.symbol,
                    orig_client_order_id=coid,
                )
                if resp:
                    self.on_user_data_update(resp)
                else:
                    order.state = OrderState.ORPHANED
                    order.retry_count += 1
                    if order.retry_count >= self.MAX_RETRIES:
                        logger.error(f"[OMS] Order {coid} permanently orphaned")
            except Exception as e:
                logger.error(f"[OMS] Orphan check failed: {e}")

    def get_active_orders(self, symbol: str = "") -> list[ManagedOrder]:
        return [
            o for o in self.orders.values()
            if o.state not in TERMINAL_STATES
            and (not symbol or o.symbol == symbol)
        ]

    def cleanup_terminal(self, max_age_sec: float = 3600):
        """Remove old terminal-state orders from memory."""
        now = time.monotonic()
        to_remove = [
            coid for coid, o in self.orders.items()
            if o.state in TERMINAL_STATES
            and now - o.last_update_ts > max_age_sec
        ]
        for coid in to_remove:
            del self.orders[coid]


# ─────────────────────────────────────────────────────────────────────
# Rate Limit Manager
# ─────────────────────────────────────────────────────────────────────

class RateLimitManager:
    """Tracks Binance API weight to prevent 429/IP bans."""

    def __init__(self, max_weight: int = 2400, window_sec: int = 60):
        self.max_weight = max_weight
        self.window_sec = window_sec
        self._requests: deque[tuple[float, int]] = deque()

    def _purge_old(self):
        cutoff = time.monotonic() - self.window_sec
        while self._requests and self._requests[0][0] < cutoff:
            self._requests.popleft()

    @property
    def current_weight(self) -> int:
        self._purge_old()
        return sum(w for _, w in self._requests)

    @property
    def utilization_pct(self) -> float:
        return self.current_weight / self.max_weight * 100

    def can_request(self, weight: int = 1) -> bool:
        return self.current_weight + weight <= int(self.max_weight * 0.85)

    def record(self, weight: int = 1):
        self._requests.append((time.monotonic(), weight))

    async def wait_if_needed(self, weight: int = 1):
        while not self.can_request(weight):
            logger.warning(f"[RATE] Throttled. Weight={self.current_weight}"
                           f"/{self.max_weight}")
            await asyncio.sleep(0.5)
        self.record(weight)
