import { create } from 'zustand'
import type { Time } from 'lightweight-charts'

export interface CandlestickData {
  time: Time
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface TickerData {
  symbol: string
  price: number
  priceChange: number
  priceChangePercent: number
  high24h: number
  low24h: number
  volume24h: number
}

interface TradingState {
  // Market data
  symbol: string
  interval: string
  candles: Map<number, CandlestickData>
  ticker: TickerData | null
  currentPrice: number // Real-time price from trades
  
  // WebSocket
  ws: WebSocket | null
  priceWs: WebSocket | null // Separate WebSocket for real-time prices
  isConnected: boolean
  isPriceConnected: boolean
  
  // Loading states
  isLoadingHistory: boolean
  
  // Actions
  setSymbol: (symbol: string) => void
  setInterval: (interval: string) => void
  loadHistoricalData: () => Promise<void>
  connectWebSocket: () => void
  connectPriceWebSocket: () => void
  disconnectWebSocket: () => void
  updateCandle: (data: any) => void
  updatePrice: (data: any) => void
  getCandleArray: () => CandlestickData[]
}

export const useTradingStore = create<TradingState>((set, get) => ({
  // Initial state
  symbol: 'BTCUSDT',
  interval: '1m',
  candles: new Map(),
  ticker: null,
  currentPrice: 0,
  ws: null,
  priceWs: null,
  isConnected: false,
  isPriceConnected: false,
  isLoadingHistory: false,

  setSymbol: (symbol: string) => {
    const state = get()
    if (state.symbol === symbol) return
    
    set({ symbol, candles: new Map() })
    state.disconnectWebSocket()
    get().loadHistoricalData()
    get().connectWebSocket()
    get().connectPriceWebSocket()
  },

  setInterval: (interval: string) => {
    const state = get()
    if (state.interval === interval) return
    
    set({ interval, candles: new Map() })
    state.disconnectWebSocket()
    get().loadHistoricalData()
    get().connectWebSocket()
  },

  loadHistoricalData: async () => {
    const { symbol, interval } = get()
    set({ isLoadingHistory: true })

    try {
      const response = await fetch(
        `http://localhost:8080/api/kline?symbol=${symbol}&interval=${interval}&limit=500`
      )
      
      if (!response.ok) {
        throw new Error('Failed to fetch historical data')
      }

      const data = await response.json()
      const candlesMap = new Map<number, CandlestickData>()

      data.forEach((item: any) => {
        const timestamp = Math.floor(item.openTime / 1000)
        candlesMap.set(timestamp, {
          time: timestamp as Time,
          open: parseFloat(item.open),
          high: parseFloat(item.high),
          low: parseFloat(item.low),
          close: parseFloat(item.close),
          volume: parseFloat(item.volume)
        })
      })

      set({ candles: candlesMap })
      console.log('✅ Loaded', candlesMap.size, 'candles for', symbol, interval)
    } catch (error) {
      console.error('❌ Failed to load historical data:', error)
    } finally {
      set({ isLoadingHistory: false })
    }
  },

  connectWebSocket: () => {
    const { symbol, interval, ws } = get()
    
    if (ws?.readyState === WebSocket.OPEN) {
      console.log('⚠️ WebSocket already connected')
      return
    }

    const wsUrl = `ws://localhost:8080/api/kline?symbol=${symbol}&interval=${interval}`
    console.log('🔌 Connecting to WebSocket:', wsUrl)
    
    const newWs = new WebSocket(wsUrl)

    newWs.onopen = () => {
      console.log('✅ WebSocket connected')
      set({ isConnected: true })
    }

    newWs.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        get().updateCandle(data)
      } catch (error) {
        console.error('❌ WebSocket message error:', error)
      }
    }

    newWs.onerror = (error) => {
      console.error('❌ WebSocket error:', error)
      set({ isConnected: false })
    }

    newWs.onclose = () => {
      console.log('🔌 WebSocket disconnected')
      set({ isConnected: false, ws: null })
    }

    set({ ws: newWs })
  },

  connectPriceWebSocket: () => {
    const { symbol, priceWs } = get()
    
    if (priceWs?.readyState === WebSocket.OPEN) {
      console.log('⚠️ Price WebSocket already connected')
      return
    }

    const wsUrl = `ws://localhost:8080/api/price?symbol=${symbol}`
    console.log('🔌 Connecting to Price WebSocket:', wsUrl)
    
    const newPriceWs = new WebSocket(wsUrl)

    newPriceWs.onopen = () => {
      console.log('✅ Price WebSocket connected')
      set({ isPriceConnected: true })
    }

    newPriceWs.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        get().updatePrice(data)
      } catch (error) {
        console.error('❌ Price WebSocket message error:', error)
      }
    }

    newPriceWs.onerror = (error) => {
      console.error('❌ Price WebSocket error:', error)
      set({ isPriceConnected: false })
    }

    newPriceWs.onclose = () => {
      console.log('🔌 Price WebSocket disconnected')
      set({ isPriceConnected: false, priceWs: null })
    }

    set({ priceWs: newPriceWs })
  },

  disconnectWebSocket: () => {
    const { ws, priceWs } = get()
    if (ws) {
      ws.close()
      set({ ws: null, isConnected: false })
    }
    if (priceWs) {
      priceWs.close()
      set({ priceWs: null, isPriceConnected: false })
    }
  },

  updateCandle: (data: any) => {
    const timestamp = Math.floor(data.time)
    const candles = new Map(get().candles)
    
    candles.set(timestamp, {
      time: timestamp as Time,
      open: data.open,
      high: data.high,
      low: data.low,
      close: data.close,
      volume: data.volume
    })

    // Update ticker with candle close price
    set({
      candles,
      ticker: {
        symbol: data.symbol,
        price: data.close,
        priceChange: 0,
        priceChangePercent: 0,
        high24h: data.high,
        low24h: data.low,
        volume24h: data.volume
      }
    })
  },

  updatePrice: (data: any) => {
    const price = parseFloat(data.data?.price || data.price)
    set({ 
      currentPrice: price,
      ticker: get().ticker ? {
        ...get().ticker!,
        price: price
      } : null
    })
  },

  getCandleArray: () => {
    const candles = get().candles
    return Array.from(candles.values()).sort((a, b) => 
      (a.time as number) - (b.time as number)
    )
  }
}))
