"""
analytics.py — Post-Backtest Analytics and Reporting
======================================================
Generates after engine.run() completes:
  1. orders.csv          — all orders (entry + exit)
  2. positions.csv       — position lifecycle (open → close)
  3. account.csv         — account balance snapshots
  4. per_instrument.csv  — per-symbol performance table
  5. equity_curve.png    — cumulative realized PnL over time
  6. drawdown.png        — drawdown from peak equity
  7. summary.json        — machine-readable key metrics

Usage:
    from analytics import BacktestAnalytics
    analytics = BacktestAnalytics(engine, Path("reports"))
    analytics.generate_all()
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")          # non-interactive backend (no display needed)
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.model.identifiers import Venue


# ═══════════════════════════════════════════════════════════════════════════════
# BacktestAnalytics
# ═══════════════════════════════════════════════════════════════════════════════

class BacktestAnalytics:
    """
    Post-backtest analytics for a completed BacktestEngine run.

    Args:
        engine      : the BacktestEngine after engine.run()
        reports_dir : directory where all output files are written
    """

    def __init__(self, engine: BacktestEngine, reports_dir: Path):
        self.engine      = engine
        self.reports_dir = reports_dir
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        self._orders_df:    Optional[object] = None
        self._positions_df: Optional[object] = None
        self._account_df:   Optional[object] = None

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────

    def generate_all(self) -> None:
        """Run all analytics and save all output files."""
        if not _PANDAS_OK:
            print("  [WARN] pandas/matplotlib not installed — skipping analytics")
            self._save_reports_raw()
            return

        self._orders_df    = self._save_orders_report()
        self._positions_df = self._save_positions_report()
        self._account_df   = self._save_account_report()

        if self._positions_df is not None and len(self._positions_df) > 0:
            self._equity_curve()
            self._drawdown_analysis()
            self._per_instrument_summary()
            self._risk_metrics()
            self._print_console_summary()
        else:
            print("  [INFO] No closed positions — analytics skipped")

        self._save_summary_json()

    # ─────────────────────────────────────────────────────────────────────────
    # Report savers
    # ─────────────────────────────────────────────────────────────────────────

    def _save_orders_report(self):
        try:
            df = self.engine.trader.generate_orders_report()
            if df is not None and len(df) > 0:
                path = self.reports_dir / f"{self.ts}_orders.csv"
                df.to_csv(path, index=True)
                print(f"  [Saved] {path.name}  ({len(df)} orders)")
                return df
        except Exception as e:
            print(f"  [WARN] orders report: {e}")
        return None

    def _save_positions_report(self):
        try:
            df = self.engine.trader.generate_positions_report()
            if df is not None and len(df) > 0:
                path = self.reports_dir / f"{self.ts}_positions.csv"
                df.to_csv(path, index=True)
                print(f"  [Saved] {path.name}  ({len(df)} positions)")
                return df
        except Exception as e:
            print(f"  [WARN] positions report: {e}")
        return None

    def _save_account_report(self):
        try:
            df = self.engine.trader.generate_account_report(Venue("BINANCE"))
            if df is not None and len(df) > 0:
                path = self.reports_dir / f"{self.ts}_account.csv"
                df.to_csv(path, index=True)
                print(f"  [Saved] {path.name}")
                return df
        except Exception as e:
            print(f"  [WARN] account report: {e}")
        return None

    def _save_reports_raw(self) -> None:
        """Minimal report saving when pandas is not available."""
        self._save_orders_report()
        self._save_positions_report()
        self._save_account_report()

    # ─────────────────────────────────────────────────────────────────────────
    # Equity Curve
    # ─────────────────────────────────────────────────────────────────────────

    def _equity_curve(self) -> None:
        """Plot cumulative realized PnL across all closed positions."""
        df  = self._positions_df
        pnl = self._extract_pnl_series(df)
        if pnl is None or len(pnl) == 0:
            return

        cum_pnl  = pnl.cumsum()
        peak     = cum_pnl.cummax()

        fig, ax = plt.subplots(figsize=(14, 6))
        ax.plot(cum_pnl.values, linewidth=1.4, color="#2196F3", label="Cumulative PnL")
        ax.plot(peak.values, linewidth=0.8, color="#4CAF50", linestyle="--",
                alpha=0.7, label="Peak Equity")
        ax.fill_between(
            range(len(cum_pnl)),
            cum_pnl.values,
            0,
            where=(cum_pnl.values >= 0),
            alpha=0.15,
            color="#4CAF50",
        )
        ax.fill_between(
            range(len(cum_pnl)),
            cum_pnl.values,
            0,
            where=(cum_pnl.values < 0),
            alpha=0.15,
            color="#F44336",
        )
        ax.axhline(y=0, color="#888888", linestyle="-", linewidth=0.8, alpha=0.6)
        ax.set_title("Portfolio Equity Curve — Cumulative Realized PnL", fontsize=14)
        ax.set_xlabel("Trade #")
        ax.set_ylabel("Cumulative PnL (USDT)")
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
        ax.legend()
        ax.grid(True, alpha=0.25)
        fig.tight_layout()

        path = self.reports_dir / f"{self.ts}_equity_curve.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        print(f"  [Saved] {path.name}")

    # ─────────────────────────────────────────────────────────────────────────
    # Drawdown Analysis
    # ─────────────────────────────────────────────────────────────────────────

    def _drawdown_analysis(self) -> None:
        """Plot drawdown from peak equity for all closed positions."""
        import pandas as pd
        df  = self._positions_df
        pnl = self._extract_pnl_series(df)
        if pnl is None or len(pnl) == 0:
            return

        cum_pnl  = pnl.cumsum()
        peak     = cum_pnl.cummax()
        drawdown = cum_pnl - peak
        max_dd   = drawdown.min()
        max_dd_i = drawdown.idxmin()

        fig, ax = plt.subplots(figsize=(14, 4))
        ax.fill_between(range(len(drawdown)), drawdown.values, 0,
                        alpha=0.5, color="#F44336", label="Drawdown")
        ax.axhline(y=max_dd, color="#B71C1C", linestyle="--", linewidth=1.0,
                   label=f"Max DD: {max_dd:.2f} USDT")
        ax.axvline(x=int(max_dd_i), color="#FF9800", linestyle=":",
                   linewidth=1.0, alpha=0.8)
        ax.set_title("Drawdown from Peak Equity", fontsize=14)
        ax.set_xlabel("Trade #")
        ax.set_ylabel("Drawdown (USDT)")
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
        ax.legend()
        ax.grid(True, alpha=0.25)
        fig.tight_layout()

        path = self.reports_dir / f"{self.ts}_drawdown.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        print(f"  [Saved] {path.name}")

    # ─────────────────────────────────────────────────────────────────────────
    # Per-Instrument Summary
    # ─────────────────────────────────────────────────────────────────────────

    def _per_instrument_summary(self) -> None:
        """Build per-symbol performance table and save to CSV."""
        import pandas as pd
        df  = self._positions_df
        pnl = self._extract_pnl_series(df)
        if pnl is None:
            return

        # Try to get instrument column
        iid_col = self._find_column(df, ["instrument_id", "symbol", "instrument"])
        if iid_col is None:
            return

        df_work = df.copy()
        df_work["_pnl"] = pnl.values

        summary_rows = []
        for sym, grp in df_work.groupby(iid_col):
            p          = grp["_pnl"].astype(float)
            total      = len(p)
            wins       = int((p > 0).sum())
            losses     = int((p <= 0).sum())
            win_rate   = wins / total * 100 if total > 0 else 0.0
            gross_win  = float(p[p > 0].sum()) if (p > 0).any() else 0.0
            gross_loss = float(p[p <= 0].sum()) if (p <= 0).any() else 0.0
            pf         = (
                gross_win / abs(gross_loss)
                if gross_loss != 0 else float("inf")
            )
            summary_rows.append({
                "symbol":      str(sym).split("-PERP")[0],
                "total_trades": total,
                "wins":         wins,
                "losses":       losses,
                "win_rate_%":   round(win_rate, 1),
                "total_pnl":    round(float(p.sum()), 4),
                "avg_pnl":      round(float(p.mean()), 4),
                "max_win":      round(float(p.max()), 4),
                "max_loss":     round(float(p.min()), 4),
                "profit_factor": round(pf, 3),
            })

        if not summary_rows:
            return

        summary_df = pd.DataFrame(summary_rows)
        path       = self.reports_dir / f"{self.ts}_per_instrument.csv"
        summary_df.to_csv(path, index=False)
        print(f"  [Saved] {path.name}")

        # Console table
        print(f"\n  {'─'*75}")
        print(f"  Per-Instrument Summary")
        print(f"  {'─'*75}")
        header = (
            f"  {'Symbol':<10} {'Trades':>6} {'W':>4} {'L':>4} "
            f"{'WR%':>6} {'PnL':>10} {'AvgPnL':>9} {'MaxWin':>9} {'MaxLoss':>9} {'PF':>6}"
        )
        print(header)
        print(f"  {'─'*75}")
        for row in summary_rows:
            print(
                f"  {row['symbol']:<10} {row['total_trades']:>6} "
                f"{row['wins']:>4} {row['losses']:>4} "
                f"{row['win_rate_%']:>5.1f}% "
                f"{row['total_pnl']:>10.2f} "
                f"{row['avg_pnl']:>9.4f} "
                f"{row['max_win']:>9.2f} "
                f"{row['max_loss']:>9.2f} "
                f"{row['profit_factor']:>6.3f}"
            )
        print(f"  {'─'*75}")

    # ─────────────────────────────────────────────────────────────────────────
    # Risk Metrics
    # ─────────────────────────────────────────────────────────────────────────

    def _risk_metrics(self) -> dict:
        """Compute portfolio-level risk metrics."""
        df  = self._positions_df
        pnl = self._extract_pnl_series(df)
        if pnl is None or len(pnl) < 2:
            return {}

        arr      = pnl.values.astype(float)
        cum_pnl  = np.cumsum(arr)
        peak     = np.maximum.accumulate(cum_pnl)
        drawdown = cum_pnl - peak

        total      = len(arr)
        wins       = int((arr > 0).sum())
        gross_win  = float(arr[arr > 0].sum()) if (arr > 0).any() else 0.0
        gross_loss = float(arr[arr <= 0].sum()) if (arr <= 0).any() else 0.0
        mean_ret   = float(arr.mean())
        std_ret    = float(arr.std()) if len(arr) > 1 else 1e-9
        neg_std    = float(arr[arr < 0].std()) if (arr < 0).any() else 1e-9
        max_dd     = float(drawdown.min())
        total_pnl  = float(arr.sum())
        pf         = gross_win / abs(gross_loss) if gross_loss != 0 else float("inf")

        # Approximate annualized (assume ~50 trades per trading day)
        sharpe  = (mean_ret / std_ret) * np.sqrt(total) if std_ret > 0 else 0.0
        sortino = (mean_ret / neg_std) * np.sqrt(total) if neg_std > 0 else 0.0
        calmar  = total_pnl / abs(max_dd) if max_dd < 0 else float("inf")
        expectancy = (
            (wins / total * (gross_win / wins if wins > 0 else 0))
            - ((total - wins) / total * (abs(gross_loss) / (total - wins) if (total - wins) > 0 else 0))
        )

        # Find max consecutive wins/losses
        max_consec_w, max_consec_l = self._max_consecutive(arr)

        self._metrics_cache = {
            "total_trades":         total,
            "total_pnl":            round(total_pnl, 4),
            "win_rate_%":           round(wins / total * 100, 2),
            "profit_factor":        round(pf, 4),
            "sharpe_ratio":         round(sharpe, 4),
            "sortino_ratio":        round(sortino, 4),
            "calmar_ratio":         round(calmar, 4),
            "expectancy_per_trade": round(expectancy, 4),
            "max_drawdown_usdt":    round(max_dd, 4),
            "gross_profit":         round(gross_win, 4),
            "gross_loss":           round(gross_loss, 4),
            "max_consecutive_wins":   max_consec_w,
            "max_consecutive_losses": max_consec_l,
        }
        return self._metrics_cache

    # ─────────────────────────────────────────────────────────────────────────
    # Console Summary
    # ─────────────────────────────────────────────────────────────────────────

    def _print_console_summary(self) -> None:
        """Print formatted results table to stdout."""
        m = getattr(self, "_metrics_cache", None)
        if m is None:
            m = self._risk_metrics()
        if not m:
            return

        df  = self._positions_df
        pnl = self._extract_pnl_series(df)
        start_bal = 0.0
        end_bal   = 0.0
        if self._account_df is not None and len(self._account_df) > 0:
            try:
                total_col  = self._find_column(self._account_df, ["total", "balance"])
                if total_col:
                    vals      = self._account_df[total_col].astype(float)
                    start_bal = float(vals.iloc[0])
                    end_bal   = float(vals.iloc[-1])
            except Exception:
                pass

        pct_return = ((end_bal - start_bal) / start_bal * 100
                      if start_bal > 0 else 0.0)

        print(f"\n  {'═'*65}")
        print(f"  {'BACKTEST RESULTS':^65}")
        print(f"  {'═'*65}")
        if start_bal > 0:
            sign = "+" if end_bal >= start_bal else ""
            print(f"  Balance     : {start_bal:,.2f} → {end_bal:,.2f} USDT"
                  f"  ({sign}{pct_return:.2f}%)")
        print(f"  Total PnL   : {m['total_pnl']:+.4f} USDT")
        print(f"  Trades      : {m['total_trades']}"
              f"  (W:{int(m['total_trades'] * m['win_rate_%'] / 100)}"
              f"  L:{m['total_trades'] - int(m['total_trades'] * m['win_rate_%'] / 100)})")
        print(f"  Win Rate    : {m['win_rate_%']:.1f}%")
        print(f"  Profit Factor: {m['profit_factor']:.3f}")
        print(f"  Expectancy  : {m['expectancy_per_trade']:+.4f} USDT/trade")
        print(f"  ─── Risk Metrics ───────────────────────────────────────")
        print(f"  Sharpe Ratio : {m['sharpe_ratio']:.4f}")
        print(f"  Sortino Ratio: {m['sortino_ratio']:.4f}")
        print(f"  Calmar Ratio : {m['calmar_ratio']:.4f}")
        print(f"  Max Drawdown : {m['max_drawdown_usdt']:.4f} USDT")
        print(f"  ─── Streaks ─────────────────────────────────────────────")
        print(f"  Max Consec Wins  : {m['max_consecutive_wins']}")
        print(f"  Max Consec Losses: {m['max_consecutive_losses']}")
        print(f"  {'═'*65}")

    # ─────────────────────────────────────────────────────────────────────────
    # Summary JSON
    # ─────────────────────────────────────────────────────────────────────────

    def _save_summary_json(self) -> None:
        """Save machine-readable metrics to JSON."""
        m = getattr(self, "_metrics_cache", {})
        output = {
            "timestamp":  self.ts,
            "report_dir": str(self.reports_dir),
            "metrics":    m,
        }
        path = self.reports_dir / f"{self.ts}_summary.json"
        with open(path, "w") as f:
            json.dump(output, f, indent=2)
        print(f"  [Saved] {path.name}")

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _extract_pnl_series(self, df):
        """Extract realized PnL series from positions DataFrame."""
        if df is None or len(df) == 0:
            return None
        # Nautilus may use different column names across versions
        col = self._find_column(df, [
            "realized_pnl", "realized_return", "pnl",
            "realized_pnl_currency", "return"
        ])
        if col is None:
            return None
        try:
            return df[col].astype(float)
        except Exception:
            return None

    def _find_column(self, df, candidates: list[str]):
        """Return the first candidate column name that exists in df."""
        if df is None:
            return None
        for col in candidates:
            if col in df.columns:
                return col
        # Case-insensitive fallback
        lower_cols = {c.lower(): c for c in df.columns}
        for col in candidates:
            if col.lower() in lower_cols:
                return lower_cols[col.lower()]
        return None

    @staticmethod
    def _max_consecutive(arr: np.ndarray) -> tuple[int, int]:
        """Return (max_consecutive_wins, max_consecutive_losses)."""
        max_w = max_l = cur_w = cur_l = 0
        for v in arr:
            if v > 0:
                cur_w += 1
                cur_l = 0
                max_w = max(max_w, cur_w)
            else:
                cur_l += 1
                cur_w = 0
                max_l = max(max_l, cur_l)
        return max_w, max_l
