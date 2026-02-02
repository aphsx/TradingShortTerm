import { useState, useEffect } from 'react'
import { Clock, ArrowUp, ArrowDown } from 'lucide-react'

interface Order {
  orderId: number
  symbol: string
  side: 'BUY' | 'SELL'
  type: 'MARKET' | 'LIMIT'
  status: string
  quantity: string
  price?: string
  executedQty?: string
  updateTime?: number
}

export default function OrderHistory() {
  const [orders, setOrders] = useState<Order[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const fetchOrders = async () => {
    setIsLoading(true)
    setError('')
    
    try {
      const response = await fetch('http://localhost:8080/api/orders?symbol=BTCUSDT&limit=20')
      if (!response.ok) {
        if (response.status === 404) {
          // Orders endpoint might not exist yet
          setError('Order history not available')
          return
        }
        throw new Error('Failed to fetch orders')
      }
      const data = await response.json()
      setOrders(data.orders || [])
    } catch (error) {
      console.error('Failed to fetch orders:', error)
      setError('Failed to load order history')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchOrders()
  }, [])

  const formatTime = (timestamp: number) => {
    return new Date(timestamp).toLocaleTimeString()
  }

  const formatPrice = (price?: string) => {
    if (!price) return 'Market'
    return parseFloat(price).toFixed(2)
  }

  return (
    <div className="w-80 bg-[#1E222D] border-l border-[#2B2B43] flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#2B2B43] flex-shrink-0 flex justify-between items-center">
        <h3 className="text-white text-sm font-semibold flex items-center gap-2">
          <Clock className="w-4 h-4" />
          Order History
        </h3>
        <button
          onClick={fetchOrders}
          disabled={isLoading}
          className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50"
        >
          {isLoading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto scrollbar-hide">
        {error ? (
          <div className="px-4 py-8 text-center">
            <p className="text-gray-400 text-xs">{error}</p>
          </div>
        ) : orders.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-gray-400 text-xs">No orders found</p>
            <p className="text-gray-500 text-xs mt-1">Place an order to see it here</p>
          </div>
        ) : (
          <div className="divide-y divide-[#2B2B43]">
            {orders.map((order) => (
              <div key={order.orderId} className="px-4 py-3 hover:bg-[#2B2B43]/50 transition-colors">
                <div className="flex justify-between items-start mb-2">
                  <div className="flex items-center gap-2">
                    <div className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${
                      order.side === 'BUY' 
                        ? 'bg-green-500/20 text-green-400' 
                        : 'bg-red-500/20 text-red-400'
                    }`}>
                      {order.side === 'BUY' ? (
                        <ArrowUp className="w-3 h-3" />
                      ) : (
                        <ArrowDown className="w-3 h-3" />
                      )}
                      {order.side}
                    </div>
                    <span className="text-white text-sm font-medium">{order.symbol}</span>
                  </div>
                  <div className="text-right">
                    <div className="text-white text-sm">{formatPrice(order.price)}</div>
                    <div className="text-gray-400 text-xs">{order.type}</div>
                  </div>
                </div>
                
                <div className="flex justify-between items-center text-xs">
                  <div className="text-gray-400">
                    Qty: {order.quantity}
                    {order.executedQty && order.executedQty !== order.quantity && (
                      <span className="ml-1">({order.executedQty} filled)</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      order.status === 'FILLED' 
                        ? 'bg-green-500/20 text-green-400'
                        : order.status === 'PARTIALLY_FILLED'
                        ? 'bg-yellow-500/20 text-yellow-400'
                        : 'bg-gray-500/20 text-gray-400'
                    }`}>
                      {order.status}
                    </span>
                    {order.updateTime && (
                      <span className="text-gray-500">
                        {formatTime(order.updateTime)}
                      </span>
                    )}
                  </div>
                </div>
                
                <div className="text-gray-500 text-xs mt-1">
                  Order ID: {order.orderId}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
