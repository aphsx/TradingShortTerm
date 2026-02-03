import { useState } from 'react'
import { useTradingStore } from '../store/useTradingStore'
import { getAssetBySymbol } from '../config/assets'
import { 
  TrendingUp, 
  Star, 
  Search,
  Grid,
  List,
  Eye,
  BarChart3,
  DollarSign,
  Activity,
  ArrowUpRight,
  ArrowDownRight,
  Flame,
  Crown,
  Gem,
  Coins
} from 'lucide-react'

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

interface MarketData {
  symbol: string
  name: string
  price: number
  change: number
  changePercent: number
  volume: number
  marketCap?: number
  category: 'crypto' | 'gold' | 'silver' | 'platinum' | 'palladium'
  rank?: number
  sparkline?: number[]
}

const MARKET_DATA: MarketData[] = [
  // Top Cryptocurrencies
  { symbol: 'BTCUSDT', name: 'Bitcoin', price: 43250.50, change: 1250.30, changePercent: 2.98, volume: 28500000000, marketCap: 845000000000, category: 'crypto', rank: 1 },
  { symbol: 'ETHUSDT', name: 'Ethereum', price: 2280.75, change: -45.20, changePercent: -1.94, volume: 15200000000, marketCap: 274000000000, category: 'crypto', rank: 2 },
  { symbol: 'BNBUSDT', name: 'Binance Coin', price: 315.40, change: 8.75, changePercent: 2.85, volume: 1200000000, marketCap: 48000000000, category: 'crypto', rank: 3 },
  { symbol: 'SOLUSDT', name: 'Solana', price: 98.45, change: 5.32, changePercent: 5.71, volume: 2800000000, marketCap: 42000000000, category: 'crypto', rank: 4 },
  { symbol: 'XRPUSDT', name: 'Ripple', price: 0.6234, change: -0.0123, changePercent: -1.93, volume: 1800000000, marketCap: 34000000000, category: 'crypto', rank: 5 },
  
  // Gold & Precious Metals
  { symbol: 'XAUUSDT', name: 'Gold Ounce', price: 2035.80, change: 15.40, changePercent: 0.76, volume: 850000000, marketCap: 12500000000000, category: 'gold', rank: 1 },
  { symbol: 'GOLDUSDT', name: 'Gold Token', price: 2035.80, change: 15.40, changePercent: 0.76, volume: 450000000, category: 'gold' },
  { symbol: 'SILVERUSDT', name: 'Silver Ounce', price: 23.45, change: 0.85, changePercent: 3.76, volume: 320000000, marketCap: 1400000000000, category: 'silver', rank: 1 },
  { symbol: 'PLATINUMUSDT', name: 'Platinum Ounce', price: 945.60, change: 8.90, changePercent: 0.95, volume: 180000000, marketCap: 280000000000, category: 'platinum', rank: 1 },
  { symbol: 'PALLADIUMUSDT', name: 'Palladium Ounce', price: 1125.40, change: -12.30, changePercent: -1.08, volume: 95000000, marketCap: 120000000000, category: 'palladium', rank: 1 },
  
  // Popular Altcoins
  { symbol: 'ADAUSDT', name: 'Cardano', price: 0.4567, change: 0.0234, changePercent: 5.40, volume: 450000000, marketCap: 16000000000, category: 'crypto', rank: 8 },
  { symbol: 'DOGEUSDT', name: 'Dogecoin', price: 0.0823, change: 0.0045, changePercent: 5.78, volume: 680000000, marketCap: 11800000000, category: 'crypto', rank: 9 },
  { symbol: 'MATICUSDT', name: 'Polygon', price: 0.8945, change: -0.0321, changePercent: -3.46, volume: 320000000, marketCap: 8300000000, category: 'crypto', rank: 10 },
  { symbol: 'SHIBUSDT', name: 'Shiba Inu', price: 0.00000985, change: 0.00000045, changePercent: 4.79, volume: 280000000, marketCap: 5800000000, category: 'crypto' },
  { symbol: 'PEPEUSDT', name: 'Pepe', price: 0.00000123, change: 0.00000008, changePercent: 6.95, volume: 180000000, marketCap: 5200000000, category: 'crypto' },
  { symbol: 'ARBUSDT', name: 'Arbitrum', price: 1.845, change: 0.085, changePercent: 4.83, volume: 420000000, marketCap: 2400000000, category: 'crypto' },
  { symbol: 'OPUSDT', name: 'Optimism', price: 2.345, change: -0.098, changePercent: -4.01, volume: 380000000, marketCap: 2500000000, category: 'crypto' },
  { symbol: 'AAVEUSDT', name: 'Aave', price: 95.40, change: 3.25, changePercent: 3.52, volume: 290000000, marketCap: 1400000000, category: 'crypto' },
  { symbol: 'LINKUSDT', name: 'Chainlink', price: 14.85, change: 0.45, changePercent: 3.12, volume: 510000000, marketCap: 8700000000, category: 'crypto' },
  { symbol: 'UNIUSDT', name: 'Uniswap', price: 6.75, change: -0.23, changePercent: -3.29, volume: 260000000, marketCap: 4000000000, category: 'crypto' },
  { symbol: 'LTCUSDT', name: 'Litecoin', price: 72.45, change: 1.85, changePercent: 2.62, volume: 420000000, marketCap: 5300000000, category: 'crypto' },
  { symbol: 'ATOMUSDT', name: 'Cosmos', price: 9.85, change: -0.34, changePercent: -3.34, volume: 180000000, marketCap: 3600000000, category: 'crypto' },
  { symbol: 'FILUSDT', name: 'Filecoin', price: 5.45, change: 0.23, changePercent: 4.40, volume: 220000000, marketCap: 3000000000, category: 'crypto' },
  { symbol: 'AVAXUSDT', name: 'Avalanche', price: 37.85, change: 1.45, changePercent: 3.98, volume: 480000000, marketCap: 14000000000, category: 'crypto' },
  { symbol: 'DOTUSDT', name: 'Polkadot', price: 7.85, change: -0.25, changePercent: -3.09, volume: 310000000, marketCap: 9800000000, category: 'crypto' }
]

