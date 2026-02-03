// Asset configuration for multi-asset trading system

// Import SVG icons directly
import btcIcon from 'cryptocurrency-icons/svg/color/btc.svg'
import ethIcon from 'cryptocurrency-icons/svg/color/eth.svg'
import bnbIcon from 'cryptocurrency-icons/svg/color/bnb.svg'
import solIcon from 'cryptocurrency-icons/svg/color/sol.svg'
import adaIcon from 'cryptocurrency-icons/svg/color/ada.svg'
import xrpIcon from 'cryptocurrency-icons/svg/color/xrp.svg'
import dotIcon from 'cryptocurrency-icons/svg/color/dot.svg'
import dogeIcon from 'cryptocurrency-icons/svg/color/doge.svg'
import maticIcon from 'cryptocurrency-icons/svg/color/matic.svg'
import usdtIcon from 'cryptocurrency-icons/svg/color/usdt.svg'
import usdcIcon from 'cryptocurrency-icons/svg/color/usdc.svg'

// For icons that don't exist in the library, use generic ones
import genericIcon from 'cryptocurrency-icons/svg/color/generic.svg'

export interface Asset {
  symbol: string
  name: string
  icon: string // SVG path
  type: 'crypto' | 'stablecoin' | 'gold'
  decimals: number
  minOrderSize: number
  stepSize: number
  isActive: boolean
  brandColor?: string
}

export interface TradingPair {
  symbol: string
  baseAsset: string
  quoteAsset: string
  isActive: boolean
}

// Popular cryptocurrencies (9 coins) + 1 gold-backed
export const ASSETS: Asset[] = [
  // Major Cryptocurrencies
  {
    symbol: 'BTC',
    name: 'Bitcoin',
    icon: btcIcon,
    type: 'crypto',
    decimals: 8,
    minOrderSize: 0.00001,
    stepSize: 0.00001,
    isActive: true,
    brandColor: '#F7931A'
  },
  {
    symbol: 'ETH',
    name: 'Ethereum',
    icon: ethIcon,
    type: 'crypto',
    decimals: 8,
    minOrderSize: 0.0001,
    stepSize: 0.0001,
    isActive: true,
    brandColor: '#627EEA'
  },
  {
    symbol: 'BNB',
    name: 'Binance Coin',
    icon: bnbIcon,
    type: 'crypto',
    decimals: 8,
    minOrderSize: 0.001,
    stepSize: 0.001,
    isActive: true,
    brandColor: '#F3BA2F'
  },
  {
    symbol: 'SOL',
    name: 'Solana',
    icon: solIcon,
    type: 'crypto',
    decimals: 8,
    minOrderSize: 0.01,
    stepSize: 0.01,
    isActive: true,
    brandColor: '#00FFA3'
  },
  {
    symbol: 'ADA',
    name: 'Cardano',
    icon: adaIcon,
    type: 'crypto',
    decimals: 8,
    minOrderSize: 0.1,
    stepSize: 0.1,
    isActive: true,
    brandColor: '#0033AD'
  },
  {
    symbol: 'XRP',
    name: 'Ripple',
    icon: xrpIcon,
    type: 'crypto',
    decimals: 8,
    minOrderSize: 0.1,
    stepSize: 0.1,
    isActive: true,
    brandColor: '#23292F'
  },
  {
    symbol: 'DOT',
    name: 'Polkadot',
    icon: dotIcon,
    type: 'crypto',
    decimals: 8,
    minOrderSize: 0.1,
    stepSize: 0.1,
    isActive: true,
    brandColor: '#E6007A'
  },
  {
    symbol: 'DOGE',
    name: 'Dogecoin',
    icon: dogeIcon,
    type: 'crypto',
    decimals: 8,
    minOrderSize: 1,
    stepSize: 1,
    isActive: true,
    brandColor: '#C2A633'
  },
  {
    symbol: 'MATIC',
    name: 'Polygon',
    icon: maticIcon,
    type: 'crypto',
    decimals: 8,
    minOrderSize: 0.1,
    stepSize: 0.1,
    isActive: true,
    brandColor: '#8247E5'
  },
  // Gold-backed cryptocurrency
  {
    symbol: 'PAXG',
    name: 'PAX Gold',
    icon: genericIcon, // Use generic icon since paxg doesn't exist
    type: 'gold',
    decimals: 8,
    minOrderSize: 0.001,
    stepSize: 0.001,
    isActive: true,
    brandColor: '#D4A017'
  },
  // Stablecoins for trading
  {
    symbol: 'USDT',
    name: 'Tether',
    icon: usdtIcon,
    type: 'stablecoin',
    decimals: 8,
    minOrderSize: 1,
    stepSize: 1,
    isActive: true,
    brandColor: '#26A17B'
  },
  {
    symbol: 'BUSD',
    name: 'Binance USD',
    icon: genericIcon, // Use generic icon since busd doesn't exist
    type: 'stablecoin',
    decimals: 8,
    minOrderSize: 1,
    stepSize: 1,
    isActive: true,
    brandColor: '#F3BA2F'
  },
  {
    symbol: 'USDC',
    name: 'USD Coin',
    icon: usdcIcon,
    type: 'stablecoin',
    decimals: 8,
    minOrderSize: 1,
    stepSize: 1,
    isActive: true,
    brandColor: '#2775CA'
  }
]

