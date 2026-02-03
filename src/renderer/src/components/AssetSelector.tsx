import { useState } from 'react'
import { useMultiAssetStore } from '../store/useMultiAssetStore'
import { ASSETS, getPopularPairs, getAssetBySymbol } from '../config/assets'
import { ChevronDown, Search, Star, TrendingUp } from 'lucide-react'

// Create a simple icon component for SVG
const CryptoIcon = ({ icon, symbol, size = 20 }: { icon: string; symbol: string; size?: number }) => (
  <img 
    src={icon} 
    alt={symbol}
    style={{ width: size, height: size }}
    className="rounded-full"
  />
)

export default function AssetSelector() {
  const { 
    currentPair, 
    selectedBaseAsset, 
    selectedQuoteAsset, 
    setCurrentPair,
    setSelectedAssets,
    prices 
  } = useMultiAssetStore()
  
  const [showAssetSelector, setShowAssetSelector] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [activeTab, setActiveTab] = useState<'popular' | 'crypto' | 'stablecoin' | 'gold'>('popular')

  const filteredAssets = ASSETS.filter(asset => {
    const matchesSearch = asset.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         asset.symbol.toLowerCase().includes(searchTerm.toLowerCase())
    
    if (activeTab === 'popular') {
      const popularSymbols = ['BTC', 'ETH', 'BNB', 'SOL', 'ADA', 'XRP', 'DOT', 'DOGE', 'MATIC', 'PAXG']
      return matchesSearch && popularSymbols.includes(asset.symbol)
    }
    
    return matchesSearch && asset.type === activeTab
  })

  const handleAssetSelect = (asset: string) => {
    if (!selectedBaseAsset) {
      setSelectedAssets(asset, selectedQuoteAsset || 'USDT')
    } else if (!selectedQuoteAsset) {
      setSelectedAssets(selectedBaseAsset, asset)
    } else {
      setSelectedAssets(asset, 'USDT')
    }
    setShowAssetSelector(false)
  }

  const handlePairSelect = (pairSymbol: string) => {
    setCurrentPair(pairSymbol)
    setShowAssetSelector(false)
  }

  const getCurrentPrice = () => {
    const priceData = prices[currentPair.symbol]
    return priceData?.price || 0
  }

  const getPriceChange = () => {
    const priceData = prices[currentPair.symbol]
    return priceData?.change24h || 0
  }

  return (
    <div className="relative">
      {/* Current Pair Display */}
      <div 
        className="flex items-center gap-2 bg-[#1E222D] px-3 py-2 rounded-lg cursor-pointer hover:bg-[#2B2B43] transition-colors"
        onClick={() => setShowAssetSelector(!showAssetSelector)}
      >
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2">
            {getAssetBySymbol(currentPair.baseAsset) && (
              <CryptoIcon 
                icon={getAssetBySymbol(currentPair.baseAsset)!.icon} 
                symbol={currentPair.baseAsset}
                size={20}
              />
            )}
            <span className="text-white font-bold">{currentPair.baseAsset}</span>
          </div>
          <span className="text-gray-400">/</span>
          <div className="flex items-center gap-2">
            {getAssetBySymbol(currentPair.quoteAsset) && (
              <CryptoIcon 
                icon={getAssetBySymbol(currentPair.quoteAsset)!.icon} 
                symbol={currentPair.quoteAsset}
                size={20}
              />
            )}
            <span className="text-gray-300">{currentPair.quoteAsset}</span>
          </div>
        </div>
        
        <div className="flex-1 text-right">
          <div className="text-white font-semibold">
            ${getCurrentPrice().toFixed(getCurrentPrice() < 1 ? 4 : 2)}
          </div>
          <div className={`text-xs ${getPriceChange() >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {getPriceChange() >= 0 ? '+' : ''}{getPriceChange().toFixed(2)}%
          </div>
        </div>
        
        <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${showAssetSelector ? 'rotate-180' : ''}`} />
      </div>

      {/* Asset Selector Modal */}
      {showAssetSelector && (
        <div className="absolute top-full left-0 right-0 mt-2 bg-[#1E222D] border border-[#2B2B43] rounded-lg shadow-xl z-50 max-h-96 overflow-hidden">
          {/* Search */}
          <div className="p-3 border-b border-[#2B2B43]">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search assets..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full bg-[#131722] text-white pl-10 pr-3 py-2 rounded border border-[#2B2B43] focus:outline-none focus:border-[#2962FF]"
              />
            </div>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-[#2B2B43]">
            {[
              { key: 'popular', label: 'Popular', icon: Star },
              { key: 'crypto', label: 'Crypto', icon: TrendingUp },
              { key: 'stablecoin', label: 'Stable', icon: '💵' },
              { key: 'gold', label: 'Gold', icon: '🪙' }
            ].map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setActiveTab(key as any)}
                className={`flex-1 py-2 text-xs font-medium transition-colors ${
                  activeTab === key
                    ? 'bg-[#2962FF] text-white'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                {typeof Icon === 'string' ? Icon : <Icon className="w-3 h-3 mx-auto" />}
                <span className="ml-1">{label}</span>
              </button>
            ))}
          </div>

          {/* Asset List */}
          <div className="max-h-64 overflow-y-auto">
            {activeTab === 'popular' ? (
              // Popular pairs
              <div>
                {getPopularPairs().map(pair => {
                  const priceData = prices[pair.symbol]
                  return (
                    <div
                      key={pair.symbol}
                      onClick={() => handlePairSelect(pair.symbol)}
                      className="flex items-center justify-between p-3 hover:bg-[#2B2B43] cursor-pointer transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <div className="flex items-center gap-2">
                          {getAssetBySymbol(pair.baseAsset) && (
                            <CryptoIcon 
                              icon={getAssetBySymbol(pair.baseAsset)!.icon} 
                              symbol={pair.baseAsset}
                              size={16}
                            />
                          )}
                          <span className="text-white font-medium">{pair.baseAsset}</span>
                        </div>
                        <span className="text-gray-400">/</span>
                        <div className="flex items-center gap-2">
                          {getAssetBySymbol(pair.quoteAsset) && (
                            <CryptoIcon 
                              icon={getAssetBySymbol(pair.quoteAsset)!.icon} 
                              symbol={pair.quoteAsset}
                              size={16}
                            />
                          )}
                          <span className="text-gray-300">{pair.quoteAsset}</span>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-white text-sm">
                          ${priceData?.price?.toFixed(priceData?.price < 1 ? 4 : 2) || '0.00'}
                        </div>
                        <div className={`text-xs ${priceData?.change24h >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {priceData?.change24h >= 0 ? '+' : ''}{priceData?.change24h?.toFixed(2) || '0.00'}%
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : (
              // Individual assets
              <div>
                {filteredAssets.map(asset => {
                  const balance = useMultiAssetStore.getState().getBalance(asset.symbol)
                  const priceData = prices[`${asset.symbol}USDT`]
                  
                  return (
                    <div
                      key={asset.symbol}
                      onClick={() => handleAssetSelect(asset.symbol)}
                      className="flex items-center justify-between p-3 hover:bg-[#2B2B43] cursor-pointer transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <CryptoIcon icon={asset.icon} symbol={asset.symbol} size={24} />
                        <div>
                          <div className="text-white font-medium">{asset.symbol}</div>
                          <div className="text-xs text-gray-400">{asset.name}</div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-white text-sm">
                          ${priceData?.price?.toFixed(priceData?.price < 1 ? 4 : 2) || '0.00'}
                        </div>
                        {balance && (
                          <div className="text-xs text-gray-400">
                            {parseFloat(balance.free).toFixed(asset.decimals)} {asset.symbol}
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
