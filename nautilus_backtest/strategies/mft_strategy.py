"""
MFT Strategy — Nautilus Trader Implementation
==============================================
Layer 1 (Bias)   : EMA 200 → กำหนดทิศทางใหญ่
Layer 2 (Entry)  : EMA 9/21 crossover + RSI filter
Layer 3 (Volume) : RVOL > 1.5 ยืนยัน momentum

ปรับพารามิเตอร์ได้ใน MFTConfig
"""

from decimal import Decimal
from collections import deque

import numpy as np

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class MFTConfig(StrategyConfig, frozen=True):
    instrument_id: str = "BTCUSDT-PERP.BINANCE"
    bar_type: str = "BTCUSDT-PERP.BINANCE-1-MINUTE-LAST-EXTERNAL"

    # EMA periods
    ema_fast: int = 9
    ema_medium: int = 21
    ema_slow: int = 200

    # RSI
    rsi_period: int = 14
    rsi_long_min: float = 50.0   # RSI ต้องอยู่เหนือนี้เพื่อ long
    rsi_long_max: float = 65.0
    rsi_short_min: float = 35.0  # RSI ต้องอยู่ใต้นี้เพื่อ short
    rsi_short_max: float = 50.0

    # Volume
    rvol_period: int = 20         # ค่าเฉลี่ย volume ย้อนหลัง N bars
    rvol_threshold: float = 1.5   # RVOL ต้องสูงกว่านี้

    # Risk
    trade_size: float = 0.001     # BTC ต่อ trade (ปรับตาม account)
    stop_loss_pct: float = 0.005  # 0.5%
    take_profit_pct: float = 0.01 # 1.0%

    # Warmup — ต้องรอให้มี data ครบก่อน
    warmup_bars: int = 210        # อย่างน้อย ema_slow + buffer


# ---------------------------------------------------------------------------
# Utility: Indicators (คำนวณเอง ไม่ต้องพึ่ง ta-lib)
# ---------------------------------------------------------------------------

def ema(prices: deque, period: int) -> float:
    """คำนวณ EMA จาก deque of prices (newest last)"""
    arr = np.array(prices)
    k = 2.0 / (period + 1)
    result = arr[0]
    for p in arr[1:]:
        result = p * k + result * (1 - k)
    return result


def rsi(prices: deque, period: int) -> float:
    """คำนวณ RSI จาก deque (newest last)"""
    arr = np.array(prices)
    deltas = np.diff(arr[-(period + 1):])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1 + rs))


