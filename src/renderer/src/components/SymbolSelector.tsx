import { useState, useEffect } from 'react'
import { useTradingStore } from '../store/useTradingStore'
import { cn } from '../lib/utils'

interface Symbol {
  symbol: string
  baseAsset: string
  quoteAsset: string
  status: string
}

export default function SymbolSelector() {
  const { symbol, setSymbol } = useTradingStore()
  const [searchQuery, setSearchQuery] = useState('')
  const [symbols, setSymbols] = useState<Symbol[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchSymbols()
  }, [])

  const fetchSymbols = async () => {
    setIsLoading(true)
    setError('')
    
    try {
      const response = await fetch('http://localhost:8080/api/symbols')
      if (!response.ok) {
        throw new Error('Failed to fetch symbols')
      }
      const data = await response.json()
      
      // Convert string array to Symbol objects
      const symbolObjects = data.symbols.map((sym: string) => ({
        symbol: sym,
        baseAsset: sym.replace(/USDT$|BUSD$|BTC$|ETH$/, ''),
        quoteAsset: sym.includes('USDT') ? 'USDT' : sym.includes('BUSD') ? 'BUSD' : 'BTC',
        status: 'TRADING'
      }))
      
      setSymbols(symbolObjects)
    } catch (error) {
      console.error('Failed to fetch symbols:', error)
      setError('Failed to load symbols')
    } finally {
      setIsLoading(false)
    }
  }

  const filteredSymbols = symbols.filter((s) =>
    s.symbol.toLowerCase().includes(searchQuery.toLowerCase())
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
        {isLoading ? (
          <div className="p-4 text-center">
            <p className="text-gray-400 text-sm">Loading symbols...</p>
          </div>
        ) : error ? (
          <div className="p-4 text-center">
            <p className="text-red-400 text-sm">{error}</p>
            <button 
              onClick={fetchSymbols}
              className="mt-2 text-xs text-blue-400 hover:text-blue-300"
            >
              Retry
            </button>
          </div>
        ) : filteredSymbols.length === 0 ? (
          <div className="p-4 text-center">
            <p className="text-gray-400 text-sm">No symbols found</p>
          </div>
        ) : (
          filteredSymbols.map((s) => (
            <button
              key={s.symbol}
              onClick={() => setSymbol(s.symbol)}
              className={cn(
                'w-full px-4 py-3 text-left text-sm transition-colors border-l-2',
                symbol === s.symbol
                  ? 'bg-[#2b2b43] text-white border-blue-500'
                  : 'text-gray-400 hover:bg-[#2b2b43] hover:text-white border-transparent'
              )}
            >
              <div className="font-medium">{s.symbol}</div>
              <div className="text-xs text-gray-500">
                {s.baseAsset}/{s.quoteAsset} • Binance
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  )
}
