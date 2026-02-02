# 🚀 Quick Start Guide - Real-Time Charting Module

## Step 1: Start the Backend

```powershell
cd backend
go run main.go
```

**Expected Output:**
```
✅ Backend is running!
📊 Dynamic multi-symbol streaming enabled
🌐 HTTP Server: http://localhost:8080
🔌 WebSocket Price: ws://localhost:8080/api/price?symbol=BTCUSDT
🕯️  WebSocket Klines: ws://localhost:8080/api/kline?symbol=BTCUSDT&interval=1m
📈 REST Klines: http://localhost:8080/api/klines?symbol=BTCUSDT&interval=1m&limit=500
💡 Streamers start automatically when clients connect
Press Ctrl+C to stop
```

## Step 2: Test Backend Endpoints

### Test REST API (Historical Data)
```powershell
# PowerShell
Invoke-RestMethod -Uri "http://localhost:8080/api/klines?symbol=BTCUSDT&interval=1m&limit=10"
```

### Test WebSocket (Real-time Data)
Open your browser's Developer Console and run:
```javascript
const ws = new WebSocket('ws://localhost:8080/api/kline?symbol=BTCUSDT&interval=1m')
ws.onmessage = (event) => console.log(JSON.parse(event.data))
```

**Expected Output:**
```json
{
  "symbol": "BTCUSDT",
  "time": 1706830800,
  "open": 43250.50,
  "high": 43280.00,
  "low": 43240.25,
  "close": 43265.75,
  "volume": 123.45
}
```

## Step 3: Start the Frontend

```powershell
cd ..
npm run dev
```

## Step 4: Integrate into Your App

### Option A: Quick Test (Replace App.tsx)

```tsx
// src/renderer/src/App.tsx
import { AdvancedTradingChart } from './components/AdvancedTradingChart'

export function App() {
  return (
    <div className="w-full h-screen bg-[#131722]">
      <AdvancedTradingChart />
    </div>
  )
}
```

### Option B: Add to Existing Layout

```tsx
// src/renderer/src/App.tsx
import { CandlestickChart } from './components/CandlestickChart'
// ... your other imports

export function App() {
  return (
    <div className="flex h-screen">
      <div className="flex-1">
        {/* Your new chart */}
        <CandlestickChart symbol="BTCUSDT" interval="1m" className="w-full h-full" />
      </div>
      <div className="w-96">
        {/* Your existing order panel */}
        <OrderPanel />
      </div>
    </div>
  )
}
```

## Step 5: Verify It's Working

✅ **Backend Console** should show:
```
🚀 Started Kline WebSocket stream for BTCUSDT (1m)
🔌 New Kline WebSocket client connected for BTCUSDT 1m (Total: 1)
🕯️  BTCUSDT 1m - Close: 43265.75 | O: 43250.50 H: 43280.00 L: 43240.25 | Vol: 123.45
```

✅ **Browser Console** should show:
```
📊 Fetching historical klines for BTCUSDT 1m...
✅ Loaded 1000 historical candles
🔌 Connecting to WebSocket: ws://localhost:8080/api/kline?symbol=BTCUSDT&interval=1m
✅ WebSocket connected
📊 Updating chart with 1000 candles
```

