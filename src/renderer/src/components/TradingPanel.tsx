import { useState, useEffect } from 'react'
import { useMultiAssetStore } from '../store/useMultiAssetStore'
import { ArrowUpDown, TrendingUp, TrendingDown } from 'lucide-react'

// Import crypto icons
import btcIcon from 'cryptocurrency-icons/svg/color/btc.svg'
import usdtIcon from 'cryptocurrency-icons/svg/color/usdt.svg'

// Create a simple icon component for SVG
const CryptoIcon = ({ icon, symbol, size = 20 }: { icon: string; symbol: string; size?: number }) => (
  <img 
    src={icon} 
    alt={symbol}
    style={{ width: size, height: size }}
    className="rounded-full"
  />
)

type OrderType = 'limit' | 'market'
type OrderSide = 'buy' | 'sell'

export default function TradingPanel() {
  const { currentSymbol, getCurrentPrice, balances, setBalances } = useMultiAssetStore()
  const currentPrice = getCurrentPrice()
  const [orderType, setOrderType] = useState<OrderType>('limit')
  const [orderSide, setOrderSide] = useState<OrderSide>('buy')
  const [price, setPrice] = useState('')
  const [amount, setAmount] = useState('')
  const [total, setTotal] = useState('')
  const [isLoadingBalance, setIsLoadingBalance] = useState(false)

  // Fetch balance on component mount
  useEffect(() => {
    fetchBalance()
  }, [])

  // Auto-calculate total when amount or price changes
  useEffect(() => {
    if (amount && parseFloat(amount) > 0) {
      const priceToUse = orderType === 'limit' && price ? parseFloat(price) : currentPrice
      if (priceToUse > 0) {
        const totalValue = parseFloat(amount) * priceToUse
        setTotal(totalValue.toFixed(2))
      }
    } else {
      setTotal('')
    }
  }, [amount, price, currentPrice, orderType])

  const fetchBalance = async () => {
    setIsLoadingBalance(true)
    try {
      const response = await fetch('http://localhost:8080/api/balance')
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        if (errorData.error && errorData.error.includes('API keys not configured')) {
          throw new Error('API keys not configured. Please check BINANCE_TESTNET_SETUP.md for instructions.')
        }
        throw new Error(errorData.error || 'Failed to fetch balance')
      }
      const data = await response.json()
      setBalances(data.balances || [])
    } catch (error) {
      console.error('Failed to fetch balance:', error)
      setBalances([]) // Clear balances on error
      // Show more helpful error message
      if (error instanceof Error && error.message.includes('API keys not configured')) {
        alert('⚠️ ' + error.message + '\n\nPlease:\n1. Get testnet keys from https://testnet.binance.vision/\n2. Copy .env.testnet to backend/.env\n3. Add your API keys')
      }
    } finally {
      setIsLoadingBalance(false)
    }
  }

  const getUSDTBalance = () => {
    const usdtBalance = balances.find(b => b.asset === 'USDT')
    return usdtBalance ? parseFloat(usdtBalance.free) : 0
  }

  const getBTCBalance = () => {
    const btcBalance = balances.find(b => b.asset === 'BTC')
    return btcBalance ? parseFloat(btcBalance.free) : 0
  }

  const getBTCValueInUSD = () => {
    const btcBalance = getBTCBalance()
    return currentPrice > 0 ? btcBalance * currentPrice : 0
  }

  const getTotalBalanceInUSD = () => {
    return getUSDTBalance() + getBTCValueInUSD()
  }

  const handlePercentageClick = (percentage: number) => {
    // Calculate amount based on percentage of available balance
    if (orderSide === 'buy') {
      // For BUY: use USDT balance and convert to BTC
      const availableUSDT = getUSDTBalance()
      const usdtAmount = (availableUSDT * percentage) / 100
      const priceToUse = orderType === 'limit' && price ? parseFloat(price) : currentPrice
      if (priceToUse > 0) {
        const btcAmount = usdtAmount / priceToUse
        setAmount(btcAmount.toFixed(6)) // BTC has 6 decimals
      }
    } else {
      // For SELL: use BTC balance
      const availableBTC = getBTCBalance()
      const btcAmount = (availableBTC * percentage) / 100
      setAmount(btcAmount.toFixed(6))
    }
  }

  const handlePlaceOrder = async () => {
    if (!amount || parseFloat(amount) <= 0) {
      alert('Please enter a valid amount')
      return
    }

    if (orderType === 'limit' && (!price || parseFloat(price) <= 0)) {
      alert('Please enter a valid price for limit orders')
      return
    }

    // Convert amount to proper format (minimum 0.00001 BTC for BTCUSDT)
    const btcQuantity = parseFloat(amount)
    if (btcQuantity < 0.00001) {
      alert('Minimum order size is 0.00001 BTC')
      return
    }

    const order = {
      symbol: currentSymbol,
      side: orderSide.toUpperCase(),
      type: orderType.toUpperCase(),
      quantity: btcQuantity.toFixed(5), // Format to 5 decimals (Binance stepSize)
      ...(orderType === 'limit' && { price: price })
    }

    try {
      const response = await fetch('http://localhost:8080/api/order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(order)
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.error || `Failed to place order: ${response.status}`)
      }

      const result = await response.json()
      console.log('✅ Order placed:', result)
      
      // Show success message with order details
      alert(`Order placed successfully!\n\nOrder ID: ${result.orderId}\nSymbol: ${result.symbol}\nSide: ${result.side}\nType: ${result.type}\nQuantity: ${result.quantity}\nPrice: ${result.price || 'Market'}`)

      // Reset form and refresh balance
      setAmount('')
      setPrice('')
      setTotal('')
      fetchBalance() // Refresh balance after successful order
    } catch (error) {
      console.error('❌ Order failed:', error)
      let errorMessage = 'Failed to place order: ' + (error as Error).message
      
      // Show more helpful error message for API key issues
      if (error instanceof Error && error.message.includes('API keys not configured')) {
        errorMessage = '⚠️ API keys not configured!\n\nPlease:\n1. Get testnet keys from https://testnet.binance.vision/\n2. Copy .env.testnet to backend/.env\n3. Add your API keys\n4. Restart the backend'
      }
      
      alert(errorMessage)
    }
  }

  return (
    <div className="w-80 bg-[#1E222D] border-l border-[#2B2B43] flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#2B2B43] flex-shrink-0">
        <h3 className="text-white text-sm font-semibold flex items-center gap-2">
          <ArrowUpDown className="w-4 h-4" />
          Spot Trading
        </h3>
      </div>

      {/* Order Type Toggle */}
      <div className="px-4 py-3 border-b border-[#2B2B43] flex-shrink-0">
        <div className="flex gap-2 bg-[#131722] rounded p-1">
          <button
            onClick={() => setOrderType('limit')}
            className={`flex-1 py-1.5 text-xs font-medium rounded transition-colors ${
              orderType === 'limit'
                ? 'bg-[#2962FF] text-white'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            Limit
          </button>
          <button
            onClick={() => setOrderType('market')}
            className={`flex-1 py-1.5 text-xs font-medium rounded transition-colors ${
              orderType === 'market'
                ? 'bg-[#2962FF] text-white'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            Market
          </button>
        </div>
      </div>

      {/* Balance */}
      <div className="px-4 py-2 border-b border-[#2B2B43] flex-shrink-0">
        <div className="flex justify-between items-center mb-2">
          <span className="text-gray-400 text-xs">Portfolio Balance</span>
          <button
            onClick={fetchBalance}
            disabled={isLoadingBalance}
            className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50"
          >
            {isLoadingBalance ? 'Loading...' : 'Refresh'}
          </button>
        </div>
        {balances.length === 0 ? (
          <div className="text-center py-2">
            <p className="text-gray-500 text-xs">No balance data available</p>
            <p className="text-gray-600 text-xs mt-1">Please configure API keys</p>
          </div>
        ) : (
          <>
            {/* Trading Pair Info */}
            <div className="bg-[#131722] rounded p-2 mb-3">
              <div className="text-center text-xs text-gray-400 mb-1">Trading Pair: {currentSymbol}</div>
              <div className="text-center text-sm">
                <span className="text-gray-400">Current Price: </span>
                <span className="text-white font-bold">
                  ${currentPrice > 0 ? currentPrice.toFixed(2) : '0.00'}
                </span>
              </div>
            </div>
            
            {/* Total USD Balance */}
            <div className="flex justify-between text-sm mb-3 pb-2 border-b border-[#2B2B43]">
              <span className="text-gray-300 font-medium">Total Value</span>
              <span className="text-white font-bold text-green-400">
                ${getTotalBalanceInUSD().toFixed(2)}
              </span>
            </div>
            
            {/* Individual Assets with Trading Info */}
            <div className="space-y-2">
              <div className="bg-[#131722] rounded p-2">
                <div className="flex justify-between items-center mb-1">
                    <div className="flex items-center gap-2">
                      <CryptoIcon icon={usdtIcon} symbol="USDT" size={16} />
                      <span className="text-gray-400 text-xs">USDT (Cash)</span>
                    </div>
                    <span className="text-green-400 text-xs">Available for BUY</span>
                  </div>
                <div className="flex justify-between text-xs">
                  <span className="text-white font-medium">${getUSDTBalance().toFixed(2)}</span>
                  <span className="text-gray-500">{getUSDTBalance().toFixed(2)} USDT</span>
                </div>
                {currentPrice > 0 && getUSDTBalance() > 0 && (
                  <div className="text-xs text-gray-400 mt-1">
                    Can buy: {(getUSDTBalance() / currentPrice).toFixed(6)} BTC
                  </div>
                )}
              </div>
              
              <div className="bg-[#131722] rounded p-2">
                <div className="flex justify-between items-center mb-1">
                    <div className="flex items-center gap-2">
                      <CryptoIcon icon={btcIcon} symbol="BTC" size={16} />
                      <span className="text-gray-400 text-xs">BTC (Bitcoin)</span>
                    </div>
                    <span className="text-red-400 text-xs">Available for SELL</span>
                  </div>
                <div className="flex justify-between text-xs">
                  <span className="text-white font-medium">${getBTCValueInUSD().toFixed(2)}</span>
                  <span className="text-gray-500">{getBTCBalance().toFixed(8)} BTC</span>
                </div>
                {getBTCBalance() > 0 && (
                  <div className="text-xs text-gray-400 mt-1">
                    Can sell: {getBTCBalance().toFixed(6)} BTC
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Order Form */}
      <div className="flex-1 overflow-y-auto scrollbar-hide px-4 py-3 space-y-3">
        {/* Price Input */}
        {orderType === 'limit' && (
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Price</label>
            <div className="relative">
              <input
                type="number"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder={currentPrice > 0 ? currentPrice.toFixed(2) : '0.00'}
                className="w-full bg-[#131722] text-white text-sm px-3 py-2 rounded 
                         border border-[#2B2B43] focus:outline-none focus:border-[#2962FF]"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500">
                USDT
              </span>
            </div>
          </div>
        )}

        {/* Amount Input */}
        <div>
          <label className="text-xs text-gray-400 mb-1 block">
            Amount <span className="text-gray-500">(min: 0.00001 BTC)</span>
          </label>
          <div className="relative">
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00000"
              step="0.00001"
              min="0.00001"
              className="w-full bg-[#131722] text-white text-sm px-3 py-2 rounded 
                       border border-[#2B2B43] focus:outline-none focus:border-[#2962FF]"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500">
              BTC
            </span>
          </div>
        </div>

        {/* Percentage Buttons */}
        <div className="flex gap-2">
          {[25, 50, 75, 100].map((percentage) => (
            <button
              key={percentage}
              onClick={() => handlePercentageClick(percentage)}
              className="flex-1 py-1.5 text-xs bg-[#131722] text-gray-400 rounded 
                       hover:bg-[#2B2B43] hover:text-white transition-colors"
            >
              {percentage}%
            </button>
          ))}
        </div>

        {/* Total Input */}
        <div>
          <label className="text-xs text-gray-400 mb-1 block">Total</label>
          <div className="relative">
            <input
              type="text"
              value={total}
              readOnly
              placeholder="0.00"
              className="w-full bg-[#1a1a2e] text-white text-sm px-3 py-2 rounded 
                       border border-[#2B2B43] cursor-not-allowed"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500">
              USDT
            </span>
          </div>
        </div>

        {/* Buy/Sell Buttons */}
        <div className="grid grid-cols-2 gap-2 pt-2">
          <button
            onClick={() => {
              setOrderSide('buy')
              handlePlaceOrder()
            }}
            disabled={balances.length === 0 || getUSDTBalance() <= 0}
            className="flex items-center justify-center gap-2 py-2.5 bg-[#26a69a] 
                     hover:bg-[#2ca89f] text-white font-semibold rounded transition-colors
                     disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-[#26a69a]"
          >
            <TrendingUp className="w-4 h-4" />
            Buy
          </button>
          <button
            onClick={() => {
              setOrderSide('sell')
              handlePlaceOrder()
            }}
            disabled={balances.length === 0 || getBTCBalance() <= 0}
            className="flex items-center justify-center gap-2 py-2.5 bg-[#ef5350] 
                     hover:bg-[#f15b59] text-white font-semibold rounded transition-colors
                     disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-[#ef5350]"
          >
            <TrendingDown className="w-4 h-4" />
            Sell
          </button>
        </div>

        {/* Order Info */}
        <div className="pt-3 border-t border-[#2B2B43] space-y-1">
          <div className="flex justify-between text-xs">
            <span className="text-gray-400">Max Buy</span>
            <div className="text-right">
              <span className="text-white">
                {currentPrice > 0 && getUSDTBalance() > 0 
                  ? (getUSDTBalance() / currentPrice).toFixed(6) + ' BTC'
                  : '0.000000 BTC'
                }
              </span>
              <span className="text-gray-500 ml-2">
                (${getUSDTBalance().toFixed(2)})
              </span>
            </div>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-gray-400">Trading Fee</span>
            <span className="text-white">0.1%</span>
          </div>
        </div>
      </div>
    </div>
  )
}
