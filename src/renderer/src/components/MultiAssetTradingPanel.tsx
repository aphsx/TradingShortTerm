import { useState, useEffect } from 'react'
import { useMultiAssetStore } from '../store/useMultiAssetStore'
import AssetSelector from './AssetSelector'
import { ArrowUpDown, TrendingUp, TrendingDown, RefreshCw } from 'lucide-react'
import { getMinOrderSize, getStepSize } from '../config/assets'

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

export default function MultiAssetTradingPanel() {
  const { 
    currentPair,
    balances,
    totalPortfolioValue,
    isLoadingBalance,
    setBalances,
    setLoadingBalance,
    getCurrentPrice,
    getCurrentBaseAsset,
    getCurrentQuoteAsset,
    getAssetBalance,
    getAssetValueInUSD,
    canBuy,
    canSell,
    getMaxBuyAmount,
    getMaxSellAmount
  } = useMultiAssetStore()

  const [orderType, setOrderType] = useState<OrderType>('limit')
  const [orderSide, setOrderSide] = useState<OrderSide>('buy')
  const [price, setPrice] = useState('')
  const [amount, setAmount] = useState('')
  const [total, setTotal] = useState('')

  // Fetch balance on component mount
  useEffect(() => {
    fetchBalance()
  }, [])

  // Auto-calculate total when amount or price changes
  useEffect(() => {
    if (amount && parseFloat(amount) > 0) {
      const priceToUse = orderType === 'limit' && price ? parseFloat(price) : getCurrentPrice()
      if (priceToUse > 0) {
        const totalValue = parseFloat(amount) * priceToUse
        setTotal(totalValue.toFixed(2))
      }
    } else {
      setTotal('')
    }
  }, [amount, price, getCurrentPrice, orderType])

  // Update price when current pair changes
  useEffect(() => {
    const currentPrice = getCurrentPrice()
    if (currentPrice > 0) {
      setPrice(currentPrice.toFixed(currentPrice < 1 ? 4 : 2))
    }
  }, [currentPair, getCurrentPrice])

  const fetchBalance = async () => {
    setLoadingBalance(true)
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
      setBalances([])
      if (error instanceof Error && error.message.includes('API keys not configured')) {
        alert('⚠️ ' + error.message + '\n\nPlease:\n1. Get testnet keys from https://testnet.binance.vision/\n2. Copy .env.testnet to backend/.env\n3. Add your API keys')
      }
    } finally {
      setLoadingBalance(false)
    }
  }

  const handlePercentageClick = (percentage: number) => {
    if (orderSide === 'buy') {
      // For BUY: use quote asset balance
      const quoteAsset = getCurrentQuoteAsset()
      if (!quoteAsset) return
      
      const availableQuote = getAssetBalance(quoteAsset.symbol)
      const quoteAmount = (availableQuote * percentage) / 100
      const priceToUse = orderType === 'limit' && price ? parseFloat(price) : getCurrentPrice()
      
      if (priceToUse > 0) {
        const baseAsset = getCurrentBaseAsset()
        if (baseAsset) {
          const baseAmount = quoteAmount / priceToUse
          setAmount(baseAmount.toFixed(baseAsset.decimals))
        }
      }
    } else {
      // For SELL: use base asset balance
      const baseAsset = getCurrentBaseAsset()
      if (!baseAsset) return
      
      const availableBase = getAssetBalance(baseAsset.symbol)
      const baseAmount = (availableBase * percentage) / 100
      setAmount(baseAmount.toFixed(baseAsset.decimals))
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

    const baseAsset = getCurrentBaseAsset()
    if (!baseAsset) {
      alert('Invalid base asset')
      return
    }

    // Check minimum order size
    const orderQuantity = parseFloat(amount)
    if (orderQuantity < getMinOrderSize(baseAsset.symbol)) {
      alert(`Minimum order size is ${getMinOrderSize(baseAsset.symbol)} ${baseAsset.symbol}`)
      return
    }

    // Check balance
    if (orderSide === 'buy' && !canBuy(orderQuantity)) {
      alert('Insufficient quote asset balance')
      return
    }
    
    if (orderSide === 'sell' && !canSell(orderQuantity)) {
      alert('Insufficient base asset balance')
      return
    }

    const order = {
      symbol: currentPair.symbol,
      side: orderSide.toUpperCase(),
      type: orderType.toUpperCase(),
      quantity: orderQuantity.toFixed(getStepSize(baseAsset.symbol).toString().split('.')[1]?.length || 6),
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
      
      alert(`Order placed successfully!\n\nOrder ID: ${result.orderId}\nSymbol: ${result.symbol}\nSide: ${result.side}\nType: ${result.type}\nQuantity: ${result.quantity}\nPrice: ${result.price || 'Market'}`)

      // Reset form and refresh balance
      setAmount('')
      setPrice('')
      setTotal('')
      fetchBalance()
    } catch (error) {
      console.error('❌ Order failed:', error)
      let errorMessage = 'Failed to place order: ' + (error as Error).message
      
      if (error instanceof Error && error.message.includes('API keys not configured')) {
        errorMessage = '⚠️ API keys not configured!\n\nPlease:\n1. Get testnet keys from https://testnet.binance.vision/\n2. Copy .env.testnet to backend/.env\n3. Add your API keys\n4. Restart the backend'
      }
      
      alert(errorMessage)
    }
  }

  const baseAsset = getCurrentBaseAsset()
  const quoteAsset = getCurrentQuoteAsset()

  return (
    <div className="w-96 bg-[#1E222D] border-l border-[#2B2B43] flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#2B2B43] flex-shrink-0">
        <h3 className="text-white text-sm font-semibold flex items-center gap-2">
          <ArrowUpDown className="w-4 h-4" />
          Multi-Asset Trading
        </h3>
      </div>

      {/* Asset Selector */}
      <div className="px-4 py-3 border-b border-[#2B2B43] flex-shrink-0">
        <AssetSelector />
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
            className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50 flex items-center gap-1"
          >
            <RefreshCw className={`w-3 h-3 ${isLoadingBalance ? 'animate-spin' : ''}`} />
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
            {/* Total Portfolio Value */}
            <div className="flex justify-between text-sm mb-3 pb-2 border-b border-[#2B2B43]">
              <span className="text-gray-300 font-medium">Total Value</span>
              <span className="text-white font-bold text-green-400">
                ${totalPortfolioValue.toFixed(2)}
              </span>
            </div>
            
            {/* Current Trading Assets */}
            {baseAsset && quoteAsset && (
              <div className="space-y-2">
                <div className="bg-[#131722] rounded p-2">
                  <div className="flex justify-between items-center mb-1">
                    <div className="flex items-center gap-2">
                      <CryptoIcon icon={quoteAsset.icon} symbol={quoteAsset.symbol} size={16} />
                      <span className="text-gray-400 text-xs">{quoteAsset.symbol} (Quote)</span>
                    </div>
                    <span className="text-green-400 text-xs">Available for BUY</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-white font-medium">${getAssetValueInUSD(quoteAsset.symbol).toFixed(2)}</span>
                    <span className="text-gray-500">{getAssetBalance(quoteAsset.symbol).toFixed(2)} {quoteAsset.symbol}</span>
                  </div>
                  {getCurrentPrice() > 0 && getAssetBalance(quoteAsset.symbol) > 0 && (
                    <div className="text-xs text-gray-400 mt-1">
                      Can buy: {(getAssetBalance(quoteAsset.symbol) / getCurrentPrice()).toFixed(6)} {baseAsset.symbol}
                    </div>
                  )}
                </div>
                
                <div className="bg-[#131722] rounded p-2">
                  <div className="flex justify-between items-center mb-1">
                    <div className="flex items-center gap-2">
                      <CryptoIcon icon={baseAsset.icon} symbol={baseAsset.symbol} size={16} />
                      <span className="text-gray-400 text-xs">{baseAsset.symbol} (Base)</span>
                    </div>
                    <span className="text-red-400 text-xs">Available for SELL</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-white font-medium">${getAssetValueInUSD(baseAsset.symbol).toFixed(2)}</span>
                    <span className="text-gray-500">{getAssetBalance(baseAsset.symbol).toFixed(baseAsset.decimals)} {baseAsset.symbol}</span>
                  </div>
                  {getAssetBalance(baseAsset.symbol) > 0 && (
                    <div className="text-xs text-gray-400 mt-1">
                      Can sell: {getAssetBalance(baseAsset.symbol).toFixed(6)} {baseAsset.symbol}
                    </div>
                  )}
                </div>
              </div>
            )}
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
                placeholder={getCurrentPrice().toFixed(getCurrentPrice() < 1 ? 4 : 2)}
                className="w-full bg-[#131722] text-white text-sm px-3 py-2 rounded 
                         border border-[#2B2B43] focus:outline-none focus:border-[#2962FF]"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500">
                {quoteAsset?.symbol}
              </span>
            </div>
          </div>
        )}

        {/* Amount Input */}
        <div>
          <label className="text-xs text-gray-400 mb-1 block">
            Amount {baseAsset && `(min: ${getMinOrderSize(baseAsset.symbol)} ${baseAsset.symbol})`}
          </label>
          <div className="relative">
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00000"
              step={baseAsset ? getStepSize(baseAsset.symbol).toString() : "0.00001"}
              min={baseAsset ? getMinOrderSize(baseAsset.symbol).toString() : "0.00001"}
              className="w-full bg-[#131722] text-white text-sm px-3 py-2 rounded 
                       border border-[#2B2B43] focus:outline-none focus:border-[#2962FF]"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500">
              {baseAsset?.symbol}
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
              {quoteAsset?.symbol}
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
            disabled={!baseAsset || !quoteAsset || !canBuy(parseFloat(amount) || 0)}
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
            disabled={!baseAsset || !quoteAsset || !canSell(parseFloat(amount) || 0)}
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
                {baseAsset && quoteAsset ? 
                  `${getMaxBuyAmount().toFixed(baseAsset.decimals)} ${baseAsset.symbol}` : 
                  '0.000000'
                }
              </span>
              <span className="text-gray-500 ml-2">
                (${quoteAsset ? getAssetBalance(quoteAsset.symbol).toFixed(2) : '0.00'})
              </span>
            </div>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-gray-400">Max Sell</span>
            <div className="text-right">
              <span className="text-white">
                {baseAsset ? `${getMaxSellAmount().toFixed(baseAsset.decimals)} ${baseAsset.symbol}` : '0.000000'}
              </span>
              <span className="text-gray-500 ml-2">
                (${baseAsset ? getAssetValueInUSD(baseAsset.symbol).toFixed(2) : '0.00'})
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