def rvol(volumes: deque, period: int) -> float:
    """Relative Volume = current vol / avg vol ย้อนหลัง period bars"""
    arr = np.array(volumes)
    if len(arr) < period + 1:
        return 0.0
    current = arr[-1]
    avg = np.mean(arr[-(period + 1):-1])
    if avg == 0:
        return 0.0
    return current / avg


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class MFTStrategy(Strategy):
    """
    Multi-Frame Trend Strategy
    
    State Machine:
    ┌─────────────┐    EMA bias OK     ┌────────────┐
    │   WAITING   │ ─────────────────► │  WATCHING  │
    └─────────────┘                    └─────┬──────┘
           ▲                                 │ EMA cross + RSI + RVOL
           │         stop/tp hit             ▼
    ┌──────┴──────┐ ◄──────────────── ┌────────────┐
    │   WAITING   │                   │  IN_TRADE  │
    └─────────────┘                   └────────────┘
    """

    def __init__(self, config: MFTConfig):
        super().__init__(config)
        self.cfg = config

        # Instrument
        self._instrument_id = InstrumentId.from_str(config.instrument_id)

        # Price/volume buffers — เก็บ closing prices
        max_buf = config.ema_slow + config.rsi_period + 10
        self._closes: deque = deque(maxlen=max_buf)
        self._volumes: deque = deque(maxlen=config.rvol_period + 5)

        # State
        self._bar_count: int = 0
        self._position_open: bool = False
        self._entry_price: float = 0.0
        self._entry_side: OrderSide | None = None

        # Last signal info (for logging)
        self._last_ema_fast: float = 0.0
        self._last_ema_medium: float = 0.0
        self._last_ema_slow: float = 0.0
        self._last_rsi: float = 50.0
        self._last_rvol: float = 0.0

    # ------------------------------------------------------------------
    # Nautilus lifecycle hooks
    # ------------------------------------------------------------------

    def on_start(self):
        bar_type = BarType.from_str(self.cfg.bar_type)
        self.subscribe_bars(bar_type)
        self.log.info(
            f"MFT Strategy started | "
            f"EMA {self.cfg.ema_fast}/{self.cfg.ema_medium}/{self.cfg.ema_slow} | "
            f"RSI {self.cfg.rsi_period} | RVOL {self.cfg.rvol_threshold}"
        )

    def on_stop(self):
        self.log.info("MFT Strategy stopped")

    # ------------------------------------------------------------------
    # Main bar handler
    # ------------------------------------------------------------------

    def on_bar(self, bar: Bar):
        close = float(bar.close)
        volume = float(bar.volume)

        self._closes.append(close)
        self._volumes.append(volume)
        self._bar_count += 1

        # รอ warmup ก่อน
        if self._bar_count < self.cfg.warmup_bars:
            if self._bar_count % 50 == 0:
                self.log.info(f"Warming up... {self._bar_count}/{self.cfg.warmup_bars}")
            return

        # คำนวณ indicators
        self._last_ema_fast = ema(self._closes, self.cfg.ema_fast)
        self._last_ema_medium = ema(self._closes, self.cfg.ema_medium)
        self._last_ema_slow = ema(self._closes, self.cfg.ema_slow)
        self._last_rsi = rsi(self._closes, self.cfg.rsi_period)
        self._last_rvol = rvol(self._volumes, self.cfg.rvol_period)

        # Check exit ถ้ามี position อยู่
        if self._position_open:
            self._check_exit(close)
            return

        # Check entry
        self._check_entry(close, bar)

    # ------------------------------------------------------------------
    # Layer 1-3: Entry Logic
    # ------------------------------------------------------------------

    def _check_entry(self, close: float, bar: Bar):
        """
        LONG  : price > EMA200 AND EMA9 crosses above EMA21 AND RSI 50-65 AND RVOL > 1.5
        SHORT : price < EMA200 AND EMA9 crosses below EMA21 AND RSI 35-50 AND RVOL > 1.5
        """
        ef = self._last_ema_fast
        em = self._last_ema_medium
        es = self._last_ema_slow
        r = self._last_rsi
        rv = self._last_rvol

        # Layer 3: Volume confirmation
        if rv < self.cfg.rvol_threshold:
            return

        # Layer 1: Bias filter
        bias_long = close > es
        bias_short = close < es

        # Layer 2: EMA crossover + RSI
        cross_long = ef > em      # EMA9 อยู่เหนือ EMA21
        cross_short = ef < em     # EMA9 อยู่ใต้ EMA21

        rsi_ok_long = self.cfg.rsi_long_min <= r <= self.cfg.rsi_long_max
        rsi_ok_short = self.cfg.rsi_short_min <= r <= self.cfg.rsi_short_max

        if bias_long and cross_long and rsi_ok_long:
            self._enter(OrderSide.BUY, close)
        elif bias_short and cross_short and rsi_ok_short:
            self._enter(OrderSide.SELL, close)

    def _check_exit(self, close: float):
        """Exit ด้วย fixed SL/TP — ทีหลังอาจเปลี่ยนเป็น trailing"""
        if self._entry_side == OrderSide.BUY:
            sl = self._entry_price * (1 - self.cfg.stop_loss_pct)
            tp = self._entry_price * (1 + self.cfg.take_profit_pct)
            if close <= sl:
                self.log.warning(f"STOP LOSS hit @ {close:.2f} (entry={self._entry_price:.2f})")
                self._close_position()
            elif close >= tp:
                self.log.info(f"TAKE PROFIT hit @ {close:.2f} (entry={self._entry_price:.2f})")
                self._close_position()

        elif self._entry_side == OrderSide.SELL:
            sl = self._entry_price * (1 + self.cfg.stop_loss_pct)
            tp = self._entry_price * (1 - self.cfg.take_profit_pct)
            if close >= sl:
                self.log.warning(f"STOP LOSS hit @ {close:.2f} (entry={self._entry_price:.2f})")
                self._close_position()
            elif close <= tp:
                self.log.info(f"TAKE PROFIT hit @ {close:.2f} (entry={self._entry_price:.2f})")
                self._close_position()

    # ------------------------------------------------------------------
    # Order helpers
    # ------------------------------------------------------------------

    def _enter(self, side: OrderSide, price: float):
        self.log.info(
            f"ENTRY {side.name} @ {price:.2f} | "
            f"EMA {self._last_ema_fast:.1f}/{self._last_ema_medium:.1f}/{self._last_ema_slow:.1f} | "
            f"RSI {self._last_rsi:.1f} | RVOL {self._last_rvol:.2f}x"
        )
        self._position_open = True
        self._entry_price = price
        self._entry_side = side

        # ส่ง Market Order ผ่าน Nautilus
        order = self.order_factory.market(
            instrument_id=self._instrument_id,
            order_side=side,
            quantity=Quantity.from_str(f"{self.cfg.trade_size:.3f}"),
        )
        self.submit_order(order)

    def _close_position(self):
        # ส่ง Market Order ฝั่งตรงข้ามเพื่อปิด position
        if self._entry_side is not None:
            close_side = OrderSide.SELL if self._entry_side == OrderSide.BUY else OrderSide.BUY
            order = self.order_factory.market(
                instrument_id=self._instrument_id,
                order_side=close_side,
                quantity=Quantity.from_str(f"{self.cfg.trade_size:.3f}"),
                reduce_only=True,
            )
            self.submit_order(order)

        self._position_open = False
        self._entry_price = 0.0
        self._entry_side = None
