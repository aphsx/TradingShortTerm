# 24HrT Trading Bot - Go Backend

## 🎯 Features
- ✅ Real-time price streaming via WebSocket (Binance)
- ✅ Market & Limit orders (Buy/Sell)
- ✅ Account balance tracking
- ✅ Testnet support for safe testing
- ✅ Auto-reconnect on connection loss
- ✅ Graceful shutdown

## 🚀 Quick Start

### 1. Get Testnet API Keys
Visit: https://testnet.binance.vision/
- Create an account
- Generate API Key & Secret Key

### 2. Setup Environment
```bash
cd backend
cp .env.example .env
# Edit .env with your testnet keys
```

### 3. Run
```bash
go run main.go
```

## 📁 Project Structure
```
backend/
├── main.go              # Entry point
├── config/
│   └── config.go        # Configuration management
├── client/
│   └── trading.go       # Trading API client
├── websocket/
│   └── price_stream.go  # Real-time price streaming
└── .env                 # Your API keys (create from .env.example)
```

## 🧪 Testing Orders

### Market Order (Buy)
```go
result, err := tradingClient.PlaceMarketBuyOrder("BTCUSDT", "0.001")
```

### Limit Order (Sell)
```go
result, err := tradingClient.PlaceLimitSellOrder("BTCUSDT", "0.001", "50000")
```

### Check Balance
```go
balances, err := tradingClient.GetAccountBalance()
```

### Get Open Orders
```go
orders, err := tradingClient.GetOpenOrders("BTCUSDT")
```

## 🔧 Configuration (.env)

```env
BINANCE_USE_TESTNET=true
BINANCE_API_KEY=your_testnet_api_key
BINANCE_SECRET_KEY=your_testnet_secret_key
DEFAULT_SYMBOL=BTCUSDT
```

## ⚠️ Important Notes

1. **Always test on TESTNET first!**
2. Never commit `.env` file to git
3. Set `BINANCE_USE_TESTNET=false` only when ready for production
4. Use proper position sizing and risk management

## 🔗 Integration with Electron

This backend will run as a child process from Electron's main process. Price updates and trading functions will be accessible via IPC.

## 📚 Libraries Used
- `adshao/go-binance/v2` - Binance API client
- `gorilla/websocket` - WebSocket support
- `joho/godotenv` - Environment variable management
