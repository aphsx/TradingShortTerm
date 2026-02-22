# TECHNICAL DOCUMENTATION: VORTEX-7 Engine 🧠
## Detailed System Breakdown & Logic Implementation

This document provides a deep dive into the internal workings of the VORTEX-7 trading engine, covering the mathematical formulas, engine logic, and the core decision-making pipeline.

---

## 1. The Multi-Engine Architecture (5-Engine System)

VORTEX-7 uses a modular approach where specific types of market data are processed by isolated engines. Each engine outputs a normalized signal (direction + strength).

### E1: Order Flow Engine (Weight: 35%)
Focuses on the **Orderbook** (Level 2 data) to detect immediate supply and demand imbalances.
- **Imbalance Calculation**: 
  $$\text{Imbalance} = \frac{\sum \text{Bid Volume} - \sum \text{Ask Volume}}{\sum \text{Bid Volume} + \sum \text{Ask Volume}}$$
- **Micro-price**: Calculates the "Fair Value" of the asset by weighting the mid-price by the volume at the best bid and ask.
  $$\text{Micro Price} = \frac{\text{Best Bid Price} \times \text{Ask Qty} + \text{Best Ask Price} \times \text{Bid Qty}}{\text{Bid Qty} + \text{Ask Qty}}$$
- **Strategy Influence**: Primarily used for spotting early breakouts before they appear on candles.

### E2: Tick Engine (Weight: 25%)
Processes every single trade (**aggTrade**) to understand current market momentum.
- **Aggressor Ratio**: Measures the percentage of "Taker" buys vs. sells.
  $$\text{Aggressor Ratio} = \frac{\text{Buy Volume}}{\text{Buy Volume} + \text{Sell Volume}}$$
- **Velocity**: Tracks the rate of trades per second. High velocity often precedes a price expansion.

### E3: Technical Engine (Weight: 20%)
Traditional indicator analysis acting as a "Reality Check" for momentum.
- **RSI (Relative Strength Index)**: Identifies overbought (>70) or oversold (<30) conditions.
- **Bollinger Bands**: Detects price extensions and potential mean reversion zones.
- **ATR (Average True Range)**: Feeds volatility data directly into the Risk Manager for dynamic SL/TP placement.

### E4: Sentiment Engine (Weight: 12%)
Uses aggregate market data to gauge crowd positioning and smart money activity.
- **Long/Short Ratio (Contrarian)**: If the crowd (>70%) is Long, the engine applies a Short bias (anticipating a long-squeeze).
- **Funding Rate**: Monitors the cost of holding positions. Expensive funding (>0.01%) suggests an overcrowded side.
- **Smart Money Tracking**: Compares Top Trader ratios vs. Global ratios to spot institutional vs. retail divergence.

### E5: Regime Filter (Weight: 8% + Global Switch)
The "Brain" that decides if the market is tradeable and adjusts the behavior of all other engines.
- **Volatility Phases**: Categorizes market into `LOW`, `NORMAL`, `HIGH`, or `EXTREME`.
- **Dynamic Weighting**: 
  - **Trending Market**: Increases weight for E1 and E2 (Momentum focused).
  - **Ranging Market**: Increases weight for E3 (Oscillator focused).
- **Safety Switch**: Blocks trading during `EXTREME_VOL` or high-spread conditions.

---

## 2. Core Decision Pipeline

The pipeline flows from raw data to order execution in under **10ms**.

### Step 1: Weighted Scoring
The `DecisionEngine` calculates a final score:
$$\text{Final Score} = (s1 \times w1) + (s2 \times w2) + (s3 \times w3) + (s4 \times w4)$$
Where $s$ is the signal strength (-1.0 to 1.0) and $w$ is the dynamic weight from E5.

### Step 2: Strategy Match
The system evaluates three distinct strategies:
- **Strategy A (Momentum/Breakout)**: High E1/E2 conviction. Uses extremely tight Stop-Loss.
- **Strategy B (Mean Reversion)**: High E3 conviction in Ranging markets. Uses wider targets.
- **Strategy C (Liquidity Fishing)**: Reacts to high Sentiment (E4) and potential liquidation clusters.

### Step 3: Risk Normalization
The `RiskManager` performs critical safety checks:
1.  **Fee/Slippage Test**: If the TP target is smaller than the round-trip fee + expected slippage, the trade is rejected.
2.  **R:R Floor**: Rejects trades with a Reward-to-Risk ratio below the configured minimum (default 0.8 for high-win rate scalping).
3.  **Leverage Clamping**: Dynamically sets leverage between **10x** and **30x** based on the required position size and available margin.
4.  **Liquidation Prevention**: Automatically "squeezes" the SL and TP if the leverage is so high that the maintenance margin would be hit before the Stop-Loss price.

---

## 3. Data Infrastructure

- **Redis**: Acts as a "Hot Store" for:
  - Real-time Orderbooks.
  - Tick History Ring Buffers.
  - Candle Cache (1m and 15m timeframes).
- **Supabase (PostgreSQL)**:
  - Stores every execution with high granularity (Latency, Slippage, Strategy used, Error types).
  - Used for back-office performance reporting and strategy refinement.

---

## 4. Setup & Deployment Recommendations

- **Server Location**: Use AWS or Vultr in **Singapore (ap-southeast-1)** to minimize network latency to Binance's matching engine.
- **Environment**: Use **Docker** to ensure consistent runtime environments for Redis and the Python engine.
- **Monitoring**: It is recommended to use the integrated Telegram bot functionality (if configured) to receive real-time "Heartbeats" and Emergency Stop controls.

---
*VORTEX-7 Technical Manual | Confidential Support Document*
