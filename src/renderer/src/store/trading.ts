import { create } from 'zustand'

interface PriceData {
  symbol: string
  price: string
  timestamp: number
}

interface Balance {
  asset: string
  free: string
  locked: string
}

interface TradingStore {
  // Price data
  currentPrice: PriceData | null
  priceHistory: PriceData[]
  
  // Balance
  balances: Balance[]
  
  // WebSocket connection status
  isConnected: boolean
  
  // Actions
  setPrice: (data: PriceData) => void
  addPriceToHistory: (data: PriceData) => void
  setBalances: (balances: Balance[]) => void
  setConnected: (connected: boolean) => void
  clearHistory: () => void
}

export const useTradingStore = create<TradingStore>((set) => ({
  // Initial state
  currentPrice: null,
  priceHistory: [],
  balances: [],
  isConnected: false,

  // Actions
  setPrice: (data) =>
    set({ currentPrice: data }),

  addPriceToHistory: (data) =>
    set((state) => ({
      priceHistory: [...state.priceHistory.slice(-1000), data] // Keep last 1000 points
    })),

  setBalances: (balances) =>
    set({ balances }),

  setConnected: (connected) =>
    set({ isConnected: connected }),

  clearHistory: () =>
    set({ priceHistory: [] })
}))
