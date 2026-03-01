"""
instruments.py — Centralized instrument registry for Binance Perpetual Futures
===============================================================================
Single source of truth for all instrument specifications.
Every other file imports from here — never define CryptoPerpetual elsewhere.

Supported instruments:
    SOLUSDT, BNBUSDT, XRPUSDT, LINKUSDT, AVAXUSDT

Usage:
    from instruments import build_instrument, build_all_instruments, INSTRUMENT_SPECS
    inst = build_instrument("SOLUSDT")
    all_insts = build_all_instruments(["SOLUSDT", "BNBUSDT"])
"""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import CurrencyType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.objects import Currency, Money, Price, Quantity

# ── Venue ─────────────────────────────────────────────────────────────────────

VENUE = Venue("BINANCE")

# ── Per-instrument precision and fee specification ────────────────────────────
#
# price_precision : decimal places for prices   (affects order formatting)
# size_precision  : decimal places for quantities (affects order formatting)
# price_increment : minimum price tick
# size_increment  : minimum lot size
# margin_init     : initial margin fraction (0.05 = 20x max leverage)
# margin_maint    : maintenance margin fraction
# maker_fee       : rebate/fee for limit orders
# taker_fee       : fee for market orders
#
# Source: Binance Futures exchange info (verified 2026-02)

INSTRUMENT_SPECS: dict[str, dict] = {
    "SOLUSDT": {
        "base_currency_code": "SOL",
        "price_precision":    4,
        "size_precision":     0,           # whole SOL units only
        "price_increment":    "0.0100",
        "size_increment":     "1",
        "min_quantity":       "1",
        "max_quantity":       "100000",
        "min_notional":       5,
        "max_price":          "99999.9900",
        "margin_init":        "0.05",
        "margin_maint":       "0.025",
        "maker_fee":          "0.0002",
        "taker_fee":          "0.0005",
    },
    "BNBUSDT": {
        "base_currency_code": "BNB",
        "price_precision":    2,
        "size_precision":     2,
        "price_increment":    "0.01",
        "size_increment":     "0.01",
        "min_quantity":       "0.01",
        "max_quantity":       "100000.00",
        "min_notional":       5,
        "max_price":          "99999.99",
        "margin_init":        "0.05",
        "margin_maint":       "0.025",
        "maker_fee":          "0.0002",
        "taker_fee":          "0.0004",
    },
    "XRPUSDT": {
        "base_currency_code": "XRP",
        "price_precision":    4,
        "size_precision":     1,
        "price_increment":    "0.0001",
        "size_increment":     "0.1",
        "min_quantity":       "0.1",
        "max_quantity":       "10000000.0",
        "min_notional":       5,
        "max_price":          "9999.9999",
        "margin_init":        "0.05",
        "margin_maint":       "0.025",
        "maker_fee":          "0.0002",
        "taker_fee":          "0.0004",
    },
    "LINKUSDT": {
        "base_currency_code": "LINK",
        "price_precision":    3,
        "size_precision":     1,
        "price_increment":    "0.001",
        "size_increment":     "0.1",
        "min_quantity":       "0.1",
        "max_quantity":       "1000000.0",
        "min_notional":       5,
        "max_price":          "99999.999",
        "margin_init":        "0.05",
        "margin_maint":       "0.025",
        "maker_fee":          "0.0002",
        "taker_fee":          "0.0004",
    },
    "AVAXUSDT": {
        "base_currency_code": "AVAX",
        "price_precision":    3,
        "size_precision":     1,
        "price_increment":    "0.001",
        "size_increment":     "0.1",
        "min_quantity":       "0.1",
        "max_quantity":       "1000000.0",
        "min_notional":       5,
        "max_price":          "99999.999",
        "margin_init":        "0.05",
        "margin_maint":       "0.025",
        "maker_fee":          "0.0002",
        "taker_fee":          "0.0004",
    },
}

