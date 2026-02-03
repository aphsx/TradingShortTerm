import { create } from 'zustand'
import { Asset, TradingPair, getAssetBySymbol, getTradingPairBySymbol, ASSETS, TRADING_PAIRS } from '../config/assets'

interface Balance {
  asset: string
  free: string
  locked: string
  valueInUSD?: number
}

interface PriceData {
  symbol: string
  price: number
  change24h: number
  high24h: number
  low24h: number
  volume24h: number
  lastUpdate: number
}

interface MultiAssetStore {
  // Current trading pair
  currentPair: TradingPair
  currentSymbol: string
  
  // Asset data
  assets: Asset[]
  tradingPairs: TradingPair[]
  popularPairs: TradingPair[]
  
  // Balance data
  balances: Balance[]
  totalPortfolioValue: number
  
  // Price data
  prices: Record<string, PriceData>
  
  // UI state
  selectedBaseAsset: string
  selectedQuoteAsset: string
  isLoadingBalance: boolean
  isLoadingPrices: boolean
  
  // Actions
  setCurrentPair: (symbol: string) => void
  setSelectedAssets: (base: string, quote: string) => void
  setBalances: (balances: Balance[]) => void
  updatePrice: (symbol: string, priceData: Partial<PriceData>) => void
  setPrices: (prices: Record<string, PriceData>) => void
  setLoadingBalance: (loading: boolean) => void
  setLoadingPrices: (loading: boolean) => void
  
  // Getters
  getCurrentPrice: () => number
  getCurrentBaseAsset: () => Asset | undefined
  getCurrentQuoteAsset: () => Asset | undefined
  getBalance: (asset: string) => Balance | undefined
  getAssetBalance: (asset: string) => number
  getAssetValueInUSD: (asset: string) => number
  canBuy: (amount: number) => boolean
  canSell: (amount: number) => boolean
  getMaxBuyAmount: () => number
  getMaxSellAmount: () => number
}

export const useMultiAssetStore = create<MultiAssetStore>((set, get) => ({
  // Initial state
  currentPair: TRADING_PAIRS[0] || { symbol: 'BTCUSDT', baseAsset: 'BTC', quoteAsset: 'USDT', isActive: true },
  currentSymbol: 'BTCUSDT',
  assets: ASSETS,
  tradingPairs: TRADING_PAIRS,
  popularPairs: TRADING_PAIRS.filter(pair => 
    ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'ADAUSDT', 
     'XRPUSDT', 'DOTUSDT', 'DOGEUSDT', 'MATICUSDT', 'PAXGUSDT'].includes(pair.symbol)
  ),
  
  balances: [],
  totalPortfolioValue: 0,
  prices: {},
  
  selectedBaseAsset: 'BTC',
  selectedQuoteAsset: 'USDT',
  isLoadingBalance: false,
  isLoadingPrices: false,
  
  // Actions
  setCurrentPair: (symbol: string) => {
    const pair = getTradingPairBySymbol(symbol)
    if (pair) {
      set({
        currentPair: pair,
        currentSymbol: symbol,
        selectedBaseAsset: pair.baseAsset,
        selectedQuoteAsset: pair.quoteAsset
      })
    }
  },
  
  setSelectedAssets: (base: string, quote: string) => {
    const pair = getTradingPairBySymbol(`${base}${quote}`)
    if (pair) {
      set({
        selectedBaseAsset: base,
        selectedQuoteAsset: quote,
        currentPair: pair,
        currentSymbol: pair.symbol
      })
    }
  },
  
  setBalances: (balances: Balance[]) => {
    // Calculate USD values for each balance
    const { prices } = get()
    const balancesWithValues = balances.map(balance => {
      let valueInUSD = 0
      
      if (balance.asset === 'USDT' || balance.asset === 'BUSD' || balance.asset === 'USDC') {
        valueInUSD = parseFloat(balance.free) + parseFloat(balance.locked)
      } else {
        const priceData = prices[`${balance.asset}USDT`]
        if (priceData) {
          valueInUSD = (parseFloat(balance.free) + parseFloat(balance.locked)) * priceData.price
        }
      }
      
      return { ...balance, valueInUSD }
    })
    
    const totalValue = balancesWithValues.reduce((sum, balance) => sum + (balance.valueInUSD || 0), 0)
    
    set({
      balances: balancesWithValues,
      totalPortfolioValue: totalValue
    })
  },
  
  updatePrice: (symbol: string, priceData: Partial<PriceData>) => {
    const { prices } = get()
    const currentPriceData = prices[symbol] || {
      symbol,
      price: 0,
      change24h: 0,
      high24h: 0,
      low24h: 0,
      volume24h: 0,
      lastUpdate: Date.now()
    }
    
    const updatedPriceData = { ...currentPriceData, ...priceData, lastUpdate: Date.now() }
    
    set({
      prices: {
        ...prices,
        [symbol]: updatedPriceData
      }
    })
  },
  
  setPrices: (prices: Record<string, PriceData>) => {
    set({ prices })
  },
  
  setLoadingBalance: (loading: boolean) => set({ isLoadingBalance: loading }),
  setLoadingPrices: (loading: boolean) => set({ isLoadingPrices: loading }),
  
  // Getters
  getCurrentPrice: () => {
    const { currentSymbol, prices } = get()
    return prices[currentSymbol]?.price || 0
  },
  
  getCurrentBaseAsset: () => {
    const { selectedBaseAsset } = get()
    return getAssetBySymbol(selectedBaseAsset)
  },
  
  getCurrentQuoteAsset: () => {
    const { selectedQuoteAsset } = get()
    return getAssetBySymbol(selectedQuoteAsset)
  },
  
  getBalance: (asset: string) => {
    const { balances } = get()
    return balances.find(b => b.asset === asset)
  },
  
  getAssetBalance: (asset: string) => {
    const balance = get().getBalance(asset)
    return balance ? parseFloat(balance.free) : 0
  },
  
  getAssetValueInUSD: (asset: string) => {
    const { balances, prices } = get()
    const balance = balances.find(b => b.asset === asset)
    
    if (!balance) return 0
    
    if (asset === 'USDT' || asset === 'BUSD' || asset === 'USDC') {
      return parseFloat(balance.free)
    }
    
    const priceData = prices[`${asset}USDT`]
    if (priceData) {
      return parseFloat(balance.free) * priceData.price
    }
    
    return 0
  },
  
  canBuy: (amount: number) => {
    const { selectedQuoteAsset } = get()
    const quoteBalance = get().getAssetBalance(selectedQuoteAsset)
    const currentPrice = get().getCurrentPrice()
    
    if (currentPrice <= 0) return false
    
    const requiredQuoteAmount = amount * currentPrice
    return quoteBalance >= requiredQuoteAmount
  },
  
  canSell: (amount: number) => {
    const { selectedBaseAsset } = get()
    const baseBalance = get().getAssetBalance(selectedBaseAsset)
    return baseBalance >= amount
  },
  
  getMaxBuyAmount: () => {
    const { selectedQuoteAsset } = get()
    const quoteBalance = get().getAssetBalance(selectedQuoteAsset)
    const currentPrice = get().getCurrentPrice()
    
    if (currentPrice <= 0) return 0
    
    return quoteBalance / currentPrice
  },
  
  getMaxSellAmount: () => {
    const { selectedBaseAsset } = get()
    return get().getAssetBalance(selectedBaseAsset)
  }
}))