✅ **Chart** should display:
- Dark TradingView-style background (#131722)
- Green/red candlesticks
- Smooth real-time updates
- Symbol selector dropdown
- Timeframe buttons
- Current price display
- Connection status indicator

## 🎯 Key Files Created

### Backend (Go)
- ✅ `backend/websocket/kline_stream.go` - Binance WebSocket connector
- ✅ `backend/server/http_server.go` - Updated with kline endpoints
- ✅ `backend/main.go` - Updated with new endpoints info

### Frontend (React/TypeScript)
- ✅ `src/renderer/src/store/useMarketStore.ts` - Zustand state management
- ✅ `src/renderer/src/components/CandlestickChart.tsx` - Pure chart component
- ✅ `src/renderer/src/components/AdvancedTradingChart.tsx` - Full UI with controls

### Documentation
- ✅ `CHARTING_MODULE_GUIDE.md` - Comprehensive implementation guide
- ✅ `APP_INTEGRATION_EXAMPLES.tsx` - Integration examples
- ✅ `QUICK_START.md` - This file

## 🐛 Troubleshooting

### Backend Not Starting
```powershell
# Reinstall dependencies
cd backend
go mod tidy
go mod download
```

### WebSocket Connection Failed
1. Check backend is running: `http://localhost:8080/api/health`
2. Check firewall settings
3. Verify port 8080 is not in use: `netstat -an | findstr 8080`

### Chart Not Rendering
1. Open browser DevTools (F12)
2. Check Console for errors
3. Check Network tab → WS for WebSocket connection
4. Verify Lightweight Charts is installed: `npm list lightweight-charts`

### Wrong Colors/Styling
Make sure your Tailwind config includes the custom colors:
```javascript
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        // These are included by default in the chart component
      }
    }
  }
}
```

## 🎨 Customization Examples

### Change Symbol
```tsx
<CandlestickChart symbol="ETHUSDT" interval="5m" />
```

### Change Colors
```typescript
// In CandlestickChart.tsx
const candlestickSeries = chart.addCandlestickSeries({
  upColor: '#00ff00',      // Your custom green
  downColor: '#ff0000',    // Your custom red
  borderUpColor: '#00ff00',
  borderDownColor: '#ff0000',
  wickUpColor: '#00ff00',
  wickDownColor: '#ff0000'
})
```

### Add Multiple Charts
```tsx
<div className="grid grid-cols-2 gap-4 h-screen p-4 bg-[#131722]">
  <CandlestickChart symbol="BTCUSDT" interval="1m" />
  <CandlestickChart symbol="ETHUSDT" interval="1m" />
  <CandlestickChart symbol="BNBUSDT" interval="5m" />
  <CandlestickChart symbol="SOLUSDT" interval="5m" />
</div>
```

## 📊 Testing Different Intervals

```tsx
// 1 minute (high frequency)
<CandlestickChart symbol="BTCUSDT" interval="1m" />

// 15 minutes (balanced)
<CandlestickChart symbol="BTCUSDT" interval="15m" />

// 1 hour (trend analysis)
<CandlestickChart symbol="BTCUSDT" interval="1h" />

// 1 day (long-term)
<CandlestickChart symbol="BTCUSDT" interval="1d" />
```

## 🚀 Performance Tips

1. **Limit historical data on slow connections**:
```typescript
// In useMarketStore.ts
const response = await fetch(
  `${BASE_URL}/api/klines?symbol=${symbol}&interval=${interval}&limit=500` // Reduced from 1000
)
```

2. **Debounce interval changes**:
```typescript
const [timeframe, setTimeframe] = useState('1m')
const debouncedTimeframe = useDebounce(timeframe, 500)
```

3. **Use React.memo for chart component**:
```typescript
export const CandlestickChart = React.memo(({ symbol, interval }) => {
  // ... component code
})
```

## 📝 Next Steps

1. ✅ Test with different symbols (BTC, ETH, BNB)
2. ✅ Test with different intervals (1m, 5m, 15m, 1h)
3. ✅ Add volume histogram (see CHARTING_MODULE_GUIDE.md)
4. ✅ Add technical indicators (MA, RSI, MACD)
5. ✅ Integrate with your order panel
6. ✅ Add drawing tools
7. ✅ Save/load chart layouts

## 💡 Pro Tips

- **Zoom**: Scroll wheel on chart
- **Pan**: Click and drag on chart
- **Reset View**: Double-click on chart
- **Crosshair**: Move mouse over chart
- **Price Scale**: Drag up/down on right axis
- **Time Scale**: Drag left/right on bottom axis

## 🎓 Learn More

- Read `CHARTING_MODULE_GUIDE.md` for detailed architecture
- Check `APP_INTEGRATION_EXAMPLES.tsx` for more layouts
- Visit TradingView Lightweight Charts docs: https://tradingview.github.io/lightweight-charts/

---

**Happy Trading! 🎯📈**
