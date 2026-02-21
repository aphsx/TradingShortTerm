import asyncio
import ccxt.pro as ccxtpro
import ccxt
import json
from config import API_KEY, SECRET_KEY, TESTNET

async def test_api():
    print("=" * 50)
    print("🚀 CCXT API & ORDER TESTER")
    print("=" * 50)
    
    # Initialize CCXT Profile using identical settings as the bot
    exchange_config = {
        'apiKey': API_KEY,
        'secret': SECRET_KEY,
        'enableRateLimit': True
    }
    
    # Use binanceusdm instead of general binance to skip Spot completely
    exchange = ccxtpro.binanceusdm(exchange_config)
    
    # CCXT introduced enable_demo_trading for Binance specifically
    if TESTNET:
        print("[INFO] CCXT Binance Demo Trading (Mock) Enabled!")
        exchange.enable_demo_trading(True)
        
    try:
        # TEST 1: Check Balances
        print("\n⏳ [1/2] Fetching Account Balance...")
        balance = await exchange.fetch_balance()
        usdt_balance = balance.get('USDT', {})
        total_usdt = usdt_balance.get('total', 0)
        free_usdt = usdt_balance.get('free', 0)
        
        print(f"✅ Success! Connected to {'TESTNET' if TESTNET else 'LIVE'} Account.")
        print(f"💵 Total USDT: {total_usdt}")
        print(f"💵 Free USDT:  {free_usdt}")
        
        if free_usdt < 10:
            print("⚠️ Warning: Your Free USDT is very low or 0. Order tests might fail with Insufficient Margin.")
            
        # TEST 2: Mock an Order on BTC/USDT Linear Futures
        symbol = 'BTC/USDT:USDT'
        print(f"\n⏳ [2/2] Fetching current price for {symbol} to mock an order...")
        ticker = await exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        print(f"📉 Current Price: {current_price} USDT")
        
        # We will mock a LIMIT BUY order 5% below the current price to ensure it doesn't instantly fill
        mock_price = round(current_price * 0.95, 1)
        mock_quantity = 0.002 # Minimal qty for BTC
        mock_leverage = 5
        
        print(f"\n🔄 Adjusting Leverage to {mock_leverage}x for {symbol}...")
        await exchange.set_leverage(mock_leverage, symbol)
        
        print(f"🚀 Attempting to create a MOCK order (BUY {mock_quantity} {symbol} @ {mock_price} USDT)...")
        order = await exchange.create_order(
            symbol=symbol,
            type='limit',
            side='buy',
            amount=mock_quantity,
            price=mock_price,
            params={'timeInForce': 'GTC'} 
        )
        
        print("\n✅ ORDER SUCCESSFUL!")
        print(f"Order ID: {order.get('id')}")
        print(f"Status:   {order.get('status')}")
        
        print("\n🧹 Cleaning up... Canceling the mock order so it doesn't execute.")
        await exchange.cancel_order(order['id'], symbol)
        print("✅ Mock order canceled successfully!")

    except ccxt.AuthenticationError as e:
        print(f"\n❌ AUTH ERROR: Invalid API Key or Secret. Details: {e}")
    except ccxt.InsufficientFunds as e:
        print(f"\n❌ INSUFFICIENT FUNDS: Not enough USDT in your futures wallet. Details: {e}")
    except Exception as e:
        print(f"\n❌ ERROR: Something went wrong: {e}")
    finally:
        await exchange.close()
        print("\nDone.")

if __name__ == "__main__":
    asyncio.run(test_api())
