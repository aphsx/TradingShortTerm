import { useState } from 'react'
import { useTradingStore } from '../store/useTradingStore'
import { cn } from '../lib/utils'

const POPULAR_SYMBOLS = [
  'BTCUSDT',
  'ETHUSDT',
  'BNBUSDT',
  'SOLUSDT',
  'XRPUSDT',
  'ADAUSDT',
  'DOGEUSDT',
  'MATICUSDT',
  'DOTUSDT',
  'LTCUSDT'
]

export default function SymbolSelector() {
  const { symbol, setSymbol } = useTradingStore()
  const [searchQuery, setSearchQuery] = useState('')

  const filteredSymbols = POPULAR_SYMBOLS.filter((s) =>
    s.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <div className="w-64 bg-[#1e222d] border-r border-[#2b2b43] flex flex-col">
      {/* Search */}
      <div className="p-4 border-b border-[#2b2b43]">
        <input
          type="text"
          placeholder="Search symbol..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full bg-[#131722] text-white text-sm px-3 py-2 rounded border border-[#2b2b43] focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Symbol List */}
      <div className="flex-1 overflow-y-auto">
        {filteredSymbols.map((s) => (
          <button
            key={s}
            onClick={() => setSymbol(s)}
            className={cn(
              'w-full px-4 py-3 text-left text-sm transition-colors border-l-2',
              symbol === s
                ? 'bg-[#2b2b43] text-white border-blue-500'
                : 'text-gray-400 hover:bg-[#2b2b43] hover:text-white border-transparent'
            )}
          >
            <div className="font-medium">{s}</div>
            <div className="text-xs text-gray-500">Binance</div>
          </button>
        ))}
      </div>
    </div>
  )
}
