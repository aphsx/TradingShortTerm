# Real-Time Charting Module - Implementation Guide

## 🎯 Architecture Overview

This implementation creates a high-performance real-time trading chart system with the following architecture:

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│  Binance API    │────────▶│  Go Backend      │────────▶│  Electron/React │
│  (WebSocket)    │         │  (Sidecar)       │         │  (Frontend)     │
└─────────────────┘         └──────────────────┘         └─────────────────┘
                             │                │
                             │  WebSocket     │  REST API
                             │  Kline Stream  │  Historical
                             └────────────────┘
```

### Data Flow:
1. **Backend** connects to Binance WebSocket kline stream (`btcusdt@kline_1m`)
2. **Backend** normalizes data to match Lightweight Charts format
3. **Backend** broadcasts via local WebSocket (`ws://localhost:8080/api/kline`)
4. **Frontend** fetches historical data via REST API on startup
5. **Frontend** connects WebSocket for real-time updates
6. **Frontend** renders chart using TradingView Lightweight Charts

---

## 📂 Backend Implementation (Go)

### 1. Kline WebSocket Streamer (`backend/websocket/kline_stream.go`)

**Purpose**: Connect to Binance kline stream and normalize data.

**Key Features**:
- ✅ Connects to Binance WebSocket API
- ✅ Converts data to Lightweight Charts format
- ✅ Handles reconnection automatically
- ✅ Thread-safe with channels
- ✅ Timestamps in seconds (not milliseconds)

**Critical Data Structure**:
```go
type KlineUpdate struct {
    Symbol string  `json:"symbol"`
    Time   int64   `json:"time"`   // Unix timestamp in SECONDS
    Open   float64 `json:"open"`
    High   float64 `json:"high"`
    Low    float64 `json:"low"`
    Close  float64 `json:"close"`
    Volume float64 `json:"volume"`
}
```

**Why This Structure?**
- Matches Lightweight Charts `CandlestickData` interface exactly
- No transformation needed on frontend
- Efficient JSON serialization
- Time in seconds (Lightweight Charts requirement)

---

### 2. HTTP Server Updates (`backend/server/http_server.go`)

**New Endpoints**:

#### WebSocket Kline Stream
```
ws://localhost:8080/api/kline?symbol=BTCUSDT&interval=1m
```

**Features**:
- ✅ Multi-symbol support (dynamic subscription)
- ✅ Multi-interval support (1m, 5m, 15m, 1h, etc.)
- ✅ Automatic streamer lifecycle management
- ✅ Broadcasts only to subscribed clients
- ✅ Auto-cleanup when no clients connected

#### REST Historical Data
```
GET http://localhost:8080/api/klines?symbol=BTCUSDT&interval=1m&limit=1000
```

**Purpose**: Load initial chart data before connecting WebSocket.

---

### 3. Key Backend Concepts

#### Dynamic Streamer Management
```go
// One streamer per symbol+interval combination
streamKey := fmt.Sprintf("%s_%s", symbol, interval)

// Start streamer only when first client connects
s.ensureKlineStreamerRunning(symbol, interval)

// Stop streamer when last client disconnects
s.checkStopKlineStreamer(symbol, interval)
```

**Benefits**:
- 💰 Efficient resource usage (no idle connections)
- 🚀 Fast startup (streamers created on demand)
- 🧹 Automatic cleanup

---

## 🎨 Frontend Implementation (React + TypeScript)

### 1. Zustand Market Store (`src/renderer/src/store/useMarketStore.ts`)

**Purpose**: Centralized state management for market data and WebSocket.

**State**:
```typescript
interface MarketStore {
  ws: WebSocket | null
  isConnected: boolean
  symbol: string
  interval: string
  candleData: Map<number, CandlestickData>
  latestCandle: KlineData | null
  isLoadingHistory: boolean
}
```

**Key Methods**:

#### `loadHistoricalData()`
```typescript
// 1. Fetch from REST API
const response = await fetch(
  `${BASE_URL}/api/klines?symbol=${symbol}&interval=${interval}&limit=1000`
)

// 2. Convert to Map for efficient updates
const candleMap = new Map<number, CandlestickData>()
klines.forEach((kline) => {
  candleMap.set(kline.time, { time, open, high, low, close })
})

// 3. Store in state
set({ candleData: candleMap })
```

#### `connectWebSocket()`
```typescript
const ws = new WebSocket(`${WS_URL}/api/kline?symbol=${symbol}&interval=${interval}`)

ws.onmessage = (event) => {
  const kline: KlineData = JSON.parse(event.data)
  updateCandle(kline) // Update or add candle
}
```

#### `updateCandle()`
```typescript
// Update existing candle or add new one
const newCandleData = new Map(candleData)
newCandleData.set(kline.time, {
  time: kline.time,
  open: kline.open,
  high: kline.high,
  low: kline.low,
  close: kline.close
})
set({ candleData: newCandleData })
```

