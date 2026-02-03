import { useState } from 'react'
import { useTradingStore } from '../store/useTradingStore'
import { getAssetBySymbol } from '../config/assets'
import { Star, TrendingUp, TrendingDown, Search } from 'lucide-react'

// Import crypto icons
import btcIcon from 'cryptocurrency-icons/svg/color/btc.svg'
import ethIcon from 'cryptocurrency-icons/svg/color/eth.svg'
import bnbIcon from 'cryptocurrency-icons/svg/color/bnb.svg'
import solIcon from 'cryptocurrency-icons/svg/color/sol.svg'
import xrpIcon from 'cryptocurrency-icons/svg/color/xrp.svg'
import adaIcon from 'cryptocurrency-icons/svg/color/ada.svg'
import genericIcon from 'cryptocurrency-icons/svg/color/generic.svg'

// Create a simple icon component for SVG
const CryptoIcon = ({ icon, symbol, size = 20 }: { icon: string; symbol: string; size?: number }) => (
  <img 
    src={icon} 
    alt={symbol}
    style={{ width: size, height: size }}
    className="rounded-full"
  />
)

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
  { symbol: 'MATICUSDT', name: 'Polygon', price: 0.8945, change: -0.0321, changePercent: -3.46 },
  { symbol: 'XAUUSDT', name: 'Gold Ounce', price: 2035.80, change: 15.40, changePercent: 0.76 },
  { symbol: 'GOLDUSDT', name: 'Gold Token', price: 2035.80, change: 15.40, changePercent: 0.76 },
  { symbol: 'SILVERUSDT', name: 'Silver Ounce', price: 23.45, change: 0.85, changePercent: 3.76 },
  { symbol: 'SHIBUSDT', name: 'Shiba Inu', price: 0.00000985, change: 0.00000045, changePercent: 4.79 },
  { symbol: 'PEPEUSDT', name: 'Pepe', price: 0.00000123, change: 0.00000008, changePercent: 6.95 },
  { symbol: 'ARBUSDT', name: 'Arbitrum', price: 1.845, change: 0.085, changePercent: 4.83 },
  { symbol: 'OPUSDT', name: 'Optimism', price: 2.345, change: -0.098, changePercent: -4.01 },
  { symbol: 'AAVEUSDT', name: 'Aave', price: 95.40, change: 3.25, changePercent: 3.52 },
  { symbol: 'LINKUSDT', name: 'Chainlink', price: 14.85, change: 0.45, changePercent: 3.12 },
  { symbol: 'UNIUSDT', name: 'Uniswap', price: 6.75, change: -0.23, changePercent: -3.29 },
  { symbol: 'LTCUSDT', name: 'Litecoin', price: 72.45, change: 1.85, changePercent: 2.62 },
  { symbol: 'ATOMUSDT', name: 'Cosmos', price: 9.85, change: -0.34, changePercent: -3.34 },
  { symbol: 'FILUSDT', name: 'Filecoin', price: 5.45, change: 0.23, changePercent: 4.40 },
  { symbol: 'AVAXUSDT', name: 'Avalanche', price: 37.85, change: 1.45, changePercent: 3.98 },
  { symbol: 'DOTUSDT', name: 'Polkadot', price: 7.85, change: -0.25, changePercent: -3.09 },
  { symbol: 'PLATINUMUSDT', name: 'Platinum Ounce', price: 945.60, change: 8.90, changePercent: 0.95 },
  { symbol: 'PALLADIUMUSDT', name: 'Palladium Ounce', price: 1125.40, change: -12.30, changePercent: -1.08 }
]

export default function WatchlistPanel() {
  const { symbol, setSymbol } = useTradingStore()
  const [searchQuery, setSearchQuery] = useState('')
  const [watchlist, setWatchlist] = useState<string[]>(['BTCUSDT', 'ETHUSDT', 'BNBUSDT'])

  // Helper function to get crypto icon
  const getSymbolIcon = (symbol: string, size = 20) => {
    // Extract base asset from symbol (e.g., BTC from BTCUSDT)
    const baseAsset = symbol.replace(/USDT|BUSD|USDC/, '')
    const asset = getAssetBySymbol(baseAsset)
    
    if (asset) {
      return <CryptoIcon icon={asset.icon} symbol={asset.symbol} size={size} />
    }
    
    // Fallback to specific icons
    if (symbol.includes('BTC')) return <CryptoIcon icon={btcIcon} symbol="BTC" size={size} />
    if (symbol.includes('ETH')) return <CryptoIcon icon={ethIcon} symbol="ETH" size={size} />
    if (symbol.includes('BNB')) return <CryptoIcon icon={bnbIcon} symbol="BNB" size={size} />
    if (symbol.includes('SOL')) return <CryptoIcon icon={solIcon} symbol="SOL" size={size} />
    if (symbol.includes('XRP')) return <CryptoIcon icon={xrpIcon} symbol="XRP" size={size} />
    if (symbol.includes('ADA')) return <CryptoIcon icon={adaIcon} symbol="ADA" size={size} />
    
    // Generic fallback for metals and others
    return <CryptoIcon icon={genericIcon} symbol={baseAsset} size={size} />
  }

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
    <div className="w-72 bg-[#1E222D] border-r border-[#2B2B43] flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2 border-b border-[#2B2B43] flex-shrink-0">
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
      <div className="flex-1 overflow-y-auto scrollbar-hide">
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
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 flex items-center justify-center">
                      {getSymbolIcon(item.symbol, 16)}
                    </div>
                    <div className="text-white text-sm font-medium">{item.symbol}</div>
                  </div>
                  <div className="text-gray-500 text-[10px] truncate">{item.name}</div>
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
                {item.price >= 1000 
                  ? `$${item.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                  : item.price >= 1 
                    ? `$${item.price.toFixed(4)}`
                    : item.price >= 0.01
                      ? `$${item.price.toFixed(6)}`
                      : `$${item.price.toFixed(8)}`
                }
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
