import { useTradingStore } from '../store/useTradingStore'
import { formatPrice, formatPercent } from '../lib/utils'
import { 
  Search, 
  Clock, 
  TrendingUp,
  BarChart3,
  Settings,
  Bell,
  User
} from 'lucide-react'

const TIMEFRAMES = [
  { label: '1m', value: '1m' },
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '1H', value: '1h' },
  { label: '4H', value: '4h' },
  { label: '1D', value: '1d' }
]

export default function TopBar() {
  const { symbol, ticker, interval, setInterval } = useTradingStore()

  return (
    <div className="h-12 bg-[#1E222D] border-b border-[#2B2B43] flex items-center px-3 justify-between">
      {/* Left: Logo & Symbol Search */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-6 h-6 text-[#2962FF]" />
          <span className="text-white font-bold text-sm">24HrTrading</span>
        </div>

        {/* Symbol Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            type="text"
            placeholder="Search symbols..."
            className="bg-[#131722] text-white text-sm pl-9 pr-4 py-1.5 rounded w-64 
                     border border-[#2B2B43] focus:outline-none focus:border-[#2962FF] 
                     placeholder-gray-500"
          />
        </div>

        {/* Timeframe Selector */}
        <div className="flex items-center gap-1 bg-[#131722] rounded px-1 py-0.5">
          <Clock className="w-4 h-4 text-gray-500 ml-2" />
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf.value}
              onClick={() => setInterval(tf.value)}
              className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                interval === tf.value
                  ? 'bg-[#2962FF] text-white'
                  : 'text-gray-400 hover:text-white hover:bg-[#2B2B43]'
              }`}
            >
              {tf.label}
            </button>
          ))}
        </div>
      </div>

      {/* Center: Market Stats */}
      {ticker && (
        <div className="flex items-center gap-6">
          <div className="flex items-baseline gap-2">
            <span className="text-white font-semibold text-base">
              {formatPrice(ticker.price)}
            </span>
            <span
              className={`text-xs font-medium flex items-center gap-1 ${
                ticker.priceChangePercent >= 0 ? 'text-[#26a69a]' : 'text-[#ef5350]'
              }`}
            >
              {ticker.priceChangePercent >= 0 ? '+' : ''}
              {formatPercent(ticker.priceChangePercent)}
            </span>
          </div>

          <div className="h-8 w-px bg-[#2B2B43]" />

          <div className="flex flex-col">
            <span className="text-[10px] text-gray-500">24h High</span>
            <span className="text-xs text-white">{formatPrice(ticker.high24h)}</span>
          </div>

          <div className="flex flex-col">
            <span className="text-[10px] text-gray-500">24h Low</span>
            <span className="text-xs text-white">{formatPrice(ticker.low24h)}</span>
          </div>

          <div className="flex flex-col">
            <span className="text-[10px] text-gray-500">24h Volume</span>
            <span className="text-xs text-white">
              {ticker.volume24h.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </span>
          </div>
        </div>
      )}

      {/* Right: User Actions */}
      <div className="flex items-center gap-3">
        <button className="p-2 hover:bg-[#2B2B43] rounded transition-colors">
          <TrendingUp className="w-4 h-4 text-gray-400" />
        </button>
        <button className="p-2 hover:bg-[#2B2B43] rounded transition-colors">
          <Bell className="w-4 h-4 text-gray-400" />
        </button>
        <button className="p-2 hover:bg-[#2B2B43] rounded transition-colors">
          <Settings className="w-4 h-4 text-gray-400" />
        </button>
        <button className="p-2 hover:bg-[#2B2B43] rounded transition-colors">
          <User className="w-4 h-4 text-gray-400" />
        </button>
      </div>
    </div>
  )
}
