import { BarChart3 } from 'lucide-react'
import { useTradingStore } from '../store/useTradingStore'
import { getAssetBySymbol } from '../config/assets'

// Import crypto icons for common symbols
import btcIcon from 'cryptocurrency-icons/svg/color/btc.svg'
import ethIcon from 'cryptocurrency-icons/svg/color/eth.svg'
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
import { formatPrice, formatPercent } from '../lib/utils'
import { 
  Search, 
  Clock, 
  TrendingUp,
  Settings,
  User,
  Activity,
  DollarSign,
  ArrowUpRight,
  ArrowDownRight
} from 'lucide-react'
import PriceAlerts from './PriceAlerts'

const TIMEFRAMES = [
  { label: '1m', value: '1m' },
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '1H', value: '1h' },
  { label: '4H', value: '4h' },
  { label: '1D', value: '1d' }
]

export default function TopBar() {
  const { ticker, interval, setInterval, currentPrice, symbol } = useTradingStore()
  
  const getSymbolIcon = (symbol: string) => {
    // Try to get crypto icon from assets config first
    const baseAsset = symbol.replace(/USDT|BUSD|USDC/, '')
    const asset = getAssetBySymbol(baseAsset)
    
    if (asset) {
      return <CryptoIcon icon={asset.icon} symbol={asset.symbol} size={20} />
    }
    
    // Fallback to specific icons
    if (symbol.includes('BTC')) return <CryptoIcon icon={btcIcon} symbol="BTC" size={20} />
    if (symbol.includes('ETH')) return <CryptoIcon icon={ethIcon} symbol="ETH" size={20} />
    if (symbol.includes('GOLD') || symbol.includes('XAU') || symbol.includes('PAXG')) return <CryptoIcon icon={genericIcon} symbol="GOLD" size={20} />
    
    // Default fallback
    return <BarChart3 className="w-5 h-5 text-gray-400" />
  }

  const getSymbolName = (symbol: string) => {
    const names: { [key: string]: string } = {
      'BTCUSDT': 'Bitcoin',
      'ETHUSDT': 'Ethereum',
      'XAUUSDT': 'Gold Ounce',
      'GOLDUSDT': 'Gold Token',
      'SILVERUSDT': 'Silver Ounce'
    }
    return names[symbol] || symbol.replace('USDT', '')
  }

  return (
    <div className="h-16 bg-[#1E222D] border-b border-[#2B2B43]">
      <div className="h-full flex items-center px-3 justify-between">
        {/* Left: Logo & Symbol Info */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-6 h-6 text-[#2962FF]" />
            <span className="text-white font-bold text-sm">24HrTrading</span>
          </div>

          {/* Current Symbol Display */}
          <div className="flex items-center gap-3 bg-[#131722] px-3 py-2 rounded-lg">
            <div className="flex items-center">
              {getSymbolIcon(symbol)}
            </div>
            <div>
              <div className="text-white font-semibold">{symbol}</div>
              <div className="text-gray-500 text-xs">{getSymbolName(symbol)}</div>
            </div>
          </div>

          {/* Symbol Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              placeholder="Search symbols..."
              className="bg-[#131722] text-white text-sm pl-9 pr-4 py-2 rounded w-64 
                       border border-[#2B2B43] focus:outline-none focus:border-[#2962FF] 
                       placeholder-gray-500"
            />
          </div>

          {/* Timeframe Selector */}
          <div className="flex items-center gap-1 bg-[#131722] rounded px-1 py-1">
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

        {/* Center: Enhanced Market Stats */}
        {(ticker || currentPrice > 0) && (
          <div className="flex items-center gap-8">
            {/* Main Price Display */}
            <div className="flex items-baseline gap-3">
              <span className="text-white font-bold text-xl">
                {formatPrice(currentPrice > 0 ? currentPrice : ticker?.price || 0)}
              </span>
              <div className={`flex items-center gap-1 text-sm font-medium ${
                (ticker?.priceChangePercent || 0) >= 0 ? 'text-[#26a69a]' : 'text-[#ef5350]'
              }`}>
                {(ticker?.priceChangePercent || 0) >= 0 ? (
                  <ArrowUpRight className="w-4 h-4" />
                ) : (
                  <ArrowDownRight className="w-4 h-4" />
                )}
                {(ticker?.priceChangePercent || 0) >= 0 ? '+' : ''}
                {formatPercent(ticker?.priceChangePercent || 0)}
              </div>
            </div>

            <div className="h-10 w-px bg-[#2B2B43]" />

            {/* 24h Stats */}
            <div className="grid grid-cols-3 gap-4">
              <div className="flex flex-col">
                <span className="text-[10px] text-gray-500 flex items-center gap-1">
                  <Activity className="w-3 h-3" />
                  24h High
                </span>
                <span className="text-sm text-white font-medium">{formatPrice(ticker?.high24h || 0)}</span>
              </div>

              <div className="flex flex-col">
                <span className="text-[10px] text-gray-500 flex items-center gap-1">
                  <Activity className="w-3 h-3 rotate-180" />
                  24h Low
                </span>
                <span className="text-sm text-white font-medium">{formatPrice(ticker?.low24h || 0)}</span>
              </div>

              <div className="flex flex-col">
                <span className="text-[10px] text-gray-500 flex items-center gap-1">
                  <DollarSign className="w-3 h-3" />
                  24h Volume
                </span>
                <span className="text-sm text-white font-medium">
                  {(ticker?.volume24h || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Right: User Actions */}
        <div className="flex items-center gap-2">
          <button className="p-2 hover:bg-[#2B2B43] rounded-lg transition-colors group">
            <TrendingUp className="w-4 h-4 text-gray-400 group-hover:text-white" />
          </button>
          <PriceAlerts />
          <button className="p-2 hover:bg-[#2B2B43] rounded-lg transition-colors group">
            <Settings className="w-4 h-4 text-gray-400 group-hover:text-white" />
          </button>
          <button className="p-2 hover:bg-[#2B2B43] rounded-lg transition-colors group">
            <User className="w-4 h-4 text-gray-400 group-hover:text-white" />
          </button>
        </div>
      </div>
    </div>
  )
}