**Why Map Instead of Array?**
- ✅ O(1) lookup and update by timestamp
- ✅ Prevents duplicate candles
- ✅ Easy to update real-time data
- ✅ Convert to array when needed for chart

---

### 2. Candlestick Chart Component (`src/renderer/src/components/CandlestickChart.tsx`)

**Purpose**: Pure chart rendering component with TradingView styling.

**Initialization**:
```typescript
const chart = createChart(container, {
  layout: {
    background: { type: ColorType.Solid, color: '#131722' }, // TradingView dark
    textColor: '#d1d4dc'
  },
  grid: {
    vertLines: { color: '#1f2937' },  // Subtle grey
    horzLines: { color: '#1f2937' }
  },
  crosshair: {
    mode: CrosshairMode.Normal,
    vertLine: {
      labelBackgroundColor: '#2962FF' // TradingView blue
    }
  },
  timeScale: {
    rightOffset: 12, // Space on right (TradingView style)
    borderVisible: false
  }
})
```

**Exact TradingView Colors**:
```typescript
const candlestickSeries = chart.addCandlestickSeries({
  upColor: '#089981',      // Teal green (bullish)
  downColor: '#f23645',    // Red (bearish)
  borderUpColor: '#089981',
  borderDownColor: '#f23645',
  wickUpColor: '#089981',
  wickDownColor: '#f23645'
})
```

**ResizeObserver for Responsive Chart**:
```typescript
const resizeObserver = new ResizeObserver((entries) => {
  const { width, height } = entries[0].contentRect
  chart.applyOptions({ width, height })
})
resizeObserver.observe(container)
```

**Why ResizeObserver?**
- ✅ Automatically handles window resize
- ✅ Works with flexbox/grid layouts
- ✅ No manual event listeners needed
- ✅ Prevents chart distortion

---

### 3. Data Loading Flow

```typescript
useEffect(() => {
  // 1. Load historical data first
  loadHistoricalData().then(() => {
    // 2. Then connect WebSocket
    connectWebSocket()
  })
}, [symbol, interval])

useEffect(() => {
  // 3. Update chart when data changes
  if (candleData.size === 0) return
  
  const candles = getCandleArray() // Convert Map to sorted Array
  candlestickSeries.setData(candles) // Set all data at once
  
  chart.timeScale().fitContent() // Auto-fit view
}, [candleData])
```

**Why This Order?**
1. **Historical First**: Provides context and initial view
2. **WebSocket Second**: Adds real-time updates
3. **Batch Updates**: More efficient than individual updates

---

## 🎨 TradingView Theme Colors

### Background Colors
```css
--bg-main: #131722        /* Main background */
--bg-panel: #1e222d       /* Panel/header background */
--bg-hover: #2a2e39       /* Hover state */
```

### Text Colors
```css
--text-primary: #d1d4dc   /* Primary text */
--text-secondary: #758696 /* Secondary/muted text */
```

### Grid & Borders
```css
--grid-line: #1f2937      /* Grid lines (subtle) */
--border: #2b2b43         /* Panel borders */
```

### Accent Colors
```css
--accent-blue: #2962FF    /* TradingView blue (crosshair, buttons) */
--green-up: #089981       /* Bullish candles (teal) */
--red-down: #f23645       /* Bearish candles */
```

### Tailwind Classes
```jsx
<div className="bg-[#131722]">          {/* Main background */}
<div className="bg-[#1e222d]">          {/* Panel background */}
<div className="text-[#d1d4dc]">        {/* Primary text */}
<div className="text-[#758696]">        {/* Muted text */}
<div className="border-[#2b2b43]">      {/* Border */}
<Button className="bg-[#2962FF]">       {/* Active button */}
<span className="text-[#089981]">       {/* Bullish price */}
<span className="text-[#f23645]">       {/* Bearish price */}
```

---

## 🚀 Usage Example

### Basic Usage
```tsx
import { CandlestickChart } from './components/CandlestickChart'

function App() {
  return (
    <CandlestickChart 
      symbol="BTCUSDT" 
      interval="1m" 
      className="w-full h-screen"
    />
  )
}
```

### Advanced Usage with Controls
```tsx
import { AdvancedTradingChart } from './components/AdvancedTradingChart'

function App() {
  return (
    <div className="w-full h-screen bg-[#131722]">
      <AdvancedTradingChart />
    </div>
  )
}
```

**Features**:
- ✅ Symbol selector dropdown
- ✅ Timeframe buttons (1m, 5m, 15m, etc.)
- ✅ Current price display
- ✅ 24h high/low/volume stats
- ✅ Connection status indicator
- ✅ Loading states
- ✅ Auto-reconnection

---

## ⚡ Performance Optimizations

