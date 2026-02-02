import { useState } from 'react'
import { useTradingStore } from '../store/useTradingStore'
import { Star, TrendingUp, TrendingDown, Search } from 'lucide-react'

interface MarketSymbol {
  symbol: string
  name: string
  price: number
  change: number
  changePercent: number
}

const POPULAR_SYMBOLS: MarketSymbol[] = [
  { symbol: 'BTCUSDT', name: 'Bitcoin', price: 43250.50, change: 1250.30, changePercent: 2.98 },
  { symbol: 'ETHUSDT', name: 'Ethereum', price: 2280.75, change: -45.20, changePercent: -1.94 },
  { symbol: 'BNBUSDT', name: 'Binance Coin', price: 315.40, change: 8.75, changePercent: 2.85 },
  { symbol: 'SOLUSDT', name: 'Solana', price: 98.45, change: 5.32, changePercent: 5.71 },
  { symbol: 'XRPUSDT', name: 'Ripple', price: 0.6234, change: -0.0123, changePercent: -1.93 },
  { symbol: 'ADAUSDT', name: 'Cardano', price: 0.4567, change: 0.0234, changePercent: 5.40 },
  { symbol: 'DOGEUSDT', name: 'Dogecoin', price: 0.0823, change: 0.0045, changePercent: 5.78 },
  { symbol: 'MATICUSDT', name: 'Polygon', price: 0.8945, change: -0.0321, changePercent: -3.46 }
]

export default function WatchlistPanel() {
  const { symbol, setSymbol } = useTradingStore()
  const [searchQuery, setSearchQuery] = useState('')
  const [watchlist, setWatchlist] = useState<string[]>(['BTCUSDT', 'ETHUSDT', 'BNBUSDT'])

  const filteredSymbols = POPULAR_SYMBOLS.filter(
    (s) =>
      s.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const toggleWatchlist = (symbolName: string) => {
    if (watchlist.includes(symbolName)) {
      setWatchlist(watchlist.filter((s) => s !== symbolName))
    } else {
      setWatchlist([...watchlist, symbolName])
    }
  }

  return (
    <div className="w-64 bg-[#1E222D] border-r border-[#2B2B43] flex flex-col">
      {/* Header */}
      <div className="px-3 py-2 border-b border-[#2B2B43]">
        <h3 className="text-white text-sm font-semibold mb-2">Watchlist</h3>
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search"
            className="w-full bg-[#131722] text-white text-xs pl-7 pr-2 py-1.5 rounded 
                     border border-[#2B2B43] focus:outline-none focus:border-[#2962FF] 
                     placeholder-gray-500"
          />
        </div>
      </div>

      {/* Symbols List */}
      <div className="flex-1 overflow-y-auto">
        {filteredSymbols.map((item) => (
          <div
            key={item.symbol}
            className={`px-3 py-2 cursor-pointer hover:bg-[#2B2B43] transition-colors border-b border-[#2B2B43] ${
              symbol === item.symbol ? 'bg-[#2B2B43]' : ''
            }`}
            onClick={() => setSymbol(item.symbol)}
          >
            <div className="flex items-start justify-between mb-1">
              <div className="flex items-center gap-2">
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    toggleWatchlist(item.symbol)
                  }}
                  className="hover:text-yellow-500 transition-colors"
                >
                  <Star
                    className={`w-3 h-3 ${
                      watchlist.includes(item.symbol)
                        ? 'fill-yellow-500 text-yellow-500'
                        : 'text-gray-500'
                    }`}
                  />
                </button>
                <div>
                  <div className="text-white text-sm font-medium">{item.symbol}</div>
                  <div className="text-gray-500 text-[10px]">{item.name}</div>
                </div>
              </div>
              <div className="flex items-center gap-1">
                {item.changePercent > 0 ? (
                  <TrendingUp className="w-3 h-3 text-[#26a69a]" />
                ) : (
                  <TrendingDown className="w-3 h-3 text-[#ef5350]" />
                )}
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-white text-xs font-semibold">
                ${item.price.toLocaleString()}
              </span>
              <span
                className={`text-xs font-medium ${
                  item.changePercent >= 0 ? 'text-[#26a69a]' : 'text-[#ef5350]'
                }`}
              >
                {item.changePercent >= 0 ? '+' : ''}
                {item.changePercent.toFixed(2)}%
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