export default function MarketOverview() {
  const { symbol: currentSymbol, setSymbol } = useTradingStore()
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')

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
  const [sortBy, setSortBy] = useState<'marketCap' | 'volume' | 'change'>('marketCap')
  const [watchlist, setWatchlist] = useState<string[]>([])

  const categories = [
    { id: 'all', name: 'All Markets', icon: BarChart3, color: 'text-blue-400' },
    { id: 'crypto', name: 'Cryptocurrency', icon: Coins, color: 'text-orange-400' },
    { id: 'gold', name: 'Gold', icon: Crown, color: 'text-yellow-400' },
    { id: 'silver', name: 'Silver', icon: Gem, color: 'text-gray-400' },
    { id: 'platinum', name: 'Platinum', icon: Gem, color: 'text-purple-400' },
    { id: 'palladium', name: 'Palladium', icon: Gem, color: 'text-indigo-400' }
  ]

  const filteredData = MARKET_DATA.filter(item => {
    const matchesSearch = item.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         item.name.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesCategory = selectedCategory === 'all' || item.category === selectedCategory
    return matchesSearch && matchesCategory
  }).sort((a, b) => {
    switch (sortBy) {
      case 'marketCap':
        return (b.marketCap || 0) - (a.marketCap || 0)
      case 'volume':
        return b.volume - a.volume
      case 'change':
        return b.changePercent - a.changePercent
      default:
        return 0
    }
  })

  const toggleWatchlist = (symbol: string) => {
    setWatchlist(prev => 
      prev.includes(symbol) 
        ? prev.filter(s => s !== symbol)
        : [...prev, symbol]
    )
  }

  const formatPrice = (price: number) => {
    if (price >= 1000) return `$${price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    if (price >= 1) return `$${price.toFixed(4)}`
    if (price >= 0.01) return `$${price.toFixed(6)}`
    return `$${price.toFixed(8)}`
  }

  const formatMarketCap = (marketCap: number) => {
    if (marketCap >= 1e12) return `$${(marketCap / 1e12).toFixed(2)}T`
    if (marketCap >= 1e9) return `$${(marketCap / 1e9).toFixed(2)}B`
    if (marketCap >= 1e6) return `$${(marketCap / 1e6).toFixed(2)}M`
    return `$${marketCap.toLocaleString()}`
  }

  const formatVolume = (volume: number) => {
    if (volume >= 1e9) return `$${(volume / 1e9).toFixed(2)}B`
    if (volume >= 1e6) return `$${(volume / 1e6).toFixed(2)}M`
    return `$${volume.toLocaleString()}`
  }

  return (
    <div className="h-full bg-[#131722] flex flex-col">
      {/* Header */}
      <div className="bg-[#1E222D] border-b border-[#2B2B43] px-6 py-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <BarChart3 className="w-6 h-6 text-[#2962FF]" />
            <h1 className="text-xl font-bold text-white">Market Overview</h1>
            <span className="text-sm text-gray-400">({filteredData.length} assets)</span>
          </div>
          
          <div className="flex items-center gap-3">
            {/* View Mode Toggle */}
            <div className="flex bg-[#131722] rounded-lg p-1">
              <button
                onClick={() => setViewMode('grid')}
                className={`p-2 rounded ${viewMode === 'grid' ? 'bg-[#2962FF] text-white' : 'text-gray-400 hover:text-white'}`}
              >
                <Grid className="w-4 h-4" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`p-2 rounded ${viewMode === 'list' ? 'bg-[#2962FF] text-white' : 'text-gray-400 hover:text-white'}`}
              >
                <List className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-4">
          {/* Search */}
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              placeholder="Search assets..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[#131722] text-white text-sm pl-10 pr-4 py-2 rounded-lg 
                       border border-[#2B2B43] focus:outline-none focus:border-[#2962FF] 
                       placeholder-gray-500"
            />
          </div>

          {/* Category Filter */}
          <div className="flex gap-2">
            {categories.map(category => {
              const Icon = category.icon
              return (
                <button
                  key={category.id}
                  onClick={() => setSelectedCategory(category.id)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors ${
                    selectedCategory === category.id
                      ? 'bg-[#2962FF] text-white'
                      : 'bg-[#131722] text-gray-400 hover:text-white hover:bg-[#2B2B43]'
                  }`}
                >
                  <Icon className={`w-4 h-4 ${selectedCategory === category.id ? 'text-white' : category.color}`} />
                  <span className="text-sm font-medium">{category.name}</span>
                </button>
              )
            })}
          </div>

          {/* Sort */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="bg-[#131722] text-white text-sm px-3 py-2 rounded-lg 
                     border border-[#2B2B43] focus:outline-none focus:border-[#2962FF]"
          >
            <option value="marketCap">Market Cap</option>
            <option value="volume">Volume</option>
            <option value="change">Top Gainers</option>
          </select>
        </div>
      </div>

      {/* Market Stats Summary */}
      <div className="bg-[#1E222D] border-b border-[#2B2B43] px-6 py-3">
        <div className="grid grid-cols-4 gap-4">
          <div className="flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-blue-400" />
            <span className="text-xs text-gray-400">Total Market Cap:</span>
            <span className="text-sm text-white font-semibold">
              {formatMarketCap(filteredData.reduce((sum, item) => sum + (item.marketCap || 0), 0))}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-green-400" />
            <span className="text-xs text-gray-400">24h Volume:</span>
            <span className="text-sm text-white font-semibold">
              {formatVolume(filteredData.reduce((sum, item) => sum + item.volume, 0))}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Flame className="w-4 h-4 text-orange-400" />
            <span className="text-xs text-gray-400">Top Gainer:</span>
            <span className="text-sm text-green-400 font-semibold">
              {filteredData.reduce((max, item) => item.changePercent > max.changePercent ? item : max, filteredData[0])?.symbol || 'N/A'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-purple-400" />
            <span className="text-xs text-gray-400">Active Assets:</span>
            <span className="text-sm text-white font-semibold">{filteredData.length}</span>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {viewMode === 'grid' ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filteredData.map((item) => (
              <div
                key={item.symbol}
                className="bg-[#1E222D] border border-[#2B2B43] rounded-lg p-4 hover:border-[#2962FF] transition-all cursor-pointer group"
                onClick={() => setSymbol(item.symbol)}
              >
                {/* Header */}
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 flex items-center justify-center">
                      {getSymbolIcon(item.symbol, 32)}
                    </div>
                    <div>
                      <div className="text-white font-semibold text-sm">{item.symbol}</div>
                      <div className="text-gray-500 text-xs">{item.name}</div>
                    </div>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      toggleWatchlist(item.symbol)
                    }}
                    className="opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <Star
                      className={`w-4 h-4 ${
                        watchlist.includes(item.symbol)
                          ? 'fill-yellow-500 text-yellow-500'
                          : 'text-gray-500 hover:text-yellow-500'
                      }`}
                    />
                  </button>
                </div>

                {/* Price */}
                <div className="mb-3">
                  <div className="text-white font-bold text-lg">{formatPrice(item.price)}</div>
                  <div className={`flex items-center gap-1 text-sm font-medium ${
                    item.changePercent >= 0 ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {item.changePercent >= 0 ? (
                      <ArrowUpRight className="w-3 h-3" />
                    ) : (
                      <ArrowDownRight className="w-3 h-3" />
                    )}
                    {item.changePercent >= 0 ? '+' : ''}{item.changePercent.toFixed(2)}%
                  </div>
                </div>

                {/* Stats */}
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Volume</span>
                    <span className="text-white">{formatVolume(item.volume)}</span>
                  </div>
                  {item.marketCap && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">Market Cap</span>
                      <span className="text-white">{formatMarketCap(item.marketCap)}</span>
                    </div>
                  )}
                </div>

                {/* Category Badge */}
                <div className="mt-3">
                  <span className={`text-xs px-2 py-1 rounded ${
                    item.category === 'gold' ? 'bg-yellow-500/20 text-yellow-400' :
                    item.category === 'silver' ? 'bg-gray-500/20 text-gray-400' :
                    item.category === 'platinum' ? 'bg-purple-500/20 text-purple-400' :
                    item.category === 'palladium' ? 'bg-indigo-500/20 text-indigo-400' :
                    'bg-orange-500/20 text-orange-400'
                  }`}>
                    {item.category.charAt(0).toUpperCase() + item.category.slice(1)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="bg-[#1E222D] border border-[#2B2B43] rounded-lg overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[#2B2B43]">
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-400">#</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-400">Asset</th>
                  <th className="text-right px-4 py-3 text-xs font-medium text-gray-400">Price</th>
                  <th className="text-right px-4 py-3 text-xs font-medium text-gray-400">24h Change</th>
                  <th className="text-right px-4 py-3 text-xs font-medium text-gray-400">Volume</th>
                  <th className="text-right px-4 py-3 text-xs font-medium text-gray-400">Market Cap</th>
                  <th className="text-center px-4 py-3 text-xs font-medium text-gray-400">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredData.map((item, index) => (
                  <tr
                    key={item.symbol}
                    className="border-b border-[#2B2B43] hover:bg-[#2B2B43]/50 cursor-pointer"
                    onClick={() => setSymbol(item.symbol)}
                  >
                    <td className="px-4 py-3 text-sm text-gray-400">{item.rank || index + 1}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 flex items-center justify-center">
                          {getSymbolIcon(item.symbol, 24)}
                        </div>
                        <div>
                          <div className="text-white font-medium text-sm">{item.symbol}</div>
                          <div className="text-gray-500 text-xs">{item.name}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right text-sm text-white font-medium">
                      {formatPrice(item.price)}
                    </td>
                    <td className={`px-4 py-3 text-right text-sm font-medium ${
                      item.changePercent >= 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {item.changePercent >= 0 ? '+' : ''}{item.changePercent.toFixed(2)}%
                    </td>
                    <td className="px-4 py-3 text-right text-sm text-white">
                      {formatVolume(item.volume)}
                    </td>
                    <td className="px-4 py-3 text-right text-sm text-white">
                      {item.marketCap ? formatMarketCap(item.marketCap) : 'N/A'}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div className="flex items-center justify-center gap-2">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            toggleWatchlist(item.symbol)
                          }}
                          className="p-1 hover:bg-[#2B2B43] rounded"
                        >
                          <Star
                            className={`w-4 h-4 ${
                              watchlist.includes(item.symbol)
                                ? 'fill-yellow-500 text-yellow-500'
                                : 'text-gray-500 hover:text-yellow-500'
                            }`}
                          />
                        </button>
                        <button className="p-1 hover:bg-[#2B2B43] rounded">
                          <Eye className="w-4 h-4 text-gray-500 hover:text-white" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
