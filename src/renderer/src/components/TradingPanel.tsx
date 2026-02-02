import { useState } from 'react'
import { useTradingStore } from '../store/useTradingStore'
import { ArrowUpDown, TrendingUp, TrendingDown } from 'lucide-react'

type OrderType = 'limit' | 'market'
type OrderSide = 'buy' | 'sell'

export default function TradingPanel() {
  const { symbol, ticker } = useTradingStore()
  const [orderType, setOrderType] = useState<OrderType>('limit')
  const [orderSide, setOrderSide] = useState<OrderSide>('buy')
  const [price, setPrice] = useState('')
  const [amount, setAmount] = useState('')
  const [total, setTotal] = useState('')

  const handlePercentageClick = (percentage: number) => {
    // Calculate amount based on percentage of available balance
    const availableBalance = 10000 // Mock balance
    const calculatedAmount = (availableBalance * percentage) / 100
    setAmount(calculatedAmount.toFixed(4))
  }

  const handlePlaceOrder = async () => {
    const order = {
      symbol,
      side: orderSide.toUpperCase(),
      type: orderType.toUpperCase(),
      quantity: parseFloat(amount),
      price: orderType === 'limit' ? parseFloat(price) : undefined
    }

    try {
      const response = await fetch('http://localhost:8080/api/order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(order)
      })

      if (!response.ok) {
        throw new Error('Failed to place order')
      }

      const result = await response.json()
      console.log('✅ Order placed:', result)
      alert('Order placed successfully!')

      // Reset form
      setAmount('')
      setPrice('')
      setTotal('')
    } catch (error) {
      console.error('❌ Order failed:', error)
      alert('Failed to place order: ' + (error as Error).message)
    }
  }

  return (
    <div className="w-80 bg-[#1E222D] border-l border-[#2B2B43] flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#2B2B43]">
        <h3 className="text-white text-sm font-semibold flex items-center gap-2">
          <ArrowUpDown className="w-4 h-4" />
          Spot Trading
        </h3>
      </div>

      {/* Order Type Toggle */}
      <div className="px-4 py-3 border-b border-[#2B2B43]">
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
      <div className="px-4 py-2 border-b border-[#2B2B43]">
        <div className="flex justify-between text-xs">
          <span className="text-gray-400">Available</span>
          <span className="text-white font-medium">10,000.00 USDT</span>
        </div>
      </div>

      {/* Order Form */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {/* Price Input */}
        {orderType === 'limit' && (
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Price</label>
            <div className="relative">
              <input
                type="number"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder={ticker?.price.toFixed(2) || '0.00'}
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
          <label className="text-xs text-gray-400 mb-1 block">Amount</label>
          <div className="relative">
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
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
              type="number"
              value={total}
              onChange={(e) => setTotal(e.target.value)}
              placeholder="0.00"
              className="w-full bg-[#131722] text-white text-sm px-3 py-2 rounded 
                       border border-[#2B2B43] focus:outline-none focus:border-[#2962FF]"
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
            className="flex items-center justify-center gap-2 py-2.5 bg-[#26a69a] 
                     hover:bg-[#2ca89f] text-white font-semibold rounded transition-colors"
          >
            <TrendingUp className="w-4 h-4" />
            Buy
          </button>
          <button
            onClick={() => {
              setOrderSide('sell')
              handlePlaceOrder()
            }}
            className="flex items-center justify-center gap-2 py-2.5 bg-[#ef5350] 
                     hover:bg-[#f15b59] text-white font-semibold rounded transition-colors"
          >
            <TrendingDown className="w-4 h-4" />
            Sell
          </button>
        </div>

        {/* Order Info */}
        <div className="pt-3 border-t border-[#2B2B43] space-y-1">
          <div className="flex justify-between text-xs">
            <span className="text-gray-400">Max Buy</span>
            <span className="text-white">0.2312 BTC</span>
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