// Generate all possible trading pairs
export const generateTradingPairs = (): TradingPair[] => {
  const pairs: TradingPair[] = []
  const activeAssets = ASSETS.filter(asset => asset.isActive)
  
  // Create pairs with stablecoins as quote
  const stablecoins = activeAssets.filter(asset => asset.type === 'stablecoin')
  const tradeableAssets = activeAssets.filter(asset => asset.type !== 'stablecoin')
  
  tradeableAssets.forEach(base => {
    stablecoins.forEach(quote => {
      if (base.symbol !== quote.symbol) {
        pairs.push({
          symbol: `${base.symbol}${quote.symbol}`,
          baseAsset: base.symbol,
          quoteAsset: quote.symbol,
          isActive: true
        })
      }
    })
  })
  
  // Add some crypto-to-crypto pairs
  const majorCryptos = activeAssets.filter(asset => 
    ['BTC', 'ETH', 'BNB'].includes(asset.symbol)
  )
  
  majorCryptos.forEach(base => {
    majorCryptos.forEach(quote => {
      if (base.symbol !== quote.symbol && !pairs.find(p => 
        p.symbol === `${base.symbol}${quote.symbol}`
      )) {
        pairs.push({
          symbol: `${base.symbol}${quote.symbol}`,
          baseAsset: base.symbol,
          quoteAsset: quote.symbol,
          isActive: true
        })
      }
    })
  })
  
  return pairs.sort((a, b) => a.symbol.localeCompare(b.symbol))
}

export const TRADING_PAIRS = generateTradingPairs()

// Helper functions
export const getAssetBySymbol = (symbol: string): Asset | undefined => {
  return ASSETS.find(asset => asset.symbol === symbol)
}

export const getTradingPairBySymbol = (symbol: string): TradingPair | undefined => {
  return TRADING_PAIRS.find(pair => pair.symbol === symbol)
}

export const getPopularPairs = (): TradingPair[] => {
  return TRADING_PAIRS.filter(pair => 
    ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'ADAUSDT', 
     'XRPUSDT', 'DOTUSDT', 'DOGEUSDT', 'MATICUSDT', 'PAXGUSDT',
     'BTCETH', 'ETHBNB'].includes(pair.symbol)
  )
}

export const formatAssetAmount = (symbol: string, amount: number): string => {
  const asset = getAssetBySymbol(symbol)
  if (!asset) return amount.toString()
  
  return amount.toFixed(asset.decimals)
}

export const getMinOrderSize = (symbol: string): number => {
  const asset = getAssetBySymbol(symbol)
  return asset?.minOrderSize || 0.00001
}

export const getStepSize = (symbol: string): number => {
  const asset = getAssetBySymbol(symbol)
  return asset?.stepSize || 0.00001
}