# ── Custom currency registration ──────────────────────────────────────────────
# Nautilus only has built-in constants for BTC, ETH, USDT, etc.
# SOL, BNB, XRP, LINK, AVAX must be registered explicitly.

_REGISTERED: set[str] = set()


def _ensure_currency(code: str) -> Currency:
    """Register a custom crypto currency with Nautilus if not already done."""
    if code not in _REGISTERED:
        try:
            cur = Currency.from_str(code)
        except Exception:
            cur = Currency(
                code=code,
                precision=8,
                iso4217=0,
                name=code,
                currency_type=CurrencyType.CRYPTO,
            )
            Currency.register(cur, overwrite=False)
        _REGISTERED.add(code)
        return Currency.from_str(code)
    return Currency.from_str(code)


# ── Instrument builder ────────────────────────────────────────────────────────

def build_instrument(symbol: str) -> CryptoPerpetual:
    """
    Build a fully configured CryptoPerpetual for the given symbol.

    Args:
        symbol: e.g. "SOLUSDT", "BNBUSDT"

    Returns:
        CryptoPerpetual with correct precision, fees, and margin settings.

    Raises:
        KeyError: if symbol is not in INSTRUMENT_SPECS.
    """
    if symbol not in INSTRUMENT_SPECS:
        raise KeyError(
            f"Unknown symbol '{symbol}'. "
            f"Available: {list(INSTRUMENT_SPECS.keys())}"
        )

    spec = INSTRUMENT_SPECS[symbol]
    base_cur = _ensure_currency(spec["base_currency_code"])

    return CryptoPerpetual(
        instrument_id=InstrumentId(Symbol(f"{symbol}-PERP"), VENUE),
        raw_symbol=Symbol(f"{symbol}-PERP"),
        base_currency=base_cur,
        quote_currency=USDT,
        settlement_currency=USDT,
        is_inverse=False,
        price_precision=spec["price_precision"],
        size_precision=spec["size_precision"],
        price_increment=Price.from_str(spec["price_increment"]),
        size_increment=Quantity.from_str(spec["size_increment"]),
        max_quantity=Quantity.from_str(spec["max_quantity"]),
        min_quantity=Quantity.from_str(spec["min_quantity"]),
        max_notional=None,
        min_notional=Money(spec["min_notional"], USDT),
        max_price=Price.from_str(spec["max_price"]),
        min_price=Price.from_str(spec["price_increment"]),
        margin_init=Decimal(spec["margin_init"]),
        margin_maint=Decimal(spec["margin_maint"]),
        maker_fee=Decimal(spec["maker_fee"]),
        taker_fee=Decimal(spec["taker_fee"]),
        ts_event=0,
        ts_init=0,
    )


def build_all_instruments(symbols: list[str] | None = None) -> list[CryptoPerpetual]:
    """
    Build CryptoPerpetual objects for a list of symbols.

    Args:
        symbols: list of symbol strings. Defaults to all in INSTRUMENT_SPECS.

    Returns:
        List of CryptoPerpetual objects.
    """
    if symbols is None:
        symbols = list(INSTRUMENT_SPECS.keys())
    return [build_instrument(s) for s in symbols]


def get_instrument_id_str(symbol: str) -> str:
    """Return the canonical instrument ID string for Nautilus.

    Example: "SOLUSDT" → "SOLUSDT-PERP.BINANCE"
    """
    return f"{symbol}-PERP.BINANCE"


def get_symbol_from_id(instrument_id_str: str) -> str:
    """Reverse of get_instrument_id_str.

    Example: "SOLUSDT-PERP.BINANCE" → "SOLUSDT"
    """
    return instrument_id_str.split("-PERP.")[0]


def get_price_precision(symbol: str) -> int:
    """Return price precision (decimal places) for a symbol."""
    return INSTRUMENT_SPECS[symbol]["price_precision"]


def get_size_precision(symbol: str) -> int:
    """Return size precision (decimal places) for a symbol."""
    return INSTRUMENT_SPECS[symbol]["size_precision"]
