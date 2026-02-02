# Binance Testnet Setup Guide

## 🚨 IMPORTANT: USE TESTNET ONLY!
This application is configured to use **Binance Testnet** by default. Never use real API keys until you've thoroughly tested the system.

## 📋 Setup Steps

### 1. Get Testnet API Keys
1. Go to: https://testnet.binance.vision/
2. Login or create an account
3. Go to API Management
4. Create new API keys
5. Copy your API Key and Secret Key

### 2. Configure Environment
Copy the testnet configuration file:
```bash
cp .env.testnet backend/.env
```

Then edit `backend/.env` and replace:
- `your_testnet_api_key_here` with your actual testnet API key
- `your_testnet_secret_key_here` with your actual testnet secret key

### 3. Start the Application
```bash
# Start backend
cd backend
go run main.go

# In another terminal, start frontend
yarn dev
```

### 4. Test Trading
1. Open the application
2. Go to the Trading panel
3. Try placing a small test order (e.g., 0.001 BTC)
4. Check if the order appears in Order History

## 🔍 Testing Checklist

- [ ] Balance shows real testnet values
- [ ] Market orders execute immediately
- [ ] Limit orders are placed correctly
- [ ] Order history shows placed orders
- [ ] Balance updates after orders

## 🚨 Safety Reminders

- **NEVER** use production API keys
- **ALWAYS** test with small amounts first
- **VERIFY** you're on testnet (logs will show "Using Binance TESTNET")
- **CHECK** the URL: testnet.binance.vision

## 🆘 Troubleshooting

### "Invalid API keys" error
- Double-check your testnet API keys
- Ensure you're using testnet.binance.vision keys, not main.binance.com

### "Insufficient balance" error
- Get testnet funds from the testnet faucet
- Check your testnet account balance

### Connection issues
- Ensure backend is running on port 8080
- Check that testnet.binance.vision is accessible

## 📚 Useful Links

- [Binance Testnet](https://testnet.binance.vision/)
- [Testnet Faucet](https://testnet.binance.vision/faucet)
- [API Documentation](https://binance-docs.github.io/apidocs/spot/en/)
