import { useState, useEffect } from 'react'
import { Activity, BookOpen, Clock, Wallet, RefreshCw } from 'lucide-react'
import { useTradingStore } from '../store/useTradingStore'

type TabType = 'orderbook' | 'trades' | 'positions' | 'orders'

interface Order {
  orderId: number
  symbol: string
  side: string
  type: string
  price: string
  origQty: string
  executedQty: string
  status: string
  time: number
}

export default function BottomPanel() {
  const [activeTab, setActiveTab] = useState<TabType>('orders')

  const tabs = [
    { id: 'orderbook' as TabType, label: 'Order Book', icon: BookOpen },
    { id: 'trades' as TabType, label: 'Recent Trades', icon: Activity },
    { id: 'positions' as TabType, label: 'Positions', icon: Wallet },
    { id: 'orders' as TabType, label: 'Orders', icon: Clock }
  ]

  return (
    <div className="h-64 bg-[#1E222D] border-t border-[#2B2B43] flex flex-col">
      {/* Tabs */}
      <div className="flex items-center gap-1 px-3 py-2 border-b border-[#2B2B43]">
        {tabs.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded transition-colors ${
                activeTab === tab.id
                  ? 'bg-[#2962FF] text-white'
                  : 'text-gray-400 hover:text-white hover:bg-[#2B2B43]'
              }`}
            >
              <Icon className="w-3 h-3" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'orderbook' && <OrderBookContent />}
        {activeTab === 'trades' && <RecentTradesContent />}
        {activeTab === 'positions' && <PositionsContent />}
        {activeTab === 'orders' && <OrdersContent />}
      </div>
    </div>
  )
}

function OrderBookContent() {
  const bids = [
    { price: 43250.50, amount: 0.5234, total: 22634.21 },
    { price: 43248.30, amount: 1.2341, total: 53363.87 },
    { price: 43245.10, amount: 0.8765, total: 37903.29 },
    { price: 43242.00, amount: 2.1234, total: 91834.57 },
    { price: 43240.50, amount: 0.4321, total: 18682.34 }
  ]

  const asks = [
    { price: 43252.50, amount: 0.6543, total: 28303.16 },
    { price: 43254.80, amount: 1.4321, total: 61957.72 },
    { price: 43257.20, amount: 0.9876, total: 42721.56 },
    { price: 43260.00, amount: 2.3456, total: 101472.96 },
    { price: 43262.50, amount: 0.5432, total: 23502.43 }
  ]

  return (
    <div className="grid grid-cols-2 h-full">
      {/* Bids */}
      <div className="border-r border-[#2B2B43]">
        <div className="grid grid-cols-3 gap-2 px-3 py-2 text-[10px] text-gray-500 border-b border-[#2B2B43]">
          <div>Price (USDT)</div>
          <div className="text-right">Amount (BTC)</div>
          <div className="text-right">Total</div>
        </div>
        <div className="overflow-y-auto" style={{ height: 'calc(100% - 32px)' }}>
          {bids.map((bid, idx) => (
            <div
              key={idx}
              className="grid grid-cols-3 gap-2 px-3 py-1 text-xs hover:bg-[#2B2B43] cursor-pointer"
            >
              <div className="text-[#26a69a] font-medium">{bid.price.toFixed(2)}</div>
              <div className="text-white text-right">{bid.amount.toFixed(4)}</div>
              <div className="text-gray-400 text-right">{bid.total.toFixed(2)}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Asks */}
      <div>
        <div className="grid grid-cols-3 gap-2 px-3 py-2 text-[10px] text-gray-500 border-b border-[#2B2B43]">
          <div>Price (USDT)</div>
          <div className="text-right">Amount (BTC)</div>
          <div className="text-right">Total</div>
        </div>
        <div className="overflow-y-auto" style={{ height: 'calc(100% - 32px)' }}>
          {asks.map((ask, idx) => (
            <div
              key={idx}
              className="grid grid-cols-3 gap-2 px-3 py-1 text-xs hover:bg-[#2B2B43] cursor-pointer"
            >
              <div className="text-[#ef5350] font-medium">{ask.price.toFixed(2)}</div>
              <div className="text-white text-right">{ask.amount.toFixed(4)}</div>
              <div className="text-gray-400 text-right">{ask.total.toFixed(2)}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function RecentTradesContent() {
  const trades = [
    { price: 43251.20, amount: 0.0234, time: '14:32:45', type: 'buy' },
    { price: 43250.50, amount: 0.1234, time: '14:32:43', type: 'sell' },
    { price: 43252.30, amount: 0.0567, time: '14:32:41', type: 'buy' },
    { price: 43249.80, amount: 0.2341, time: '14:32:38', type: 'sell' },
    { price: 43251.50, amount: 0.0876, time: '14:32:35', type: 'buy' }
  ]

  return (
    <div className="h-full flex flex-col">
      <div className="grid grid-cols-3 gap-2 px-3 py-2 text-[10px] text-gray-500 border-b border-[#2B2B43]">
        <div>Price (USDT)</div>
        <div className="text-right">Amount (BTC)</div>
        <div className="text-right">Time</div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {trades.map((trade, idx) => (
          <div
            key={idx}
            className="grid grid-cols-3 gap-2 px-3 py-1 text-xs hover:bg-[#2B2B43]"
          >
            <div
              className={`font-medium ${
                trade.type === 'buy' ? 'text-[#26a69a]' : 'text-[#ef5350]'
              }`}
            >
              {trade.price.toFixed(2)}
            </div>
            <div className="text-white text-right">{trade.amount.toFixed(4)}</div>
            <div className="text-gray-400 text-right">{trade.time}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function PositionsContent() {
  const { currentPrice } = useTradingStore()
  const [balances, setBalances] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(false)

  const fetchBalances = async () => {
    setIsLoading(true)
    try {
      const response = await fetch('http://localhost:8080/api/balance')
      if (!response.ok) {
        throw new Error('Failed to fetch balance')
      }
      const data = await response.json()
      // Filter only non-zero balances
      const nonZero = (data.balances || []).filter(
        (b: any) => parseFloat(b.free) > 0 || parseFloat(b.locked) > 0
      )
      setBalances(nonZero)
    } catch (error) {
      console.error('Failed to fetch balances:', error)
      setBalances([])
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchBalances()
    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchBalances, 30000)
    return () => clearInterval(interval)
  }, [])

  const calculateUSDValue = (asset: string, amount: number) => {
    if (asset === 'USDT') return amount
    if (asset === 'BTC' && currentPrice > 0) return amount * currentPrice
    return 0
  }

  const totalUSDValue = balances.reduce((sum, balance) => {
    const amount = parseFloat(balance.free)
    return sum + calculateUSDValue(balance.asset, amount)
  }, 0)

  if (balances.length === 0 && !isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <Wallet className="w-12 h-12 text-gray-600 mx-auto mb-3" />
          <p className="text-gray-400 text-sm">No positions</p>
          <p className="text-gray-600 text-xs mt-1">Your positions will appear here</p>
          <button
            onClick={fetchBalances}
            className="text-xs text-blue-400 hover:text-blue-300 px-3 py-1 rounded bg-[#2B2B43] mt-3"
          >
            Refresh
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header with total */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#2B2B43]">
        <div className="text-xs">
          <span className="text-gray-400">Total Value: </span>
          <span className="text-white font-bold">${totalUSDValue.toFixed(2)}</span>
        </div>
        <button
          onClick={fetchBalances}
          disabled={isLoading}
          className="text-gray-400 hover:text-white disabled:opacity-50"
          title="Refresh"
        >
          <RefreshCw className={`w-3 h-3 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Table Header */}
      <div className="grid grid-cols-5 gap-2 px-3 py-2 text-[10px] text-gray-500 border-b border-[#2B2B43]">
        <div>Asset</div>
        <div className="text-right">Free</div>
        <div className="text-right">Locked</div>
        <div className="text-right">Total</div>
        <div className="text-right">USD Value</div>
      </div>

      {/* Table Body */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && balances.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <RefreshCw className="w-6 h-6 text-gray-500 animate-spin" />
          </div>
        ) : (
          balances.map((balance) => {
            const free = parseFloat(balance.free)
            const locked = parseFloat(balance.locked)
            const total = free + locked
            const usdValue = calculateUSDValue(balance.asset, free)

            return (
              <div
                key={balance.asset}
                className="grid grid-cols-5 gap-2 px-3 py-2 text-xs hover:bg-[#2B2B43] border-b border-[#2B2B43]/30"
              >
                <div className="text-white font-medium">{balance.asset}</div>
                <div className="text-white text-right font-mono">
                  {balance.asset === 'BTC' ? free.toFixed(8) : free.toFixed(2)}
                </div>
                <div className="text-yellow-500 text-right font-mono">
                  {locked > 0 ? (balance.asset === 'BTC' ? locked.toFixed(8) : locked.toFixed(2)) : '-'}
                </div>
                <div className="text-white text-right font-mono">
                  {balance.asset === 'BTC' ? total.toFixed(8) : total.toFixed(2)}
                </div>
                <div className="text-green-500 text-right font-mono">
                  {usdValue > 0 ? `$${usdValue.toFixed(2)}` : '-'}
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

function OrdersContent() {
  const { symbol } = useTradingStore()
  const [orders, setOrders] = useState<Order[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [showAll, setShowAll] = useState(false)

  const fetchOrders = async () => {
    setIsLoading(true)
    try {
      const endpoint = showAll 
        ? `http://localhost:8080/api/orders?symbol=${symbol}&limit=50`
        : `http://localhost:8080/api/orders/open?symbol=${symbol}`
      
      const response = await fetch(endpoint)
      if (!response.ok) {
        throw new Error('Failed to fetch orders')
      }
      const data = await response.json()
      setOrders(data.orders || [])
    } catch (error) {
      console.error('Failed to fetch orders:', error)
      setOrders([])
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchOrders()
    // Auto-refresh every 10 seconds
    const interval = setInterval(fetchOrders, 10000)
    return () => clearInterval(interval)
  }, [symbol, showAll])

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'FILLED':
        return 'text-green-500'
      case 'PARTIALLY_FILLED':
        return 'text-yellow-500'
      case 'CANCELED':
        return 'text-red-500'
      case 'NEW':
        return 'text-blue-500'
      default:
        return 'text-gray-400'
    }
  }

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp)
    return date.toLocaleString('en-US', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    })
  }

  if (orders.length === 0 && !isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <Clock className="w-12 h-12 text-gray-600 mx-auto mb-3" />
          <p className="text-gray-400 text-sm">
            {showAll ? 'No order history' : 'No open orders'}
          </p>
          <p className="text-gray-600 text-xs mt-1">
            {showAll ? 'Your order history will appear here' : 'Your open orders will appear here'}
          </p>
          <div className="flex gap-2 justify-center mt-3">
            <button
              onClick={() => setShowAll(!showAll)}
              className="text-xs text-blue-400 hover:text-blue-300 px-3 py-1 rounded bg-[#2B2B43]"
            >
              {showAll ? 'Show Open Only' : 'Show All Orders'}
            </button>
            <button
              onClick={fetchOrders}
              className="text-xs text-blue-400 hover:text-blue-300 px-3 py-1 rounded bg-[#2B2B43]"
            >
              Refresh
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header with filters */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#2B2B43]">
        <div className="flex gap-2">
          <button
            onClick={() => setShowAll(false)}
            className={`text-xs px-2 py-1 rounded ${
              !showAll ? 'bg-[#2962FF] text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            Open Orders
          </button>
          <button
            onClick={() => setShowAll(true)}
            className={`text-xs px-2 py-1 rounded ${
              showAll ? 'bg-[#2962FF] text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            Order History
          </button>
        </div>
        <button
          onClick={fetchOrders}
          disabled={isLoading}
          className="text-gray-400 hover:text-white disabled:opacity-50"
          title="Refresh"
        >
          <RefreshCw className={`w-3 h-3 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Table Header */}
      <div className="grid grid-cols-7 gap-2 px-3 py-2 text-[10px] text-gray-500 border-b border-[#2B2B43]">
        <div>Time</div>
        <div>Side</div>
        <div className="text-right">Price</div>
        <div className="text-right">Amount</div>
        <div className="text-right">Filled</div>
        <div>Status</div>
        <div className="text-right">Order ID</div>
      </div>

      {/* Table Body */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && orders.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <RefreshCw className="w-6 h-6 text-gray-500 animate-spin" />
          </div>
        ) : (
          orders.map((order) => (
            <div
              key={order.orderId}
              className="grid grid-cols-7 gap-2 px-3 py-2 text-xs hover:bg-[#2B2B43] border-b border-[#2B2B43]/30"
            >
              <div className="text-gray-400 text-[10px]">
                {formatTime(order.time)}
              </div>
              <div
                className={`font-medium ${
                  order.side === 'BUY' ? 'text-green-500' : 'text-red-500'
                }`}
              >
                {order.side}
              </div>
              <div className="text-white text-right font-mono">
                {parseFloat(order.price).toFixed(2)}
              </div>
              <div className="text-white text-right font-mono">
                {parseFloat(order.origQty).toFixed(5)}
              </div>
              <div className="text-gray-400 text-right font-mono">
                {parseFloat(order.executedQty).toFixed(5)}
              </div>
              <div className={`text-[10px] ${getStatusColor(order.status)}`}>
                {order.status}
              </div>
              <div className="text-gray-500 text-right text-[10px] font-mono">
                #{order.orderId}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
