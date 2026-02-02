import { create } from 'zustand'
import type { CandlestickData } from 'lightweight-charts'

// Kline data from backend (matches Go struct)
export interface KlineData {
  symbol: string
  time: number // Unix timestamp in seconds
  open: number
  high: number
  low: number
  close: number
  volume: number
}

// Historical kline from REST API
export interface HistoricalKline {
  openTime: number
  open: string
  high: string
  low: string
  close: string
  volume: string
  closeTime: number
  quoteAssetVolume: string
  numberOfTrades: number
  takerBuyBaseAssetVolume: string
  takerBuyQuoteAssetVolume: string
}

interface MarketStore {
  // WebSocket connection
  ws: WebSocket | null
  isConnected: boolean
  
  // Current symbol and interval
  symbol: string
  interval: string
  
  // Candlestick data
  candleData: Map<number, CandlestickData>
  latestCandle: KlineData | null
  
  // Loading states
  isLoadingHistory: boolean
  historyError: string | null
  
  // Actions
  setSymbol: (symbol: string) => void
  setInterval: (interval: string) => void
  loadHistoricalData: () => Promise<void>
  connectWebSocket: () => void
  disconnectWebSocket: () => void
  updateCandle: (kline: KlineData) => void
  getCandleArray: () => CandlestickData[]
}

const BASE_URL = 'http://localhost:8080'
const WS_URL = 'ws://localhost:8080'

export const useMarketStore = create<MarketStore>((set, get) => ({
  // Initial state
  ws: null,
  isConnected: false,
  symbol: 'BTCUSDT',
  interval: '1m',
  candleData: new Map(),
  latestCandle: null,
  isLoadingHistory: false,
  historyError: null,

  // Set symbol and reload data
  setSymbol: (symbol: string) => {
    const state = get()
    if (state.symbol === symbol) return
    
    // Disconnect old WebSocket
    state.disconnectWebSocket()
    
    // Clear data and set new symbol
    set({ 
      symbol, 
      candleData: new Map(),
      latestCandle: null 
    })
    
    // Load new data
    state.loadHistoricalData().then(() => {
      state.connectWebSocket()
    })
  },

  // Set interval and reload data
  setInterval: (interval: string) => {
    const state = get()
    if (state.interval === interval) return
    
    // Disconnect old WebSocket
    state.disconnectWebSocket()
    
    // Clear data and set new interval
    set({ 
      interval, 
      candleData: new Map(),
      latestCandle: null 
    })
    
    // Load new data
    state.loadHistoricalData().then(() => {
      state.connectWebSocket()
    })
  },

  // Load historical candlestick data from REST API
  loadHistoricalData: async () => {
    const { symbol, interval } = get()
    
    set({ isLoadingHistory: true, historyError: null })
    
    try {
      console.log(`📊 Fetching historical klines for ${symbol} ${interval}...`)
      
      const response = await fetch(
        `${BASE_URL}/api/klines?symbol=${symbol}&interval=${interval}&limit=1000`
      )
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
      
      const klines: HistoricalKline[] = await response.json()
      
      if (!klines || klines.length === 0) {
        throw new Error('No historical data received')
      }
      
      // Convert to CandlestickData format
      const candleMap = new Map<number, CandlestickData>()
      
      klines.forEach((kline) => {
        const time = Math.floor(kline.openTime / 1000) // Convert ms to seconds
        candleMap.set(time, {
          time,
          open: parseFloat(kline.open),
          high: parseFloat(kline.high),
          low: parseFloat(kline.low),
          close: parseFloat(kline.close)
        })
      })
      
      console.log(`✅ Loaded ${candleMap.size} historical candles`)
      
      set({ 
        candleData: candleMap, 
        isLoadingHistory: false,
        historyError: null
      })
      
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown error'
      console.error('❌ Failed to load historical data:', errorMsg)
      set({ 
        isLoadingHistory: false, 
        historyError: errorMsg 
      })
    }
  },

  // Connect to WebSocket for real-time updates
  connectWebSocket: () => {
    const { symbol, interval, ws: existingWs } = get()
    
    // Close existing connection
    if (existingWs) {
      existingWs.close()
    }
    
    try {
      const wsUrl = `${WS_URL}/api/kline?symbol=${symbol}&interval=${interval}`
      console.log(`🔌 Connecting to WebSocket: ${wsUrl}`)
      
      const ws = new WebSocket(wsUrl)
      
      ws.onopen = () => {
        console.log('✅ WebSocket connected')
        set({ isConnected: true, ws })
      }
      
      ws.onmessage = (event) => {
        try {
          const kline: KlineData = JSON.parse(event.data)
          get().updateCandle(kline)
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
        }
      }
      
      ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error)
        set({ isConnected: false })
      }
      
      ws.onclose = () => {
        console.log('🔌 WebSocket disconnected')
        set({ isConnected: false, ws: null })
        
        // Auto-reconnect after 5 seconds
        setTimeout(() => {
          const state = get()
          if (!state.ws && !state.isConnected) {
            console.log('♻️  Attempting to reconnect...')
            state.connectWebSocket()
          }
        }, 5000)
      }
      
    } catch (error) {
      console.error('Failed to create WebSocket:', error)
      set({ isConnected: false, ws: null })
    }
  },

  // Disconnect WebSocket
  disconnectWebSocket: () => {
    const { ws } = get()
    if (ws) {
      ws.close()
      set({ ws: null, isConnected: false })
    }
  },

  // Update or add a candle from WebSocket
  updateCandle: (kline: KlineData) => {
    const { candleData } = get()
    
    // Create a new Map to trigger React re-renders
    const newCandleData = new Map(candleData)
    
    newCandleData.set(kline.time, {
      time: kline.time,
      open: kline.open,
      high: kline.high,
      low: kline.low,
      close: kline.close
    })
    
    set({ 
      candleData: newCandleData,
      latestCandle: kline
    })
  },

  // Get candles as sorted array (for Lightweight Charts)
  getCandleArray: () => {
    const { candleData } = get()
    return Array.from(candleData.values()).sort((a, b) => a.time - b.time)
  }
}))