### 1. Efficient Data Structure
```typescript
// ❌ Bad: Array (O(n) search, duplicates possible)
const candles: CandlestickData[] = []

// ✅ Good: Map (O(1) lookup, no duplicates)
const candleData: Map<number, CandlestickData> = new Map()
```

### 2. Batch Updates
```typescript
// ❌ Bad: Update one by one
candles.forEach(candle => series.update(candle))

// ✅ Good: Set all data at once
series.setData(candles)
```

### 3. WebSocket Buffering
```go
// Backend: Buffer channel to prevent blocking
updateChan: make(chan KlineUpdate, 100)
```

### 4. Conditional Rendering
```typescript
// Only render chart when data is ready
if (candleData.size === 0) return

// Skip update if no change
if (state.symbol === symbol) return
```

---

## 🔧 Configuration Options

### Backend Configuration
```go
// In backend/config/config.go
type Config struct {
    BinanceAPIKey    string
    BinanceSecretKey string
    UseTestnet       bool
    ServerPort       string // Default: "8080"
}
```

### Frontend Configuration
```typescript
// In src/renderer/src/store/useMarketStore.ts
const BASE_URL = 'http://localhost:8080'
const WS_URL = 'ws://localhost:8080'
```

### Chart Options
```typescript
// Adjust precision based on asset
priceFormat: {
  type: 'price',
  precision: 2,      // For BTC/USD
  minMove: 0.01
}

// For cryptocurrencies with more decimals
priceFormat: {
  type: 'price',
  precision: 8,      // For BTC satoshis
  minMove: 0.00000001
}
```

---

## 🐛 Troubleshooting

### Issue: Chart Not Updating
**Check**:
1. Backend is running: `http://localhost:8080/api/health`
2. WebSocket connected: Check browser console for "✅ WebSocket connected"
3. Data is flowing: Network tab → WS → Messages

### Issue: Wrong Timezone
**Solution**: Lightweight Charts automatically converts Unix timestamps to local time.
```typescript
// Backend sends: 1706830800 (UTC timestamp)
// Chart shows: Local time based on browser timezone
```

### Issue: Chart Distorted on Resize
**Solution**: Ensure ResizeObserver is working:
```typescript
// Check if resizeObserver is properly observing
console.log('ResizeObserver active:', !!resizeObserverRef.current)
```

### Issue: Duplicate Candles
**Solution**: Using Map prevents this automatically:
```typescript
// Map key is timestamp, so duplicates overwrite
candleMap.set(kline.time, candleData)
```

---

## 📊 Supported Intervals

Binance supports these kline intervals:
```
1m, 3m, 5m, 15m, 30m
1h, 2h, 4h, 6h, 8h, 12h
1d, 3d
1w
1M
```

**Usage**:
```typescript
<CandlestickChart symbol="BTCUSDT" interval="15m" />
```

---

## 🎓 Best Practices

### 1. Always Load History First
```typescript
// ✅ Good: History → WebSocket
loadHistoricalData().then(() => connectWebSocket())

// ❌ Bad: WebSocket only (no context)
connectWebSocket()
```

### 2. Handle Disconnections Gracefully
```typescript
ws.onclose = () => {
  console.log('Disconnected')
  // Auto-reconnect after 5 seconds
  setTimeout(() => connectWebSocket(), 5000)
}
```

### 3. Cleanup Resources
```typescript
useEffect(() => {
  connectWebSocket()
  
  return () => {
    disconnectWebSocket() // Cleanup on unmount
  }
}, [symbol])
```

### 4. Use Proper TypeScript Types
```typescript
// Import types from library
import type { CandlestickData, IChartApi } from 'lightweight-charts'

// Define your own types
interface KlineData {
  symbol: string
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}
```

---

## 🚀 Next Steps

### Enhancements You Can Add:

1. **Volume Histogram**
```typescript
const volumeSeries = chart.addHistogramSeries({
  color: '#26a69a',
  priceFormat: { type: 'volume' },
  priceScaleId: ''
})
volumeSeries.priceScale().applyOptions({
  scaleMargins: { top: 0.8, bottom: 0 }
})
```

2. **Technical Indicators**
- Moving Averages (SMA, EMA)
- Bollinger Bands
- RSI, MACD

3. **Drawing Tools**
- Trend lines
- Fibonacci retracement
- Support/resistance levels

4. **Multi-Chart Layout**
- Split screen with multiple symbols
- Synchronized crosshair
- Layout persistence

5. **Order Placement**
- Click-to-trade on chart
- Visual stop-loss/take-profit
- Order history overlay

---

## 📝 License

This implementation guide is part of the 24HrT trading application.

---

## 🙏 Credits

- **TradingView Lightweight Charts**: https://www.tradingview.com/lightweight-charts/
- **Binance API**: https://binance-docs.github.io/apidocs/
- **go-binance**: https://github.com/adshao/go-binance

---

**Happy Trading! 📈🚀**
