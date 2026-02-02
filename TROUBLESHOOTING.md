# 🔧 Troubleshooting Guide - Runtime Errors

## Issue 1: Backend API Error (500 - Internal Server Error)

**Error Message:**
```
Failed to load resource: the server responded with a status of 500 (Internal Server Error)
at :8080/api/order
```

### Root Cause
The backend needs valid Binance API credentials to process orders.

### Solution

1. **Get Binance API Credentials:**
   - Go to https://testnet.binance.vision
   - Sign in with your account
   - Generate API Key and Secret Key in the API Management section

2. **Create `.env` file in the backend folder:**
   ```bash
   # In: c:\Github\24HrT\backend\.env
   
   BINANCE_API_KEY=your_api_key_here
   BINANCE_SECRET_KEY=your_secret_key_here
   BINANCE_USE_TESTNET=true
   DEFAULT_SYMBOL=BTCUSDT
   ```

3. **Restart the backend:**
   ```bash
   cd c:\Github\24HrT\backend
   go run main.go
   ```

4. **Verify the backend is running:**
   - Check that you see "🧪 Using Binance TESTNET" in the console
   - The server should start on port 8080

---

## Issue 2: Chart Assertion Error

**Error Message:**
```
Error initializing chart: Error: Assertion failed
at TradingChart.tsx:58:32
```

### Root Cause
The lightweight-charts library throws an assertion error when trying to update a series without initial data.

### Solution
✅ **Already Fixed!** The code now includes:
- Error boundary in the useEffect hook
- Validation of price data before updating
- Graceful error handling

**What was changed:**
```typescript
// Added validation
if (!isFinite(dataPoint.value)) {
  console.warn('Invalid price value:', currentPrice.price)
  return
}

// Added try-catch
try {
  seriesRef.current.update(dataPoint)
} catch (error) {
  console.error('Error updating chart data:', error)
}
```

---

## Issue 3: Better Error Messages

✅ **Improved!** The API service now:
- Returns actual backend error messages
- Displays detailed error information in the UI
- Logs requests for debugging

---

## Debugging Checklist

### ✅ Frontend (Electron App)
- [x] Build completed successfully
- [x] TypeScript types check out
- [x] Error handling improved
- [x] Better error messages displayed

### ✅ Backend Setup Required
- [ ] Binance API credentials obtained
- [ ] `.env` file created with credentials
- [ ] Backend running on port 8080
- [ ] "Using Binance TESTNET" message appears

### Verify Connection

**Test the API health endpoint:**
```bash
curl http://localhost:8080/api/health
```

Should return: `{"status":"ok"}`

---

## Development Commands

```bash
# Frontend (Electron)
cd c:\Github\24HrT
npm run dev          # Run with hot reload
npm run build        # Build for production

# Backend (Go)
cd c:\Github\24HrT\backend
go run main.go       # Run the server
```

---

## Common Issues

### "No balances available"
- The backend is running but API credentials are invalid
- Check your Binance API key and secret

### "Failed to fetch balance"
- Backend is not running
- Start the backend: `go run main.go` in the backend folder

### Chart won't display
- Wait for price data to come in (WebSocket connection)
- Check that the WebSocket connection to backend is established
- Look at browser console for connection errors

---

## Next Steps

1. Add your Binance API credentials to `.env`
2. Start the backend: `go run main.go`
3. Start the frontend: `npm run dev`
4. Try placing a test order (small amount on testnet)

Good luck! 🚀
