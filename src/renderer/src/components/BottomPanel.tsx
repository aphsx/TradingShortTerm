import { useState } from 'react'
import { Activity, BookOpen, Clock, Wallet } from 'lucide-react'

type TabType = 'orderbook' | 'trades' | 'positions' | 'orders'

export default function BottomPanel() {
  const [activeTab, setActiveTab] = useState<TabType>('orderbook')

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
  return (
    <div className="flex items-center justify-center h-full">
      <div className="text-center">
        <Wallet className="w-12 h-12 text-gray-600 mx-auto mb-3" />
        <p className="text-gray-400 text-sm">No open positions</p>
        <p className="text-gray-600 text-xs mt-1">Your positions will appear here</p>
      </div>
    </div>
  )
}

function OrdersContent() {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="text-center">
        <Clock className="w-12 h-12 text-gray-600 mx-auto mb-3" />
        <p className="text-gray-400 text-sm">No open orders</p>
        <p className="text-gray-600 text-xs mt-1">Your orders will appear here</p>
      </div>
    </div>
  )
}
